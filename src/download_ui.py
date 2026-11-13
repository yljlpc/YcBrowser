"""下载管理器界面：进度、速度、连接数、暂停/继续/取消、打开文件/目录。

承接 SwiftDL 的下载管理交互（分组、实时速度、每连接视图、队列），
但用 PyQt6 原生控件实现，风格与主窗口一致。
"""
import os
import subprocess
import sys

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .downloader import human_size, human_time
from .zh import zh_buttons, zh_msg_question

# 状态 → (中文名, 排序权重)
STATE_LABEL = {
    "pending": "等待中",
    "downloading": "下载中",
    "paused": "已暂停",
    "completed": "已完成",
    "failed": "失败",
}


def open_in_file_manager(path):
    """在系统文件管理器中定位文件（跨平台）。"""
    if not path or not os.path.exists(path):
        return False
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
            return True
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(os.path.abspath(path))))
        return True
    except Exception:  # noqa: BLE001
        return False


class DownloadRow:
    """一行下载任务的状态快照。"""

    __slots__ = ("task", "item", "progress", "speed_label", "status_label")

    def __init__(self, task, item, progress, speed_label, status_label):
        self.task = task
        self.item = item
        self.progress = progress
        self.speed_label = speed_label
        self.status_label = status_label


class DownloadManagerDialog(QDialog):
    """下载管理器主对话框。"""

    changed = pyqtSignal()

    def __init__(self, parent=None, downloader=None):
        super().__init__(parent)
        self.setWindowTitle("下载管理")
        # 保证按钮行与表格有足够空间，避免窄窗口下挤压溢出
        self.setMinimumSize(560, 320)
        self.dl = downloader
        self._rows = {}   # id(task) -> DownloadRow

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["文件", "状态", "大小", "进度", "速度"])
        # 列宽策略：全部按固定宽度 + 首列 Stretch。
        # 若用 Stretch 拉伸首列，其余列会被挤到视口外；这里让首列吃掉剩余空间，
        # 其余列固定，保证状态/进度/速度始终可见。
        header = self.tree.header()
        header.setStretchLastSection(False)
        for col, width in ((1, 76), (2, 132), (3, 58), (4, 92)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.tree.setColumnWidth(col, width)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.setColumnWidth(0, 220)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        root.addWidget(self.tree)

        bar = QHBoxLayout()
        bar.setContentsMargins(10, 6, 10, 6)
        bar.setSpacing(6)
        self.btn_pause = QPushButton("暂停")
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_resume = QPushButton("继续")
        self.btn_resume.clicked.connect(self._on_resume)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_retry = QPushButton("重试")
        self.btn_retry.clicked.connect(self._on_retry)
        self.btn_open = QPushButton("打开")
        self.btn_open.clicked.connect(self._on_open)
        self.btn_folder = QPushButton("所在目录")
        self.btn_folder.clicked.connect(self._on_folder)
        self.btn_clear = QPushButton("清除已完成")
        self.btn_clear.clicked.connect(self._on_clear_done)
        for b in (self.btn_pause, self.btn_resume, self.btn_cancel, self.btn_retry,
                  self.btn_open, self.btn_folder, self.btn_clear):
            b.setMinimumWidth(66)
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        root.addWidget(zh_buttons(self, close="关闭", with_ok=False, with_cancel=False))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(500)

    # ---------------- 任务接入 ----------------
    def add_task(self, task):
        """登记一个下载任务并显示。"""
        item = QTreeWidgetItem(self.tree)
        item.setText(0, task.filename or task.url.rsplit("/", 1)[-1] or "下载")
        item.setText(1, STATE_LABEL.get(task.state, task.state))
        item.setText(2, human_size(task.total) if task.total else "未知")
        item.setText(3, "")
        item.setText(4, "")
        item.setData(0, Qt.ItemDataRole.UserRole, id(task))
        row = DownloadRow(task, item, QProgressBar(self), QLabel(""), QLabel(""))
        self._rows[id(task)] = row
        self.refresh()
        return row

    def refresh(self):
        """刷新所有行的进度与状态。"""
        for row in list(self._rows.values()):
            t = row.task
            total = t.total or 0
            done = t.downloaded or 0
            row.item.setText(1, STATE_LABEL.get(t.state, t.state))
            if total:
                row.item.setText(2, f"{human_size(done)} / {human_size(total)}")
                pct = int(done * 100 / total)
                row.item.setText(3, f"{pct}%")
            else:
                row.item.setText(2, human_size(done))
                row.item.setText(3, "…")
            if t.state == "downloading":
                eta = (total - done) / t.speed if t.speed > 1 and total else None
                row.item.setText(4, f"{human_size(int(t.speed))}/s")
                row.item.setToolTip(4, f"剩余约 {human_time(eta)}")
            else:
                row.item.setText(4, "")
            if t.state == "failed" and t.error:
                row.item.setToolTip(1, t.error)
            # 完整信息放在提示里，列窄时不丢信息
            row.item.setToolTip(0, f"{t.filename}\n{t.path or t.url}")
        self._update_buttons()

    # ---------------- 交互 ----------------
    def _current_task(self):
        item = self.tree.currentItem()
        if item is None:
            return None
        key = item.data(0, Qt.ItemDataRole.UserRole)
        row = self._rows.get(key)
        return row.task if row else None

    def _on_current_changed(self, *_a):
        self._update_buttons()

    def _update_buttons(self):
        t = self._current_task()
        has = t is not None
        self.btn_pause.setEnabled(has and t.state == "downloading")
        self.btn_resume.setEnabled(has and t.state in ("paused", "failed"))
        self.btn_cancel.setEnabled(has and t.state in ("downloading", "paused", "failed"))
        self.btn_retry.setEnabled(has and t.state == "failed")
        self.btn_open.setEnabled(has and t.state == "completed")
        self.btn_folder.setEnabled(has and t.state == "completed")

    def _on_pause(self):
        t = self._current_task()
        if t:
            t.pause()
            self.refresh()

    def _on_resume(self):
        t = self._current_task()
        if t:
            if t.state == "failed":
                t.state = "paused"
            t.start()
            self.refresh()

    def _on_cancel(self):
        t = self._current_task()
        if t and QMessageBoxHelper.confirm(self, "取消下载", f"确定取消「{t.filename}」的下载？"):
            t.cancel()
            self.refresh()

    def _on_retry(self):
        self._on_resume()

    def _on_open(self):
        t = self._current_task()
        if t and t.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(t.path))

    def _on_folder(self):
        t = self._current_task()
        if t and t.path:
            open_in_file_manager(t.path)

    def _on_clear_done(self):
        for key, row in list(self._rows.items()):
            if row.task.state == "completed":
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(row.item))
                del self._rows[key]
        self.refresh()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


class QMessageBoxHelper:
    """确认对话框的小包装（便于单测替换）。"""

    @staticmethod
    def confirm(parent, title, text):
        from PyQt6.QtWidgets import QMessageBox

        return zh_msg_question(parent, title, text)
