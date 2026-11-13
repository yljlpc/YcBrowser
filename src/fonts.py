"""注册随附的中文字体，并提供 UI 字体选择。

字体随包一起分发（<pkg>/fonts 目录），同时保留对开发期桌面 fonts 目录的回退，
保证同一份代码在开发环境与安装后的 /opt 路径下都能正确注册字体。
优先挑选适合屏幕 UI 的字体（书宋/仿宋作正文，小标宋作标题）。
"""
import glob
import os

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

_REGISTERED = []

# 候选字体目录：打包后的 <pkg>/fonts 优先，开发环境与常见桌面目录作为回退。
_PREFERRED_UI = [
    "方正书宋简体",
    "仿宋_GB2312",
    "仿宋_GB2312 by lhaix",
    "方正仿宋_GBK",
]
_PREFERRED_HEADING = [
    "方正小标宋简体",
    "方正小标宋_GBK",
    "方正小标宋_GB18030",
]


def _font_search_dirs():
    import sys

    here = os.path.dirname(os.path.abspath(__file__))  # src/
    pkg = os.path.normpath(os.path.join(here, "..", "fonts"))
    if sys.platform == "win32":
        # Windows：优先用随包字体目录，回退到系统字体目录。
        sysroot = os.environ.get("SystemRoot", r"C:\Windows")
        dirs = [pkg, os.path.join(sysroot, "Fonts")]
    else:
        # Linux（openKylin / deepin 等）：随包字体 + 常见桌面字体目录回退。
        dirs = [
            pkg,
            os.path.expanduser("~/桌面/fonts"),
            os.path.expanduser("~/Desktop/fonts"),
        ]
    out = []
    for d in dirs:
        d = os.path.normpath(d)
        if d not in out:
            out.append(d)
    return out


def register_fonts():
    """注册字体目录下所有字体文件，返回已注册字族列表（幂等）。"""
    if _REGISTERED:
        return list(_REGISTERED)
    for d in _font_search_dirs():
        if not os.path.isdir(d):
            continue
        for path in sorted(glob.glob(os.path.join(d, "*"))):
            if path.lower().endswith((".ttf", ".otf", ".ttc")):
                fid = QFontDatabase.addApplicationFont(path)
                if fid >= 0:
                    _REGISTERED.extend(QFontDatabase.applicationFontFamilies(fid))
    return list(_REGISTERED)


def available_families():
    return list(dict.fromkeys(_REGISTERED))


def pick_ui_font(size=11):
    register_fonts()
    for name in _PREFERRED_UI:
        if name in available_families():
            return QFont(name, size)
    return QFont(QApplication.font().family(), size)


def pick_heading_font(size=14):
    register_fonts()
    for name in _PREFERRED_HEADING:
        if name in available_families():
            return QFont(name, size)
    return pick_ui_font(size)
