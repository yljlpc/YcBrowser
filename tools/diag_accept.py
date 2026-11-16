"""诊断：R1 唯独 github.com 不导航 —— 定位 acceptNavigationRequest 内部哪一步导致被拒。

变体（每个变体单独进程跑，用 --variant 选择）：
  v0  真实代码路径（走仓库里的 BrowserPage.acceptNavigationRequest）
  v1  猴补 acceptNavigationRequest 直接 return True（完全绕开仓库实现）
  v2  只调 super().acceptNavigationRequest（跳过 on_external_nav 回调）
  v3  真实代码路径 + 目标换成 example.com（对照域名）

每个变体都打印：命中校验、导航请求、最终 URL。
"""
import argparse
import os
import subprocess
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


def js(tab, code, timeout=12000, retries=4):
    for _ in range(retries):
        out = {}
        loop = QEventLoop()

        def _quit(*_a):
            try:
                loop.quit()
            except RuntimeError:
                pass

        cb = lambda v: (out.__setitem__("v", v), _quit())
        tab.page.runJavaScript(code, cb)
        QTimer.singleShot(timeout, _quit)
        loop.exec()
        if "v" in out:
            return out["v"]
        wait_ms(2000)
    return None


HTML = (
    "<html><body style='margin:0;font-family:sans-serif'>"
    "<div style='height:200px;background:#eee'>占位区</div>"
    "<a id='lnk' href='https://github.com' "
    "style='display:block;padding:20px;font-size:20px'>去 GitHub</a>"
    "</body></html>"
)

HTML_EX = HTML.replace("https://github.com", "https://example.com")


def click(tab):
    rect = js(
        tab,
        """(() => {
            const el = document.querySelector('#lnk');
            if (!el) return null;
            el.scrollIntoView({block:'center'});
            const r = el.getBoundingClientRect();
            const x = r.left + r.width/2, y = r.top + r.height/2;
            const hit = document.elementFromPoint(x, y);
            return {x:x, y:y, hitTag: hit?hit.tagName:null,
                    ok: !!hit && (hit===el||el.contains(hit)||hit.contains(el)),
                    origin: location.origin, href: el.href};
        })()""",
    )
    if not rect:
        print("  元素未找到")
        return None
    z = tab.view.zoomFactor()
    o = tab.view.mapToGlobal(QPoint(0, 0))
    sx, sy = o.x() + int(rect["x"] * z), o.y() + int(rect["y"] * z)
    subprocess.run(["xdotool", "mousemove", "--sync", str(sx), str(sy)])
    time.sleep(0.15)
    subprocess.run(["xdotool", "click", "--delay", "100", "1"])
    return rect


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="v0")
    args = ap.parse_args()
    v = args.variant

    app = QApplication.instance() or QApplication(sys.argv)
    register_fonts()
    core = CoreClient()
    win = MainWindow(core)
    win.resize(1360, 860)
    win.show()
    wait_ms(3000)

    t = win.add_tab(None)
    t.set_html(HTML_EX if v == "v3" else HTML)
    wait_ms(2500)
    old = t.page.url().toString()

    if v == "v1":
        t.page.acceptNavigationRequest = lambda url, ty, im: True
    elif v == "v2":
        t.page.acceptNavigationRequest = (
            lambda url, ty, im: BrowserPage.acceptNavigationRequest(t.page, url, ty, im)
        )

    print(f"=== 变体 {v}  初始 URL={old[:60]}", flush=True)
    rect = click(t)
    print(f"  命中: {rect}", flush=True)
    wait_ms(7000)
    cur = t.page.url().toString()
    print(f"  最终 URL = {cur[:70]}", flush=True)
    print(f"  → {'✅ 导航成功' if cur != old else '❌ 未导航'}", flush=True)

    win.close()
    core.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
