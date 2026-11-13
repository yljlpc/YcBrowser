"""真实启动并截图：在 Xvfb(:99) 下拉起 MainWindow，渲染主页后抓取窗口与页面。"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
os.environ.setdefault("DISPLAY", ":99")
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
from src.internal import home_html
from src.theme import STYLE
from src.window import MainWindow

OUT = os.path.join(ROOT, "outputs")
os.makedirs(OUT, exist_ok=True)


def wait_loaded(tab, timeout=12000):
    loop = QEventLoop()
    done = {}

    def on_progress(v):
        if v >= 100:
            done["ok"] = True
            loop.quit()

    tab.load_progress.connect(on_progress)
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    return done.get("ok", False)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("OmniBrowser")
    register_fonts()
    from src.fonts import pick_ui_font
    app.setFont(pick_ui_font(11))
    app.setStyleSheet(STYLE)

    core = CoreClient()
    win = MainWindow(core)
    win.resize(1280, 800)
    win.show()

    # 渲染一段示例页面作为“显示窗”证据
    tab = win.tabs.currentWidget()
    tab.set_html(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>渲染验证</title></head><body style='font-family:sans-serif;padding:24px'>"
        "<h1>OmniBrowser 渲染验证</h1>"
        "<p>Trident / WebKit / Blink 多内核兼容模式，分辨率自适应。</p>"
        "<p style='color:#2b6cff'>这是一个由 Blink 实际渲染的页面。</p>"
        "</body></html>"
    )
    wait_loaded(tab)
    time.sleep(0.6)

    # 抓取整窗（工具栏/地址栏/引擎下拉/标签）
    ui_pix = win.grab()
    ui_path = os.path.join(OUT, "omni_ui.png")
    ui_pix.save(ui_path)

    # 抓取页面内容（Qt6 下 QWidget.grab 可捕获 WebEngine 渲染层）
    page_path = os.path.join(OUT, "omni_page.png")

    def save_and_quit():
        tab.view.grab().save(page_path)
        print("PAGE_SAVED", page_path)
        app.quit()

    QTimer.singleShot(800, save_and_quit)
    app.exec()

    core.close()
    print("UI_SAVED", ui_path)
    print("DONE")


if __name__ == "__main__":
    main()
