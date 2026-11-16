"""诊断：点击外链不导航，是否与 base URL 是保留域名有关。

变体（每个独立进程）：
  b1  base = https://internal.yc-browser.example/   （当前实现，保留域名）
  b2  base = https://example.com/                    （真实可达站点）
  b3  base = https://internal.yc-browser.example/ + 点击 https://example.com

在 b2/b3 里若点击 github.com 能导航，说明问题出在 base 的性质，
而不是目标站点 —— 也就是说当前用保留域名当 base 会影响真实站点的导航。
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

from PyQt6.QtCore import QEventLoop, QPoint, QTimer, QUrl
from PyQt6.QtWidgets import QApplication

from src.core_client import CoreClient
from src.fonts import register_fonts
from src.window import MainWindow


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="b1")
    args = ap.parse_args()
    v = args.variant

    app = QApplication.instance() or QApplication(sys.argv)
    register_fonts()
    core = CoreClient()
    win = MainWindow(core)
    win.resize(1360, 860)
    win.show()
    wait_ms(3000)

    bases = {
        "b1": "https://internal.yc-browser.example/",
        "b2": "https://example.com/",
        "b3": "https://internal.yc-browser.example/",
    }
    targets = {
        "b1": "https://github.com",
        "b2": "https://github.com",
        "b3": "https://example.com",
    }
    base = bases[v]
    target = targets[v]

    t = win.add_tab(None)
    t.view.setHtml(
        "<html><body style='margin:0;font-family:sans-serif'>"
        "<div style='height:200px;background:#eee'>占位区</div>"
        f"<a id='lnk' href='{target}' "
        "style='display:block;padding:20px;font-size:20px'>链接</a>"
        "</body></html>",
        QUrl(base),
    )
    wait_ms(3000)
    old = t.page.url().toString()

    rect = js(
        t,
        """(() => {
            const el = document.querySelector('#lnk');
            if (!el) return null;
            el.scrollIntoView({block:'center'});
            const r = el.getBoundingClientRect();
            const x = r.left + r.width/2, y = r.top + r.height/2;
            const hit = document.elementFromPoint(x, y);
            return {x:x, y:y, hitTag: hit?hit.tagName:null, href: el.href,
                    origin: location.origin};
        })()""",
    )
    print(f"=== {v}  base={base}  target={target}", flush=True)
    print(f"  命中: {rect}", flush=True)
    if rect:
        z = t.view.zoomFactor()
        o = t.view.mapToGlobal(QPoint(0, 0))
        sx, sy = o.x() + int(rect["x"] * z), o.y() + int(rect["y"] * z)
        subprocess.run(["xdotool", "mousemove", "--sync", str(sx), str(sy)])
        time.sleep(0.2)
        subprocess.run(["xdotool", "click", "--delay", "120", "1"])

    for _ in range(8):
        wait_ms(2500)
        if t.page.url().toString() != old:
            break
    cur = t.page.url().toString()
    print(f"  old={old[:55]}", flush=True)
    print(f"  new={cur[:65]}", flush=True)
    print(f"  → {'✅ 导航成功' if cur != old else '❌ 未导航'}", flush=True)

    win.close()
    core.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
