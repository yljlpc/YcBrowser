"""布局与输入的纯算法（只依赖 QtCore，不触发 WebEngine / GPU）。

这些逻辑原先散落在 MainWindow 里，抽出来后可独立单元测试，
也避免为验证算法而去导入 window.py（导入会初始化 Chromium 渲染进程）。
"""
import re

from PyQt6.QtCore import QSize

# 窗口占可用屏幕的比例与上限（避免 4K 屏上窗口过大、小屏上过小）
WIN_W_FRAC = 0.92
WIN_H_FRAC = 0.90
WIN_W_MAX = 1700
WIN_H_MAX = 1050
WIN_W_MIN = 800
WIN_H_MIN = 560


def window_size(screen_w, screen_h):
    """按主屏可用区域推导主窗口尺寸，并做上下限保护。"""
    if screen_w <= 0 or screen_h <= 0:
        return QSize(WIN_W_MIN, WIN_H_MIN)
    w = int(min(screen_w * WIN_W_FRAC, WIN_W_MAX))
    h = int(min(screen_h * WIN_H_FRAC, WIN_H_MAX))
    # 小屏保护：不超过屏幕本身，也不低于最小值（除非屏幕更小）
    w = max(min(w, screen_w), min(WIN_W_MIN, screen_w))
    h = max(min(h, screen_h), min(WIN_H_MIN, screen_h))
    return QSize(w, h)


def dialog_size(screen_w, screen_h, frac_w=0.5, frac_h=0.6,
                max_w=900, max_h=720, min_w=420, min_h=300):
    """按主屏分辨率推导对话框尺寸：小屏不溢出，大屏不显得过小。"""
    if screen_w <= 0 or screen_h <= 0:
        return QSize(max_w, max_h)
    w = int(max(min_w, min(screen_w * frac_w, max_w)))
    h = int(max(min_h, min(screen_h * frac_h, max_h)))
    # 绝不超出屏幕可用区域
    w = min(w, screen_w)
    h = min(h, screen_h)
    return QSize(w, h)


_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")
_HOSTISH_RE = re.compile(r"^(www\.|[\w\-]+\.)+[a-zA-Z]{2,}([/:?#]|\?|#|$)")


def looks_like_url(text):
    """判断是否为「完整网址」：带协议，或省略协议但形如 host.tld[/...]。

    用于地址栏：是网址则不弹历史补全下拉，回车直接前往。
    """
    if not text or " " in text:
        return False
    if _URL_SCHEME_RE.match(text):
        return True
    if _HOSTISH_RE.match(text):
        return True
    # localhost / host:port
    if re.match(r"^localhost(:\d+)?([/?#].*)?$", text, re.IGNORECASE):
        return True
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?([/?#].*)?$", text):
        return True
    return False