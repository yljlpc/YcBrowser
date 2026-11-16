"""诊断：同窗口外链导航为何不发生（R1 失败）。

对照实验：
  A) 新标签页 setHtml(base=https) → 点击 github.com 链接
  B) 先做一次内部页二级目录跳转，再做 A

监听 acceptNavigationRequest 收到的 (url, type, is_main) 与 urlChanged 序列。
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

from PyQt6.QtCore import QEventLoop, QPoint, QTimer
from PyQt6.QtWidgets import QApplication

from src.core_client import CoreClient
from src.fonts import register_fonts
from src.window import MainWindow
from src.tab import BrowserPage


def wait_ms(ms):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        QApplication.processEvents()
        time.sleep(0.01)


def js(tab, code, timeout=8000, retries=3):
    for _ in range(retries):
        out = {}
        loop = QEventLoop()
        cb = lambda v: (out.__setitem__("v", v), loop.quit())
        tab.page.runJavaScript(code, cb)
        QTimer.singleShot(timeout, loop.quit)
        loop.exec()
        if "v" in out:
            return out["v"]
        wait_ms(1500)
    return None


def probe(tab, tag):
    """给该标签页的 page 打补丁，记录导航请求与 URL 变化。"""
    page = tab.page
    orig_acc = page.acceptNavigationRequest

    def acc(url, _type, is_main):
        print(f"    [{tag}] acceptNavigationRequest url={url.toString()[:60]} "
              f"type={_type} is_main={is_main}", flush=True)
        r = orig_acc(url, _type, is_main)
        print(f"    [{tag}]   -> 返回 {r}", flush=True)
        return r

    page.acceptNavigationRequest = acc
    page.urlChanged.connect(
        lambda u: print(f"    [{tag}] urlChanged -> {u.toString()[:70]}", flush=True)
    )
    page.loadStarted.connect(
        lambda: print(f"    [{tag}] loadStarted", flush=True)
    )


LOCAL_HTML = (
    "<html><body style='margin:0;font-family:sans-serif'>"
    "<div style='height:200px;background:#eee'>占位区</div>"
    "<a id='lnk' href='https://github.com' "
    "style='display:block;padding:20px;font-size:20px'>去 GitHub</a>"
    "</body></html>"
)


def click(tab, selector):
    rect = js(
        tab,
        f"""(() => {{
            const el = document.querySelector({selector!r});
            if (!el) return null;
            el.scrollIntoView({{block:'center'}});
            const r = el.getBoundingClientRect();
            return {{x: r.left + r.width/2, y: r.top + r.height/2}};
        }})()""",
    )
    if not rect:
        print("    元素未找到", flush=True)
        return
    z = tab.view.zoomFactor()
    o = tab.view.mapToGlobal(QPoint(0, 0))
    sx, sy = o.x() + int(rect["x"] * z), o.y() + int(rect["y"] * z)
    print(f"    点击屏幕坐标 ({sx}, {sy})  当前 tab={tab.page.url().toString()[:50]}", flush=True)
    import subprocess
    subprocess.run(["xdotool", "mousemove", "--sync", str(sx), str(sy)])
    time.sleep(0.15)
    subprocess.run(["xdotool", "click", "--delay", "100", "1"])


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    register_fonts()
    core = CoreClient()
    win = MainWindow(core)
    win.resize(1360, 860)
    win.show()
    wait_ms(2500)

    tab0 = win._cur()
    probe(tab0, "tab0")

    print("\n===== 场景 A：新标签页直接 setHtml + 点击外链 =====", flush=True)
    t1 = win.add_tab(None)
    t1.set_html(LOCAL_HTML)
    wait_ms(2000)
    probe(t1, "A")
    print(f"  当前标签是否为 t1: {win._cur() is t1}", flush=True)
    click(t1, "#lnk")
    wait_ms(6000)
    print(f"  A 结果 URL = {t1.page.url().toString()[:70]}", flush=True)
    print(f"  A 当前标签 = {win._cur() is t1}", flush=True)

    print("\n===== 场景 B：先走内部页二级目录，再做同样点击 =====", flush=True)
    win.tabs.setCurrentIndex(win.tabs.indexOf(tab0))
    wait_ms(800)
    win.open_internal(tab0, "home")
    wait_ms(2500)
    probe(tab0, "B")
    click(tab0, ".nav a")
    wait_ms(4000)
    print(f"  B 内部页跳转后 URL = {tab0.page.url().toString()[:70]} "
          f"标题={tab0.page.title()!r}", flush=True)

    t2 = win.add_tab(None)
    t2.set_html(LOCAL_HTML)
    wait_ms(2000)
    probe(t2, "B2")
    print(f"  当前标签是否为 t2: {win._cur() is t2}", flush=True)
    click(t2, "#lnk")
    wait_ms(6000)
    print(f"  B2 结果 URL = {t2.page.url().toString()[:70]}", flush=True)

    win.close()
    core.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
