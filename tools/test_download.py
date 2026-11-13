"""下载引擎端到端验证：本地 HTTP 服务器 + 真实多连接分片下载。

验证项：
1. 探测：拿到真实大小、识别 Range 支持、正确解析文件名；
2. 多连接分片：8 连接下载 3MB 文件，字节完全正确（与源文件逐字节比对）；
3. 动态再平衡：连接数少于分片数时仍能完成且不丢字节；
4. 不支持 Range 的服务器 → 自动退化为单流下载；
5. 断点续传：中断后保留 .part 与状态文件，重跑能接着下完；
6. 目标文件去重：同名文件不覆盖。
"""
import hashlib
import http.server
import os
import socketserver
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.downloader import DownloadTask  # noqa: E402

R = []


def check(name, ok, detail=""):
    R.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


# ---------------- 本地测试服务器 ----------------
DATA = os.urandom(3 * 1024 * 1024)   # 3MB 随机内容，便于校验
BIG = os.urandom(5 * 1024 * 1024 + 12345)
NO_RANGE = os.urandom(256 * 1024)
SLOW = os.urandom(8 * 1024 * 1024)   # 慢速路径专用，确保暂停落在下载途中


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    allow_ranges = True

    def log_message(self, *a):  # 静音
        pass

    def _pick(self):
        if self.path.startswith("/big"):
            return BIG, self.allow_ranges
        if self.path.startswith("/norange"):
            return NO_RANGE, False
        if self.path.startswith("/slow"):
            return SLOW, self.allow_ranges
        return DATA, self.allow_ranges

    def do_HEAD(self):
        body, _ = self._pick()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        body, ranges = self._pick()
        rng = self.headers.get("Range")
        start, end = 0, len(body) - 1
        partial = False
        if rng and ranges:
            # bytes=a-b
            spec = rng.split("=", 1)[-1]
            a, _, b = spec.partition("-")
            start = int(a) if a else 0
            end = int(b) if b else len(body) - 1
            end = min(end, len(body) - 1)
            partial = True
        chunk = body[start:end + 1]
        if partial:
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(body)}")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(chunk)))
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        if "filename" in self.path:
            self.send_header("Content-Disposition",
                             'attachment; filename="report 2024.pdf"')
        self.end_headers()
        # 分块写出，模拟真实网络；/slow 路径额外限速，便于测试暂停/续传
        slow = "/slow" in self.path
        for i in range(0, len(chunk), 64 * 1024):
            try:
                self.wfile.write(chunk[i:i + 64 * 1024])
                self.wfile.flush()
                if slow:
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                return


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


httpd = Server(("127.0.0.1", 0), Handler)
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{port}"
print(f"测试服务器: {BASE}\n")

TMP = "/tmp/omnidl_test"
os.makedirs(TMP, exist_ok=True)


def clean():
    for f in os.listdir(TMP):
        try:
            os.remove(os.path.join(TMP, f))
        except OSError:
            pass


# ---------------- 1. 探测 ----------------
print("=== A. 探测 ===")
clean()
t = DownloadTask(f"{BASE}/file.bin", TMP, filename="file.bin", connections=8)
t.probe()
check("探测到真实大小", t.total == len(DATA), f"{t.total} vs {len(DATA)}")
check("识别 Range 支持", t.resumable is True)
check("文件名取自 URL", t.filename == "file.bin", t.filename)

t2 = DownloadTask(f"{BASE}/x?filename=1", TMP, filename="x")
t2.probe()
check("文件名取自 Content-Disposition", t2.filename == "report 2024.pdf", t2.filename)

# ---------------- 2. 多连接下载 ----------------
print("\n=== B. 多连接分片下载 ===")
clean()
t = DownloadTask(f"{BASE}/file.bin", TMP, filename="file.bin", connections=8)
t.probe()
t.start()
st = t.wait(timeout=60)
check("下载完成", st == "completed", f"{st} {t.error}")
out = t.path
check("文件存在", os.path.exists(out), out)
if os.path.exists(out):
    with open(out, "rb") as f:
        got = f.read()
    check("字节完全一致", hashlib.sha256(got).hexdigest() == hashlib.sha256(DATA).hexdigest(),
          f"{len(got)} bytes")
    check("无残留 .part 文件", not os.path.exists(out + ".part"))

