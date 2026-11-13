"""OmniBrowser 启动入口。

必须在导入任何 PyQt / WebEngine 模块之前决定 Chromium 运行参数，
否则 QtWebEngine 子进程会以默认参数启动并可能在沙箱 / 无显示环境下直接崩溃。
参数由 src/flags.py 自适应计算（真实桌面启用 GPU 加速）。
"""
import os
import sys
import time

from .flags import chromium_flags

os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", chromium_flags())

from PyQt6.QtWidgets import QApplication

from .core_client import CoreClient
from .fonts import pick_ui_font, register_fonts
from .icons import make_logo
from .theme import STYLE
from .zh import zh_msg_error
from .window import MainWindow


def main():
    t0 = time.perf_counter()
    app = QApplication(sys.argv)
    t_app = time.perf_counter()
    app.setApplicationName("Yc浏览器")
    app.setOrganizationName("Yc浏览器")
    # 固化品牌图标：窗口与所有子对话框（设置 / 帮助 / 书签等）统一显示 Yc 徽标。
    app.setWindowIcon(make_logo(64))

    register_fonts(verbose=True)
    app.setFont(pick_ui_font(11))
    app.setStyleSheet(STYLE)
    t_font = time.perf_counter()

    try:
        core = CoreClient()
    except Exception as exc:  # noqa: BLE001
        zh_msg_error(None, "启动失败", f"无法启动 Rust 核心：{exc}")
        return 1
    t_core = time.perf_counter()

    win = MainWindow(core)
    win.show()
    t_win = time.perf_counter()

    # 启动耗时分解（毫秒）。窗口显示前的耗时直接决定用户点图标后的等待感。
    print(
        "[启动] QApplication {:.0f} | 字体+样式 {:.0f} | Rust 核心 {:.0f} | 主窗口 {:.0f} "
        "| 合计 {:.0f} ms".format(
            (t_app - t0) * 1000,
            (t_font - t_app) * 1000,
            (t_core - t_font) * 1000,
            (t_win - t_core) * 1000,
            (t_win - t0) * 1000,
        )
    )

    rc = app.exec()
    core.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
