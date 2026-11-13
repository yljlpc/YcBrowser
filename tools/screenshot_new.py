"""新功能界面截图（offscreen 真实渲染）：翻译按钮、下载管理器、设置页。

产出到 outputs/：
  omni_translate.png   工具栏含「翻译」按钮的整窗
  omni_downloads.png   下载管理器对话框
  omni_settings.png    设置页（含翻译与下载设置项）
  omni_translated.png  英文页面被翻译为中文后的渲染结果
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer",
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from src.core_client import CoreClient
from src.fonts import register_fonts
from src.window import MainWindow

OUT = os.path.join(ROOT, "outputs")
os.makedirs(OUT, exist_ok=True)


def wait_ms(ms):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        QApplication.processEvents()
        time.sleep(0.01)


def wait_loaded(tab, timeout=12000):
    loop = QEventLoop()
    ok = {"v": False}
    tab.page.loadFinished.connect(lambda r: (ok.__setitem__("v", True), loop.quit()))
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    wait_ms(300)


def js(tab, code, timeout=8000):
    out = {}
    loop = QEventLoop()
    tab.page.runJavaScript(code, lambda v: (out.__setitem__("v", v), loop.quit()))
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    return out.get("v")


def shot(widget, name):
    path = os.path.join(OUT, name)
    widget.grab().save(path)
    print(f"  saved {path} ({os.path.getsize(path)} bytes)")


app = QApplication.instance() or QApplication(sys.argv)
register_fonts()
core = CoreClient()
win = MainWindow(core)
win.resize(1360, 860)
win.show()
wait_ms(1200)

print("生成截图：")

# 1) 主窗口（含翻译按钮）
shot(win, "omni_translate.png")

# 2) 英文页面 → 翻译为中文 → 截图
EN = ("<html><head><title>OmniBrowser</title><meta charset='utf-8'>"
      "<style>body{font-family:'Noto Sans CJK SC',sans-serif;max-width:760px;"
      "margin:40px auto;line-height:1.9;color:#1f2329}h1{color:#2f6fed}</style>"
      "</head><body><h1>Welcome to OmniBrowser</h1>"
      "<p>Download the browser and install it on your computer.</p>"
      "<p>This feature was disabled by the administrator.</p>"
      "<p>The installation is finished, so you can open the application now.</p>"
      "</body></html>")
tab = win.add_tab(None)
tab.set_html(EN)
wait_loaded(tab)

from src.translate import EXTRACT_JS, FILL_JS
import json

items = js(tab, EXTRACT_JS) or []
from src.translate import TranslateClient

client = TranslateClient(core=core, backend="mymemory", timeout=25)
pairs = {}
for t in items:
    if client.should_translate(t, "zh"):
        try:
            pairs[t] = client.translate(t, "auto", "zh")
        except Exception as exc:  # noqa: BLE001
            print("    翻译失败:", exc)
if pairs:
    js(tab, FILL_JS.replace("__PAIRS__", json.dumps(pairs, ensure_ascii=False)))
    wait_ms(800)
shot(tab.view, "omni_translated.png")
print("  译文示例:", list(pairs.items())[:2])

# 3) 下载管理器
from src.downloader import DownloadTask

dldir = os.path.join(OUT, "_dl_demo")
os.makedirs(dldir, exist_ok=True)
for name, size, done, state in (
    ("ubuntu-26.04-desktop-amd64.iso", 5_800_000_000, 2_100_000_000, "downloading"),
    ("movie-1080p.mp4", 1_200_000_000, 1_200_000_000, "completed"),
    ("manual-guide.pdf", 3_400_000, 1_100_000, "downloading"),
):
    t = DownloadTask("https://example.com/" + name, dldir, filename=name, connections=8)
    t.filename = name
    t.total = size
    t.downloaded = done
    t.state = state
    t.speed = 24_500_000 if state == "downloading" else 0
    win._dl_tasks.append(t)
win._open_downloads()
wait_ms(700)
shot(win._dl_dlg, "omni_downloads.png")

# 4) 设置页
from src.window import SettingsDialog

dlg = SettingsDialog(win.settings, win)
dlg.resize(560, 640)
dlg.show()
wait_ms(500)
shot(dlg, "omni_settings.png")

win.close()
core.close()
print("完成")
