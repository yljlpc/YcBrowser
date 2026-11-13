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

    # 只注册「需要显式注册」的字体目录：
    #   - 随包分发的字体（不在系统字体目录，必须显式注册）
    #   - 用户自备字体目录（开发期放在桌面 fonts/ 下）
    #
    # **刻意不扫描 C:\Windows\Fonts**：系统字体本来就由 Windows 全局提供，
    # 浏览器与 Qt 都能直接使用；而逐个调用 QFontDatabase.addApplicationFont()
    # 解析那 300+ 个系统字体文件（合计约 470 MB）会让启动多花 1~3 秒，
    # 是启动慢的头号原因。系统字体无需注册。
    user_dirs = [
        os.path.expanduser("~/桌面/fonts"),
        os.path.expanduser("~/Desktop/fonts"),
    ]
    dirs = [pkg] + user_dirs
    out = []
    for d in dirs:
        d = os.path.normpath(d)
        if d not in out:
            out.append(d)
    return out


def register_fonts(verbose=False):
    """注册字体目录下所有字体文件，返回已注册字族列表（幂等）。

    只处理「随包字体 + 用户自备字体目录」，不触碰系统字体目录 —— 详见
    _font_search_dirs 的说明。
    """
    if _REGISTERED:
        return list(_REGISTERED)
    import time

    t0 = time.perf_counter()
    count = 0
    for d in _font_search_dirs():
        if not os.path.isdir(d):
            continue
        for path in sorted(glob.glob(os.path.join(d, "*"))):
            if path.lower().endswith((".ttf", ".otf", ".ttc")):
                fid = QFontDatabase.addApplicationFont(path)
                if fid >= 0:
                    _REGISTERED.extend(QFontDatabase.applicationFontFamilies(fid))
                count += 1
    if verbose:
        dt = (time.perf_counter() - t0) * 1000
        print(f"[fonts] 注册 {count} 个字体文件，耗时 {dt:.0f} ms，"
              f"字族 {len(set(_REGISTERED))} 个")
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
