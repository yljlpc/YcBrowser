"""矢量图标模块：随 DPI 高清渲染，保证缩放后依然清晰。

提供：
- 工具栏图标（back/forward/reload/stop/home/newtab/find/download/settings/devtools/help/bookmark/bookmark_on/menu/clear/translate/globe）
- Yc 品牌徽标 make_logo()
- win_icon_size()：按 Windows 工具栏图标尺寸规范取档（100% 缩放 16px，
  125%->20, 150%->24, 175%->28, 200%->32）。

PyQt6 约束：QPainter 的 drawLine/drawRect/drawEllipse/drawArc 只接受整数坐标，
因此所有绘制坐标统一在内部用 int() 截断（图标为像素级，截断无损）。
"""
import math

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPainterPath
from PyQt6.QtWidgets import QApplication

_STROKE = QColor("#3a3f47")
_ACCENT = QColor("#2b6cff")


def _dpr():
    app = QApplication.instance()
    if app and app.primaryScreen():
        return app.primaryScreen().devicePixelRatio() or 1.0
    return 1.0


def _new(size, draw, color=None):
    dpr = _dpr()
    px = QPixmap(max(1, int(size * dpr)), max(1, int(size * dpr)))
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(dpr, dpr)
    draw(p, size, color or _STROKE)
    p.end()
    ic = QIcon()
    ic.addPixmap(px, QIcon.Mode.Normal)
    return ic


def _pen(p, w=2.0, color=_STROKE):
    pen = QPen(color)
    pen.setWidthF(w)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)


def _arrow(p, s, left):
    _pen(p, 2.2)
    if left:
        p.drawLine(int(s * 0.62), int(s * 0.50), int(s * 0.40), int(s * 0.50))
        p.drawLine(int(s * 0.62), int(s * 0.50), int(s * 0.46), int(s * 0.34))
        p.drawLine(int(s * 0.62), int(s * 0.50), int(s * 0.46), int(s * 0.66))
    else:
        p.drawLine(int(s * 0.38), int(s * 0.50), int(s * 0.60), int(s * 0.50))
        p.drawLine(int(s * 0.38), int(s * 0.50), int(s * 0.54), int(s * 0.34))
        p.drawLine(int(s * 0.38), int(s * 0.50), int(s * 0.54), int(s * 0.66))


def _draw_back(p, s, c):
    _arrow(p, s, True)


def _draw_forward(p, s, c):
    _arrow(p, s, False)


def _draw_reload(p, s, c):
    _pen(p, 2.0)
    r = int(s * 0.27)
    cx, cy = int(s * 0.50), int(s * 0.54)
    p.drawArc(cx - r, cy - r, 2 * r, 2 * r, 40 * 16, 300 * 16)
    ax, ay = cx + int(r * 0.60), cy - int(r * 0.80)
    _pen(p, 2.0)
    p.drawLine(ax, ay, ax - int(s * 0.03), ay - int(s * 0.16))
    p.drawLine(ax, ay, ax + int(s * 0.16), ay - int(s * 0.03))


def _draw_stop(p, s, c):
    _pen(p, 2.4)
    m = int(s * 0.34)
    p.drawLine(m, m, s - m, s - m)
    p.drawLine(s - m, m, m, s - m)


def _draw_home(p, s, c):
    _pen(p, 2.0)
    p.drawLine(int(s * 0.20), int(s * 0.48), int(s * 0.50), int(s * 0.22))
    p.drawLine(int(s * 0.50), int(s * 0.22), int(s * 0.80), int(s * 0.48))
    p.drawRect(int(s * 0.32), int(s * 0.48), int(s * 0.36), int(s * 0.30))


def _draw_newtab(p, s, c):
    _pen(p, 2.0, _ACCENT)
    p.drawRect(int(s * 0.22), int(s * 0.22), int(s * 0.56), int(s * 0.56))
    cx, cy = int(s * 0.50), int(s * 0.50)
    p.drawLine(cx - int(s * 0.15), cy, cx + int(s * 0.15), cy)
    p.drawLine(cx, cy - int(s * 0.15), cx, cy + int(s * 0.15))


def _draw_find(p, s, c):
    _pen(p, 2.0)
    r = int(s * 0.20)
    cx, cy = int(s * 0.42), int(s * 0.42)
    p.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
    p.drawLine(cx + int(r * 0.7), cy + int(r * 0.7), int(s * 0.74), int(s * 0.74))


def _draw_download(p, s, c):
    _pen(p, 2.0)
    cx = int(s * 0.50)
    p.drawLine(cx, int(s * 0.16), cx, int(s * 0.60))
    p.drawLine(cx, int(s * 0.60), cx - int(s * 0.16), int(s * 0.44))
    p.drawLine(cx, int(s * 0.60), cx + int(s * 0.16), int(s * 0.44))
    p.drawLine(int(s * 0.26), int(s * 0.76), int(s * 0.74), int(s * 0.76))


def _draw_settings(p, s, c):
    _pen(p, 2.0)
    for y in (0.34, 0.50, 0.66):
        yy = int(s * y)
        p.drawLine(int(s * 0.26), yy, int(s * 0.74), yy)
        p.drawEllipse(int(s * 0.30), yy - int(s * 0.06), int(s * 0.12), int(s * 0.12))
        p.drawEllipse(int(s * 0.58), yy - int(s * 0.06), int(s * 0.12), int(s * 0.12))


