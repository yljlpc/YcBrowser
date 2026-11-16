"""诊断：Chromium 内部网络栈能否直接加载 github.com。

对照：
  G) 直接 view.load("https://github.com")   —— 不经任何点击
  E) 直接 view.load("https://example.com")

若 G 也失败，则 github 不可达属容器网络/DNS/证书问题，与点击逻辑无关。
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer",
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEventLoop, QTimer, QUrl
from PyQt6.QtWidgets import QApplication

from src.core_client import CoreClient
from src.fonts import register_fonts
from src.window import MainWindow


def wait_ms(ms):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        QApplication.processEvents()
        time.sleep(0.01)


def load_and_wait(tab, url, timeout=25000):
    """直接 load 一个 URL，等到 urlChanged 或超时。"""
    got = {"url": None, "err": None}
    loop = QEventLoop()

    def _quit(*_a):
        try:
            loop.quit()
        except RuntimeError:
            pass

    def on_url(u):
        got["url"] = u.toString()
        _quit()

    tab.page.urlChanged.connect(on_url)
    tab.page.loadFinished.connect(lambda ok: got.setdefault("err", f"loadFinished ok={ok}")
                                  or _quit())
    tab.page.loadProgress.connect(
        lambda p: print(f"    progress {p}%", flush=True) if p in (10, 50, 90) else None
    )
    tab.view.load(QUrl(url))
    QTimer.singleShot(timeout, _quit)
    loop.exec()
    try:
        tab.page.urlChanged.disconnect(on_url)
    except Exception:  # noqa: BLE001
        pass
    return got


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    register_fonts()
    core = CoreClient()
    win = MainWindow(core)
    win.resize(1200, 800)
    win.show()
    wait_ms(2500)

    for tag, url in (("E", "https://example.com"), ("G", "https://github.com")):
        t = win.add_tab(None)
        wait_ms(1500)
        print(f"=== 直接 load {url}", flush=True)
        got = load_and_wait(t, url)
        print(f"  urlChanged={got['url']} {got['err']}", flush=True)
        print(f"  最终 URL = {t.page.url().toString()[:70]}", flush=True)
        print(f"  → {'✅ 加载成功' if got['url'] else '❌ 加载失败/超时'}", flush=True)

    win.close()
    core.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
