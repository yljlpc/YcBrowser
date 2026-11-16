"""诊断：为什么 R1（点 github.com）不导航，而 R5（点 example.com）能导航。

对照维度：
  D) 目标域名：github.com vs example.com（同样 setHtml + 绝对 URL 链接）
  E) 是否带尾斜杠
  F) base URL 是否同源
  G) 链接数量 / 元素类型

每个组合独立进程内完成（同一标签页顺序点击），避免互相干扰。
"""
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


def click(tab, selector="#lnk"):
    rect = js(
        tab,
        f"""(() => {{
            const el = document.querySelector({selector!r});
            if (!el) return null;
            el.scrollIntoView({{block:'center'}});
            const r = el.getBoundingClientRect();
            const x = r.left + r.width/2, y = r.top + r.height/2;
            const hit = document.elementFromPoint(x, y);
            return {{x:x, y:y, hitTag: hit?hit.tagName:null,
                     ok: !!hit && (hit===el||el.contains(hit)||hit.contains(el)),
                     href: el.getAttribute('href'), origin: location.origin}};
        }})()""",
    )
    if not rect:
        return None, None
    z = tab.view.zoomFactor()
    o = tab.view.mapToGlobal(QPoint(0, 0))
    sx, sy = o.x() + int(rect["x"] * z), o.y() + int(rect["y"] * z)
    subprocess.run(["xdotool", "mousemove", "--sync", str(sx), str(sy)])
    time.sleep(0.15)
    subprocess.run(["xdotool", "click", "--delay", "100", "1"])
    return rect, (sx, sy)


def make_html(href):
    return (
        "<html><body style='margin:0;font-family:sans-serif'>"
        "<div style='height:200px;background:#eee'>占位区</div>"
        f"<a id='lnk' href='{href}' "
        "style='display:block;padding:20px;font-size:20px'>链接</a>"
        "</body></html>"
    )


def trial(win, tag, href):
    """在新建标签页上做一次点击导航，返回是否成功。"""
    t = win.add_tab(None)
    t.set_html(make_html(href))
    wait_ms(2500)
    old = t.page.url().toString()
    # 记录导航请求
    seen = []
    t.page.acceptNavigationRequest = lambda url, ty, im: (
        seen.append((url.toString()[:60], str(ty))), True)[1]
    rect, scr = click(t)
    wait_ms(6000)
    cur = t.page.url().toString()
    ok = cur != old
    print(f"  [{tag}] href={href!r} 命中={rect and rect.get('hitTag')} "
          f"ok={rect and rect.get('ok')} origin={rect and rect.get('origin')}")
    print(f"       old={old[:55]}")
    print(f"       new={cur[:55]}  导航请求={seen}")
    print(f"       → {'✅ 导航成功' if ok else '❌ 未导航'}")
    # 关掉标签，避免影响后续
    idx = win.tabs.indexOf(t)
    if idx >= 0:
        win.tabs.removeTab(idx)
    wait_ms(800)
    return ok


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    register_fonts()
    core = CoreClient()
    win = MainWindow(core)
    win.resize(1360, 860)
    win.show()
    wait_ms(3000)

    print("===== 目标域名对照 =====", flush=True)
    trial(win, "A", "https://github.com")
    trial(win, "B", "https://example.com")
    trial(win, "C", "https://github.com/")
    trial(win, "D", "https://www.qt.io")

    win.close()
    core.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
