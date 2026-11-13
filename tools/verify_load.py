"""独立验证：页面加载 / JS 取值 / 后退前进 / 引擎 UA / 内部页 / 帮助对话框。

用于确认 test_browser.py 中的加载类失败是环境光栅化问题还是代码问题。
由外部通过 QTWEBENGINE_CHROMIUM_FLAGS 控制标志。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401  必须在 QApplication 前
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)

from src.window import MainWindow
from src.core_client import CoreClient

core = CoreClient()
win = MainWindow(core)
win.show()

STATE = {"results": {}}


def js(page, expr, key, then):
    def cb(v):
        STATE["results"][key] = v
        then()

    page.runJavaScript(expr, 0, cb)


def wait_load(tab, then, timeout=20000):
    """等待 loadFinished；超时也继续。"""
    box = {"done": False}

    def on_ok(ok):
        if box["done"]:
            return
        box["done"] = True
        then(ok)

    tab.view.loadFinished.connect(on_ok)
    QTimer.singleShot(timeout, lambda: (not box["done"]) and (box.update(done=True), then(False)))


def phase1():
    """首页标签 + 内部页渲染"""
    t = win.add_tab("data:text/html,<html><head><title>PageA</title></head><body>A</body></html>")

    def after(ok):
        STATE["results"]["load1_ok"] = ok
        STATE["results"]["url1"] = t.view.page().url().toString()
        js(t.view.page(), "document.title", "titleA", phase2)

    wait_load(t, after)


def phase2():
    cur = win._cur()
    cur.view.load(QUrl_pageB())

    def after(ok):
        STATE["results"]["load2_ok"] = ok
        js(cur.view.page(), "document.title", "titleB", phase3)

    # 重新绑定
    box = {"done": False}

    def on_ok(ok):
        if not box["done"]:
            box["done"] = True
            after(ok)

    cur.view.loadFinished.connect(on_ok)
    QTimer.singleShot(20000, lambda: (not box["done"]) and (box.update(done=True), after(False)))


def QUrl_pageB():
    from PyQt6.QtCore import QUrl

    return QUrl("data:text/html,<html><head><title>PageB</title></head><body>B</body></html>")


def phase3():
    cur = win._cur()
    STATE["results"]["can_back"] = cur.can_go_back()
    cur.go_back()

    def after(ok):
        js(cur.view.page(), "document.title", "title_back", phase4)

    box = {"done": False}

    def on_ok(ok):
        if not box["done"]:
            box["done"] = True
            after(ok)

    cur.view.loadFinished.connect(on_ok)
    QTimer.singleShot(20000, lambda: (not box["done"]) and (box.update(done=True), after(False)))


def phase4():
    cur = win._cur()
    STATE["results"]["can_forward"] = cur.can_go_forward()
    cur.go_forward()

    def after(ok):
        js(cur.view.page(), "document.title", "title_forward", phase5)

    box = {"done": False}

    def on_ok(ok):
        if not box["done"]:
            box["done"] = True
            after(ok)

    cur.view.loadFinished.connect(on_ok)
    QTimer.singleShot(20000, lambda: (not box["done"]) and (box.update(done=True), after(False)))


def phase5():
    """引擎 UA"""
    cur = win._cur()
    cur.set_engine("trident")
    STATE["results"]["ua_trident"] = cur.view.page().profile().httpUserAgent()
    cur.set_engine("blink")
    STATE["results"]["ua_blink"] = cur.view.page().profile().httpUserAgent()
    phase6()


def phase6():
    """内部关于页"""
    t = win.add_tab(None)
    win.open_internal(t, "about")

    def after(ok):
        STATE["results"]["about_ok"] = ok
        js(t.view.page(), "document.title", "about_title", phase7)

    box = {"done": False}

    def on_ok(ok):
        if not box["done"]:
            box["done"] = True
            after(ok)

    t.view.loadFinished.connect(on_ok)
    QTimer.singleShot(20000, lambda: (not box["done"]) and (box.update(done=True), after(False)))


def phase7():
    """帮助对话框 HTML 完整性（不 exec，避免阻塞）"""
    html = win._help_html()
    STATE["results"]["help_len"] = len(html)
    STATE["results"]["help_has_copyright"] = "杨凌雨晨商贸有限公司" in html
    STATE["results"]["help_has_mail"] = "554669500@QQ.COM" in html
    STATE["results"]["help_has_version"] = "OmniBrowser " in html
    # 窗口与对话框自适应尺寸
    STATE["results"]["win_size"] = (win.width(), win.height())
    STATE["results"]["dlg_size"] = win._dialog_size(0.6, 0.74, 780, 760, 480, 380)
    finish()


def finish():
    print("=== VERIFY RESULTS ===")
    for k, v in STATE["results"].items():
        print(f"  {k} = {v!r}")
    app.quit()


QTimer.singleShot(500, phase1)
QTimer.singleShot(180000, app.quit)

app.exec()

r = STATE["results"]
print("\n=== SUMMARY ===")
checks = [
    ("页面加载 PageA", r.get("load1_ok") is True),
    ("标题 PageA", r.get("titleA") == "PageA"),
    ("标题 PageB", r.get("titleB") == "PageB"),
    ("可后退", r.get("can_back") is True),
    ("后退后 PageA", r.get("title_back") == "PageA"),
    ("前进后 PageB", r.get("title_forward") == "PageB"),
    ("Trident UA 含 Trident", "Trident" in (r.get("ua_trident") or "")),
    ("Blink UA 含 Chrome", "Chrome" in (r.get("ua_blink") or "")),
    ("关于页标题", r.get("about_title") is not None),
    ("帮助含版权", r.get("help_has_copyright") is True),
    ("帮助含邮箱", r.get("help_has_mail") is True),
]
okn = sum(1 for _, v in checks if v)
for n, v in checks:
    print(("[PASS] " if v else "[FAIL] ") + n)
print(f"\n{okn}/{len(checks)} 通过")
sys.exit(0 if okn == len(checks) else 1)