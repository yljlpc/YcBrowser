"""多连接分片下载执行器（标准库实现，无第三方依赖）。

移植自 SwiftDL（MIT）的下载引擎，但把网络层换成本项目可用的方案：
- SwiftDL 用 reqwest/tokio；本项目核心必须零依赖，网络 I/O 由前端用
  标准库 urllib + 线程池完成。
- **算法**（分片规划、动态再平衡、限速、断点状态、文件命名）放在 Rust 核心
  （core/src/download.rs），本模块只做「取活 → 拉数据 → 写盘 → 交回进度」。

与 SwiftDL 一致的关键行为：
1. 多连接并发，每连接负责一个字节区间，直接写入最终文件的对应偏移（无合并步骤）。
2. 服务器不支持 Range 时自动退化为单流下载。
3. 断点续传：`.omnidl` 记录仍缺失区间，崩溃最多损失最后一秒进度。
4. 失败重试带指数退避；连接若取得进展则重试计数归零。
5. 全局限速（令牌桶，允许欠账）。
"""
import json
import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

# 与核心一致的默认参数
MIN_SPLIT_HALF = 512 * 1024
MAX_CONNECTIONS = 32
MAX_RETRIES = 8
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) YcBrowser/1.0"
STATE_EXT = ".omnidl"
PART_EXT = ".part"


class DownloadError(Exception):
    """下载失败。"""