def _draw_devtools(p, s, c):
    p.setPen(_STROKE)
    f = QFont("monospace")
    f.setPixelSize(int(s * 0.42))
    f.setBold(True)
    p.setFont(f)
    p.drawText(0, 0, int(s), int(s), Qt.AlignmentFlag.AlignCenter, "</>")


def _draw_help(p, s, c):
    p.setPen(_STROKE)
    f = QFont()
    f.setPixelSize(int(s * 0.58))
    f.setBold(True)
    p.setFont(f)
    p.drawText(0, 0, int(s), int(s), Qt.AlignmentFlag.AlignCenter, "?")


def _star_path(p, s, R):
    r = R * 0.42
    cx, cy = s * 0.5, s * 0.56
    path = QPainterPath()
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = R if i % 2 == 0 else r
        x = cx + rad * math.cos(ang)
        y = cy + rad * math.sin(ang)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    return path


def _draw_bookmark(p, s, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_ACCENT)
    p.drawPath(_star_path(p, s, s * 0.30))


def _draw_bookmark_on(p, s, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_ACCENT)
    p.drawPath(_star_path(p, s, s * 0.30))


def _draw_menu(p, s, c):
    _pen(p, 2.0)
    for y in (0.34, 0.50, 0.66):
        p.drawLine(int(s * 0.26), int(s * y), int(s * 0.74), int(s * y))


def _draw_clear(p, s, c):
    _pen(p, 2.2, QColor("#9aa0a6"))
    m = int(s * 0.32)
    p.drawLine(m, m, s - m, s - m)
    p.drawLine(s - m, m, m, s - m)


def _draw_translate(p, s, c):
    """翻译图标：左半「文」字形 + 右半气泡轮廓，寓意「把外文译过来」。"""
    _pen(p, 1.8, _ACCENT)
    # 左侧文字基线与横竖（抽象的"文"字）
    p.drawLine(int(s * 0.12), int(s * 0.34), int(s * 0.44), int(s * 0.34))
    p.drawLine(int(s * 0.28), int(s * 0.24), int(s * 0.28), int(s * 0.52))
    p.drawLine(int(s * 0.16), int(s * 0.52), int(s * 0.40), int(s * 0.52))
    p.drawLine(int(s * 0.20), int(s * 0.52), int(s * 0.16), int(s * 0.68))
    p.drawLine(int(s * 0.36), int(s * 0.52), int(s * 0.40), int(s * 0.68))
    # 右侧对话框
    _pen(p, 1.8)
    r = int(s * 0.30)
    cx, cy = int(s * 0.63), int(s * 0.38)
    p.drawRoundedRect(cx - r, cy - int(r * 0.75), 2 * r, int(r * 1.5), 3, 3)
    p.drawLine(cx - int(r * 0.45), cy + int(r * 0.75), cx - int(r * 0.25), cy + int(r * 1.15))
    p.drawLine(cx - int(r * 0.25), cy + int(r * 1.15), cx + int(r * 0.05), cy + int(r * 0.75))


def _draw_globe(p, s, c):
    """地球图标：外圆 + 经纬线（用于整页翻译入口）。"""
    _pen(p, 1.8, _ACCENT)
    m = int(s * 0.16)
    p.drawEllipse(m, m, s - 2 * m, s - 2 * m)
    p.drawLine(m, int(s * 0.50), s - m, int(s * 0.50))
    p.drawArc(int(s * 0.32), m, int(s * 0.36), s - 2 * m, 0, 360 * 16)


_DRAW = {
    "back": _draw_back,
    "forward": _draw_forward,
    "reload": _draw_reload,
    "stop": _draw_stop,
    "home": _draw_home,
    "newtab": _draw_newtab,
    "find": _draw_find,
    "download": _draw_download,
    "settings": _draw_settings,
    "devtools": _draw_devtools,
    "help": _draw_help,
    "bookmark": _draw_bookmark,
    "bookmark_on": _draw_bookmark_on,
    "menu": _draw_menu,
    "clear": _draw_clear,
    "translate": _draw_translate,
    "globe": _draw_globe,
}


def icon(name, size=20):
    d = _DRAW.get(name)
    if not d:
        return QIcon()
    return _new(size, d)


def win_icon_size():
    """Windows 工具栏图标尺寸规范：100% 缩放 16px，按 DPI 吸附到 16/20/24/28/32。"""
    dpr = _dpr()
    raw = 16 * dpr
    for s in (16, 20, 24, 28, 32):
        if raw <= s:
            return s
    return 32


def make_logo(size=64):
    """Yc 品牌徽标：圆角方块 + Yc 字样（高清渲染）。"""
    dpr = _dpr()
    px = QPixmap(max(1, int(size * dpr)), max(1, int(size * dpr)))
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(dpr, dpr)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(_ACCENT))
    p.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
    f = QFont()
    f.setPixelSize(int(size * 0.52))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#ffffff"))
    p.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, "Yc")
    p.end()
    ic = QIcon()
    ic.addPixmap(px, QIcon.Mode.Normal)
    return ic
