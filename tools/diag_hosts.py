"""诊断：从 setHtml 页面点击外链，多站点对照（每个站点独立进程）。

用法：bash tools/run_xvfb.sh tools/diag_hosts.py --host github.com
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
    ap.add_argument("--host", default="github.com")
    args = ap.parse_args()
    host = args.host

    app = QApplication.instance() or QApplication(sys.argv)
    register_fonts()
    core = CoreClient()
    win = MainWindow(core)
    win.resize(1360, 860)
    win.show()
    wait_ms(3000)

    t = win.add_tab(None)
    t.set_html(
        "<html><body style='margin:0;font-family:sans-serif'>"
        "<div style='height:200px;background:#eee'>占位区</div>"
        f"<a id='lnk' href='https://{host}' "
        "style='display:block;padding:20px;font-size:20px'>链接</a>"
        "</body></html>"
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
            return {x:x, y:y, hitTag: hit?hit.tagName:null, href: el.href};
        })()""",
    )
    print(f"host={host} 命中={rect}", flush=True)
    if rect:
        z = t.view.zoomFactor()
        o = t.view.mapToGlobal(QPoint(0, 0))
        sx, sy = o.x() + int(rect["x"] * z), o.y() + int(rect["y"] * z)
        subprocess.run(["xdotool", "mousemove", "--sync", str(sx), str(sy)])
        time.sleep(0.2)
        subprocess.run(["xdotool", "click", "--delay", "120", "1"])

    for i in range(6):
        wait_ms(2500)
        cur = t.page.url().toString()
        if cur != old:
            break
    cur = t.page.url().toString()
    print(f"  old={old[:50]}", flush=True)
    print(f"  new={cur[:60]}", flush=True)
    print(f"  → {'✅ 导航成功' if cur != old else '❌ 未导航'}", flush=True)

    win.close()
    core.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