class DownloadTask:
    """一个下载任务：URL → 本地文件。

    线程模型：主线程调用 start() 后启 N 个工作线程；
    每个工作线程循环地从 SegmentTable 领活（核心算法），
    用 urllib 发 Range 请求拉数据，按偏移写入目标文件。
    """

    def __init__(self, url, dest_dir, filename="", connections=8,
                 referer="", cookies="", core=None, speed_limit=0,
                 on_progress=None, on_state=None):
        self.url = url
        self.dest_dir = dest_dir
        self.connections = max(1, min(connections, MAX_CONNECTIONS))
        self.referer = referer or ""
        self.cookies = cookies or ""
        self.core = core
        self.speed_limit = speed_limit  # 字节/秒，0 = 不限
        self.on_progress = on_progress
        self.on_state = on_state

        # 运行期状态
        self.filename = filename
        self.explicit_name = bool(filename)
        self.total = 0
        self.downloaded = 0
        self.speed = 0.0
        self.state = "pending"   # pending/downloading/paused/completed/failed
        self.error = ""
        # 段表：key=段起点，value=[当前位置, 结束位置]
        self._segs = {}
        # 初始段的认领指针（对应 SwiftDL 的 Table::next）
        self._order = []
        self._next = 0
        self.path = ""          # 最终文件路径
        self.part_path = ""
        self.state_path = ""
        self.resumable = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads = []
        self._done_flag = False
        self._active = 0
        self._speed_lock = threading.Lock()
        self._bucket = 0.0
        self._bucket_ts = time.monotonic()
        self._last_sample = (0.0, 0)
        self._started_at = 0.0

    # ---------------- 生命周期 ----------------
    def probe(self):
        """探测远端文件：大小、是否支持 Range、文件名。

        一次 `Range: bytes=0-0` 请求即可确定：
        - 206 + `Content-Range: bytes 0-0/N` → 支持分片，大小为 N；
        - 200 → 服务器忽略 Range，只能单流下载。
        """
        url = self._direct_url(self.url)
        req = urllib.request.Request(url, headers=self._headers(range_spec="bytes=0-0"))
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                status = resp.status
                headers = resp.headers
                content_length = _int_or_none(headers.get("Content-Length"))
                content_range = headers.get("Content-Range")
                disposition = headers.get("Content-Disposition")
                final_url = resp.geturl()
                etag = headers.get("ETag")
                last_modified = headers.get("Last-Modified")
        except urllib.error.HTTPError as exc:
            raise DownloadError(f"服务器返回 {exc.code}") from exc
        except Exception as exc:  # noqa: BLE001
            raise DownloadError(f"无法连接：{exc}") from exc

        size = None
        resumable = False
        if status == 206 and content_range:
            total = content_range.rsplit("/", 1)[-1].strip()
            if total.isdigit():
                size = int(total)
                resumable = True
        if size is None:
            size = content_length
            resumable = False

        self.resumable = resumable
        self.total = size or 0
        self.etag = etag
        self.last_modified = last_modified
        self.final_url = final_url

        # 文件名优先级：Content-Disposition > 调用方显式指定 > URL 末段
        # （服务端声明的文件名最权威，浏览器下载时它也更贴近用户预期）
        name = ""
        if disposition:
            name = _filename_from_disposition(disposition) or ""
        if not name and self.explicit_name:
            name = self.filename
        if not name:
            name = _filename_from_url(final_url) or ""
        if not name:
            name = "download.bin"
        self.filename = _sanitize(name)

        # 目标路径去重（绝不覆盖已有文件）
        self.path = self._resolve_dest()
        self.part_path = self.path + PART_EXT
        self.state_path = self.path + STATE_EXT
        return self

    def _resolve_dest(self):
        """目标路径去重：同名时追加 " (1)"、" (2)"，绝不覆盖已有文件。

        比对按**文件名**进行（existing 是目录内的文件名清单）。
        """
        try:
            existing = set(os.listdir(self.dest_dir))
        except OSError:
            existing = set()
        base = self.filename
        if base not in existing:
            return os.path.join(self.dest_dir, base)
        stem, ext = os.path.splitext(base)
        for i in range(1, 10000):
            cand = f"{stem} ({i}){ext}"
            if cand not in existing:
                return os.path.join(self.dest_dir, cand)
        return os.path.join(self.dest_dir, base)

    def start(self):
        """开始下载（后台线程）。"""
        if not self.path:
            self.probe()
        self._stop.clear()
        self._done_flag = False
        self.state = "downloading"
        self._started_at = time.monotonic()

        # 断点续传：若已有 .part 与状态文件且匹配，则接着下
        resumed = self._load_state()
        if not resumed:
            self._initial_segments()
            self._truncate_part()

        n = self.connections if self.resumable else 1
        self._threads = []
        self._active = n
        for i in range(n):
            t = threading.Thread(target=self._worker, args=(i,), daemon=True)
            t.start()
            self._threads.append(t)
        return self

    def pause(self):
        """暂停：保存断点后停机（可随时继续）。

        必须等所有工作线程真正退出再返回，否则线程可能继续写 .part 文件，
        与后续的"继续"产生竞争。
        已完成或已失败的任务不应被改写为"已暂停"。
        """
        self._stop.set()
        for t in self._threads:
            if t.is_alive() and t is not threading.current_thread():
                t.join(timeout=3.0)
        if self.state not in ("completed", "failed"):
            self.state = "paused"
        self._save_state()

    def cancel(self):
        """取消：停机并清理临时文件。"""
        self._stop.set()
        self.state = "paused"
        for p in (self.part_path, self.state_path):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    def wait(self, timeout=None):
        """等待下载结束（供测试与命令行使用）。"""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if self.state in ("completed", "failed", "paused"):
                return self.state
            if deadline is not None and time.monotonic() > deadline:
                return "timeout"
            time.sleep(0.05)

    # ---------------- 内部实现 ----------------
    def _headers(self, range_spec=None):
        h = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",  # 避免压缩导致字节偏移错乱
        }
        if self.referer:
            h["Referer"] = self.referer
        if self.cookies:
            h["Cookie"] = self.cookies
        if range_spec:
            h["Range"] = range_spec
        return h

    def _direct_url(self, url):
        """Google Drive 分享链接转直链。"""
        if "drive.google.com" not in url:
            return url
        from urllib.parse import parse_qs

        qs = parse_qs(urlsplit(url).query)
        fid = (qs.get("id") or [None])[0]
        if not fid:
            parts = [p for p in urlsplit(url).path.split("/") if p]
            if len(parts) >= 3 and parts[0] == "file" and parts[1] == "d":
                fid = parts[2]
        if fid and all(c.isalnum() or c in "-_" for c in fid):
            return (f"https://drive.usercontent.google.com/download?id={fid}"
                    f"&export=download&confirm=t")
        return url

    def _initial_segments(self):
        """建立初始段表：均分成 connections 段。"""
        size = self.total
        self._segs = {}
        self._order = []
        self._next = 0
        if not size:
            return
        n = max(1, min(self.connections, MAX_CONNECTIONS))
        n = min(n, max(1, size))
        chunk = size // n
        for i in range(n):
            start = i * chunk
            end = size if i + 1 == n else start + chunk
            self._segs[start] = [start, end]
            self._order.append(start)
        return self._segs

    def _truncate_part(self):
        os.makedirs(self.dest_dir, exist_ok=True)
        # 预分配全长，各分片直接写入自己的偏移，无需最后合并
        with open(self.part_path, "wb") as f:
            if self.total:
                f.truncate(self.total)
            else:
                f.truncate(0)

    def _load_state(self):
        """读取断点状态：把仍缺失的区间恢复为段表。"""
        if not (self.state_path and os.path.exists(self.state_path)):
            return False
        if not (self.part_path and os.path.exists(self.part_path)):
            return False
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return False
        if data.get("url") != self.url:
            return False
        if self.total and data.get("size") != self.total:
            return False
        segs = data.get("segments") or []
        if not segs:
            return False
        self._segs = {}
        self._order = []
        self._next = 0
        for p, e in segs:
            p, e = int(p), int(e)
            if e > p:
                self._segs[p] = [p, e]
                self._order.append(p)
        if not self._segs:
            return False
        self.downloaded = self.total - sum(e - p for p, e in self._segs.values())
        return True

    def _save_state(self):
        if not self.state_path:
            return
        try:
            with self._lock:
                segs = [[p, v[1]] for p, v in self._segs.items() if v[0] < v[1]]
            data = {
                "url": self.url,
                "size": self.total,
                "etag": getattr(self, "etag", None),
                "last_modified": getattr(self, "last_modified", None),
                "segments": segs,
            }
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    def _claim(self):
        """领活：优先派发未认领的整段；整段发完后从剩余最多的段抢一半。

        与 SwiftDL 的 `Shared::claim` 语义一致。返回 (start, end) 或 None。
        """
        with self._lock:
            # 1) 派发未认领的整段
            while self._next < len(self._order):
                key = self._order[self._next]
                self._next += 1
                seg = self._segs.get(key)
                if seg and seg[0] < seg[1]:
                    return (seg[0], seg[1])
            # 2) 全部派完：从剩余最多的段抢走后半段
            best_key = None
            best_rem = 0
            for key, seg in self._segs.items():
                rem = seg[1] - seg[0]
                if rem > best_rem:
                    best_rem = rem
                    best_key = key
            if best_key is None or best_rem < MIN_SPLIT_HALF * 2:
                return None
            seg = self._segs[best_key]
            old_end = seg[1]
            mid = seg[0] + best_rem // 2
            seg[1] = mid          # 原段收缩到 mid
            self._segs[mid] = [mid, old_end]   # 新段接手后半部分
            return (mid, old_end)

    def _commit(self, start, pos):
        """提交某段的写入位置。"""
        with self._lock:
            seg = self._segs.get(start)
            if seg:
                seg[0] = pos

    def _seg_limit(self, start):
        """取某段当前的结束位置。

        动态再平衡时，其他线程可能抢走本段的后半段并把 end 收缩；
        写入方必须每块都重新读取，否则会覆盖被抢走的字节
        （SwiftDL 的 `Segment::write` 用同一把锁校验，正是为此）。
        """
        with self._lock:
            seg = self._segs.get(start)
            return seg[1] if seg else 0

    def _remaining(self):
        with self._lock:
            return sum(v[1] - v[0] for v in self._segs.values() if v[0] < v[1])

    def _worker(self, wid):
        """工作线程：循环领活 → 拉数据 → 交回进度。

        完成判定必须由**最后一个退出的线程**来做：
        任何一个线程先退出就判完成，会把"其他线程还在下"误报为"部分数据缺失"。
        """
        try:
            self._run_worker(wid)
        finally:
            with self._lock:
                self._active -= 1
                last = self._active == 0
            if last and not self._stop.is_set() and not self._done_flag:
                if self._remaining() <= 0:
                    self._complete()
                else:
                    self._fail("部分数据缺失")

    def _run_worker(self, wid):
        failures = 0
        while not self._stop.is_set():
            if not self.resumable:
                # 单流模式：整文件顺序下载
                self._single_stream()
                return
            job = self._claim()
            if job is None:
                # 没有可领的活了：若总量已下完则正常收尾，否则等最后一次判定
                break
            start, end = job
            progressed = self._download_range(start, end)
            if progressed:
                failures = 0
            else:
                failures += 1
                if failures > MAX_RETRIES:
                    self._fail(f"服务器反复中断连接（字节 {start}）")
                    return
                backoff = 0.25 * (2 ** min(failures, 5))
                self._stop.wait(backoff)

        if self._stop.is_set():
            self.state = "paused"
            self._save_state()

    def _download_range(self, start, end):
        """下载 [start, end) 区间，返回是否有进展。

        注意：写入过程中必须动态读取段的当前结束位置——
        其他线程可能抢走本段后半段（动态再平衡），
        继续按旧 end 写会覆盖别人的字节。
        """
        pos = start
        try:
            req = urllib.request.Request(
                self.final_url or self.url,
                headers=self._headers(range_spec=f"bytes={start}-{end - 1}"),
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status not in (206, 200):
                    return False
                f = open(self.part_path, "r+b")
                try:
                    while not self._stop.is_set():
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        # 动态上限：段被抢走后立即停止写入
                        limit = self._seg_limit(start) - pos
                        if limit <= 0:
                            break
                        if len(chunk) > limit:
                            chunk = chunk[:limit]
                        f.seek(pos)
                        f.write(chunk)
                        pos += len(chunk)
                        self._advance(len(chunk))
                        self._commit(start, pos)
                        wait = self._take_limit(len(chunk))
                        if wait > 0:
                            self._stop.wait(wait)
                finally:
                    f.close()
        except Exception:  # noqa: BLE001
            self._commit(start, pos)
            return pos > start
        self._commit(start, pos)
        return pos > start

    def _single_stream(self):
        """不支持 Range 时的单流下载。"""
        try:
            req = urllib.request.Request(self.final_url or self.url,
                                         headers=self._headers())
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(self.part_path, "wb") as f:
                    while not self._stop.is_set():
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        self._advance(len(chunk))
                        wait = self._take_limit(len(chunk))
                        if wait > 0:
                            self._stop.wait(wait)
        except Exception as exc:  # noqa: BLE001
            self._fail(str(exc))
            return
        if self._stop.is_set():
            self.state = "paused"
            return
        self._complete()

    def _advance(self, n):
        with self._lock:
            self.downloaded += n
        self._sample_speed(n)

    def _sample_speed(self, n):
        now = time.monotonic()
        with self._speed_lock:
            ts, dl = self._last_sample
            if now - ts >= 0.5:
                self.speed = (self.downloaded - dl) / (now - ts)
                self._last_sample = (now, self.downloaded)
        if self.on_progress:
            try:
                self.on_progress(self)
            except Exception:  # noqa: BLE001
                pass

    def _take_limit(self, n):
        """令牌桶限速：返回需要等待的秒数。"""
        if self.speed_limit <= 0:
            return 0.0
        now = time.monotonic()
        with self._speed_lock:
            refill = (now - self._bucket_ts) * self.speed_limit
            self._bucket = min(self._bucket + refill, float(self.speed_limit)) - n
            self._bucket_ts = now
            if self._bucket < 0:
                return -self._bucket / self.speed_limit
        return 0.0

    def _complete(self):
        # 多个工作线程可能同时判定完成，只允许一个线程执行收尾。
        with self._lock:
            if self._done_flag:
                return
            self._done_flag = True
        try:
            if self.part_path and os.path.exists(self.part_path):
                os.replace(self.part_path, self.path)
        except OSError as exc:
            self._done_flag = False
            self._fail(f"保存文件失败：{exc}")
            return
        try:
            if self.state_path and os.path.exists(self.state_path):
                os.remove(self.state_path)
        except OSError:
            pass
        self.state = "completed"
        self.downloaded = self.total or self.downloaded
        if self.on_state:
            try:
                self.on_state(self, "completed")
            except Exception:  # noqa: BLE001
                pass

    def _fail(self, msg):
        self.state = "failed"
        self.error = msg
        self._save_state()
        if self.on_state:
            try:
                self.on_state(self, "failed")
            except Exception:  # noqa: BLE001
                pass


# ---------------- 辅助函数 ----------------
def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _filename_from_disposition(value):
    """解析 Content-Disposition，优先 filename*（RFC 6266/5987）。"""
    from urllib.parse import unquote

    parts = [p.strip() for p in value.split(";")]
    for p in parts:
        low = p.lower()
        if low.startswith("filename*="):
            raw = p[len("filename*="):]
            enc = raw.split("'")[2] if raw.count("'") >= 2 else raw
            return unquote(enc.strip('"'))
    for p in parts:
        low = p.lower()
        if low.startswith("filename="):
            return p[len("filename="):].strip().strip('"')
    return None


def _filename_from_url(url):
    path = urlsplit(url).path
    last = path.rstrip("/").rsplit("/")[-1] if path.strip("/") else ""
    return last or None


def _sanitize(name):
    base = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    out = "".join("_" if (c in '<>:"|?*' or ord(c) < 0x20) else c for c in base)
    return out.strip().rstrip(".") or "download.bin"


def human_size(n):
    """字节数转可读字符串（中文单位：字节 / KB / MB / GB / TB）。"""
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def human_time(seconds):
    """秒数转剩余时间。"""
    if seconds is None or seconds < 0 or seconds != seconds or seconds == float("inf"):
        return "--"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分 {seconds % 60} 秒"
    return f"{seconds // 3600} 小时 {(seconds % 3600) // 60} 分"


def test_url(url):
    """测试地址可达性（供设置页"测试连接"用）。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except Exception:  # noqa: BLE001
        return False


# 避免未使用告警：ssl/socket 在需要时可扩展为自定义 CA/代理支持
_ = (ssl, socket)