# ---------------- 3. 动态再平衡（连接数少于分片）----------------
print("\n=== C. 动态再平衡 ===")
clean()
t = DownloadTask(f"{BASE}/big", TMP, filename="big.bin", connections=4)
t.probe()
t.start()
st = t.wait(timeout=90)
check("大文件多连接完成", st == "completed", f"{st} {t.error}")
if os.path.exists(t.path):
    with open(t.path, "rb") as f:
        got = f.read()
    check("大文件字节一致", hashlib.sha256(got).hexdigest() == hashlib.sha256(BIG).hexdigest(),
          f"{len(got)} bytes")

# ---------------- 4. 不支持 Range → 单流 ----------------
print("\n=== D. 不支持 Range 的服务器 ===")
clean()
t = DownloadTask(f"{BASE}/norange", TMP, filename="nr.bin", connections=8)
t.probe()
check("识别为不支持 Range", t.resumable is False)
t.start()
st = t.wait(timeout=60)
check("单流下载完成", st == "completed", f"{st} {t.error}")
if os.path.exists(t.path):
    with open(t.path, "rb") as f:
        got = f.read()
    check("单流字节一致", hashlib.sha256(got).hexdigest() == hashlib.sha256(NO_RANGE).hexdigest())

# ---------------- 5. 断点续传 ----------------
print("\n=== E. 断点续传 ===")
clean()
# 用慢速大文件，确保暂停落在下载途中（而非下载已完成）
t = DownloadTask(f"{BASE}/slow", TMP, filename="resume.bin", connections=2)
t.probe()
t.start()
# 等待确实下到一部分数据再暂停
deadline = time.time() + 30
while time.time() < deadline:
    if 0 < t.downloaded < t.total:
        break
    time.sleep(0.05)
check("下载途中已有部分数据", 0 < t.downloaded < t.total, f"{t.downloaded}/{t.total}")
t.pause()
check("暂停后保留 .part 文件", os.path.exists(t.path + ".part"),
      f"{os.path.getsize(t.path + '.part') if os.path.exists(t.path + '.part') else 0} bytes")
check("暂停后保留状态文件", os.path.exists(t.path + ".omnidl"))
check("暂停后状态为 paused", t.state == "paused", t.state)
# .part 文件按设计预分配为全长（各分片直接写入自己偏移，无需最后合并），
# 因此完成度要看"已下载字节"，而不是文件大小。
check("已下部分数据（未完成）", 0 < t.downloaded < t.total, f"{t.downloaded}/{t.total}")
# 继续下载（同一任务对象，读取断点状态）
t.start()
st = t.wait(timeout=180)
check("续传后完成", st == "completed", f"{st} {t.error}")
if os.path.exists(t.path):
    with open(t.path, "rb") as f:
        got = f.read()
    check("续传字节一致", hashlib.sha256(got).hexdigest() == hashlib.sha256(SLOW).hexdigest(),
          f"{len(got)} bytes")
    check("续传后无残留状态文件", not os.path.exists(t.path + ".omnidl"))

# ---------------- 6. 目标文件去重 ----------------
print("\n=== F. 目标文件去重 ===")
clean()
a = DownloadTask(f"{BASE}/file.bin", TMP, filename="dup.bin", connections=4)
a.probe()
a.start()
a.wait(timeout=60)
b = DownloadTask(f"{BASE}/file.bin", TMP, filename="dup.bin", connections=4)
b.probe()
check("同名文件不覆盖", b.path != a.path and b.path.endswith("dup (1).bin"), b.path)

httpd.shutdown()

# ---------------- 汇总 ----------------
print("\n=== 汇总 ===")
passed = sum(1 for _, ok in R if ok)
print(f"通过 {passed}/{len(R)}")
fails = [n for n, ok in R if not ok]
if fails:
    print("失败项: " + ", ".join(fails))
    sys.exit(1)
print("全部通过")
