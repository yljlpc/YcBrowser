"""历史记录防抖验证（供 test_launch.py 调用的独立脚本）。

验证性能优化没有引入数据丢失：
1. 连续推入 5 条历史 → 内存应新增 5 条；
2. 立即检查磁盘 → 应**少于**内存（说明防抖生效，未每次都写盘）；
3. 等防抖窗口（2.5s）过后 → 磁盘条数应等于内存条数；
4. 关闭窗口时（防抖窗口内）→ 应立即落盘，不丢最后一条。

输出格式：DEB:<新增>,<内存>,<立即落盘>,<防抖后落盘>,<关闭后落盘>
"""
import os
import sys
import time
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-dev-shm-usage",
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtWidgets import QApplication  # noqa: E402

from src.core_client import CoreClient  # noqa: E402
from src.window import MainWindow  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
core = CoreClient()
win = MainWindow(core)

tag = uuid.uuid4().hex[:6]
base = len(win._history)
for i in range(5):
    win._push_history(f"https://debounce-{tag}-{i}.example/")
added = len(win._history) - base
mem = len(win._history)

disk_now = len(win._qsettings().value("history", []))

t0 = time.time()
while time.time() - t0 < 2.5:
    QApplication.processEvents()
    time.sleep(0.02)
disk_after = len(win._qsettings().value("history", []))

# 防抖窗口内关闭 → closeEvent 应立即落盘
win._push_history(f"https://debounce-{tag}-last.example/")
win.close()
disk_close = len(win._qsettings().value("history", []))

print(f"DEB:{added},{mem},{disk_now},{disk_after},{disk_close}")
core.close()
