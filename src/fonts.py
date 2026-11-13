"""注册随附的中文字体，并提供 UI 字体选择。

字体随包一起分发（<pkg>/fonts 目录），同时保留对开发期桌面 fonts 目录的回退，
保证同一份代码在开发环境与安装后的 /opt 路径下都能正确注册字体。
优先挑选适合屏幕 UI 的字体（书宋/仿宋作正文，小标宋作标题）。

随包分发的字体为开源字体 **思源宋体 Noto Serif SC**（SIL OFL 1.1，见 fonts/OFL.txt），
仅作为**开源兜底**：若本机已安装方正系列字体，仍优先生效方正字体，
因此开发/本地环境的界面观感保持不变；CI 与正式分发包中没有方正字体时
自动回落到思源宋体。

> 为什么不随包分发方正字体：方正系列是**商业字体**，再分发受版权限制，
> 且 SignPath Foundation 明确要求「不得包含专有、非开源组件」，
> 携带商业字体的分发包无法通过开源代码签名审核。
"""
import glob
import os

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

_REGISTERED = []

# 候选字体目录：打包后的 <pkg>/fonts 优先，开发环境与常见桌面目录作为回退。
# 顺序即优先级：方正系列在前（本地环境观感不变），开源兜底在后。
_PREFERRED_UI = [
    "方正书宋简体",
    "仿宋_GB2312",
    "仿宋_GB2312 by lhaix",
    "方正仿宋_GBK",
    "Noto Serif SC",  # 开源兜底：思源宋体，随包分发
]
_PREFERRED_HEADING = [
    "方正小标宋简体",
    "方正小标宋_GBK",
    "方正小标宋_GB18030",
    "Noto Serif SC",  # 开源兜底：思源宋体，随包分发
]


def _font_search_dirs():
    import sys

    here = os.path.dirname(os.path.abspath(__file__))  # src/
    pkg = os.path.normpath(os.path.join(here, "..", "fonts"))

    # 冻结运行（PyInstaller）时，src 包被编译进 PYZ 归档，__file__ 指向
    # 归档内的虚拟路径，此时「../fonts」解析不到实际目录。
    # 真实目录在 sys._MEIPASS（one-folder 模式即 _internal）下。
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        pkg = os.path.join(meipass, "fonts")

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
