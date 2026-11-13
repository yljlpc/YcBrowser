"""与 Rust 核心 (omnibrowser-core) 的行式 JSON-RPC 客户端。

核心以子进程方式常驻：stdin 收请求、stdout 回应答，每行一个 JSON 对象。
请求/应答严格一一对应，本客户端用一把锁保证顺序，避免并发错乱。

稳定性增强：
- 请求带超时（默认 5s），核心无响应时立即返回错误而非永久阻塞 GUI；
- 核心进程意外退出时自动重启，保证前端始终可用。
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import threading


def _find_binary():
    env = os.environ.get("OMNIBROWSER_CORE")
    if env and os.path.isfile(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))  # src/
    # Windows 可执行文件带 .exe 后缀；其余平台无后缀。
    suffix = ".exe" if sys.platform == "win32" else ""
    name = "omnibrowser-core" + suffix
    candidates = [
        os.path.join(here, "..", name),
        os.path.join(here, "..", "core", "target", "release", name),
    ]
    # 冻结运行（PyInstaller）：src 包被编译进 PYZ 归档，__file__ 指向虚拟路径，
    # 「../」推算不到真实目录；核心 exe 实际在 sys._MEIPASS（one-folder 即 _internal）下。
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, os.path.join(meipass, name))
    for c in candidates:
        c = os.path.normpath(c)
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    found = shutil.which(name)
    if found:
        return found
    return os.path.normpath(os.path.join(here, "..", name))


class CoreClient:
    """封装对 omnibrowser-core 的进程内长连接调用。"""

    def __init__(self, binary_path=None, timeout=5.0):
        self.binary_path = binary_path or _find_binary()
        self.timeout = timeout
        self._lock = threading.Lock()
        self._start()

    def _start(self):
        self.proc = subprocess.Popen(
            [self.binary_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

    def alive(self):
        return self.proc.poll() is None

    def request(self, cmd, **args):
        req = {"cmd": cmd}
        req.update(args)
        line = json.dumps(req, ensure_ascii=False)
        with self._lock:
            if not self.alive():
                try:
                    self._start()
                except Exception as exc:  # noqa: BLE001
                    return {"ok": False, "error": f"core restart failed: {exc}"}
            proc = self.proc
            try:
                proc.stdin.write(line + "\n")
                proc.stdin.flush()
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"io error: {exc}"}
            # 在独立线程读取，主线程用超时等待，避免 GUI 卡死。
            # proc 在闭包里按值捕获，重启动后不会误读新进程的管道。
            q: "queue.Queue[str]" = queue.Queue()

            def reader(p):
                try:
                    q.put(p.stdout.readline())
                except Exception:  # noqa: BLE001
                    q.put("")

            t = threading.Thread(target=reader, args=(proc,), daemon=True)
            t.start()
            try:
                resp_line = q.get(timeout=self.timeout)
            except queue.Empty:
                # 超时：进程可能已挂死。终止并重启，避免后续请求永久阻塞 GUI。
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self._start()
                except Exception:  # noqa: BLE001
                    pass
                return {"ok": False, "error": "core timeout (已重启)"}
        if not resp_line:
            return {"ok": False, "error": "core closed"}
        try:
            data = json.loads(resp_line)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"bad response: {exc}"}
        if data.get("ok") and "result" in data:
            return data["result"]
        return data

    def ping(self):
        return self.request("ping")

    def resolve_nav(self, input_text, engine="bing"):
        return self.request("resolve_nav", input=input_text, engine=engine)

    def engine_spec(self, backend, doc_mode=None):
        if doc_mode:
            return self.request("engine_spec", backend=backend, doc_mode=doc_mode)
        return self.request("engine_spec", backend=backend)

    def negotiate_docmode(self, x_ua_compatible, current=None):
        if current:
            return self.request(
                "negotiate_docmode", x_ua_compatible=x_ua_compatible, current=current
            )
        return self.request("negotiate_docmode", x_ua_compatible=x_ua_compatible)

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.terminate()
        except Exception:  # noqa: BLE001
            pass
