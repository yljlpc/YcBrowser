"""简约专业的浅色界面主题（QSS）。集中定义配色与控件样式，便于统一调校。"""

ACCENT = "#2f6fed"
ACCENT_SOFT = "#e8f0fe"
BG = "#eef0f3"
PANEL = "#ffffff"
PANEL_2 = "#f7f8fa"
BORDER = "#dfe3e8"
BORDER_STRONG = "#c9cfd8"
TEXT = "#20242b"
MUTED = "#7b828c"
HOVER = "#f0f3f7"

# 字体回退：优先使用随附中文字体，保证中文界面整洁。
FONT_STACK = '"方正书宋简体","仿宋_GB2312","Noto Sans CJK SC","WenQuanYi Micro Hei",sans-serif'
HEADING_STACK = '"方正小标宋简体","方正小标宋_GBK","Noto Serif CJK SC",serif'

STYLE = f"""
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: {FONT_STACK};
}}
QToolBar {{
    background: {PANEL};
    border: none;
    border-bottom: 1px solid {BORDER};
    spacing: 6px;
    padding: 5px 8px;
}}
QToolButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    color: {TEXT};
}}
QToolButton:hover {{ background: {HOVER}; }}
QToolButton:pressed {{ background: {ACCENT_SOFT}; }}
QPushButton {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 12px;
    color: {TEXT};
}}
QPushButton:hover {{ border-color: {ACCENT}; background: {HOVER}; }}
QPushButton#accent {{
    background: {ACCENT};
    border: none;
    color: #ffffff;
}}
QPushButton#accent:hover {{ background: #2a62d6; }}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid {BORDER};
    color: {TEXT};
}}
QPushButton#ghost:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; }}
QLineEdit {{
    border: 1px solid {BORDER};
    border-radius: 18px;
    padding: 6px 16px;
    background: {PANEL};
    color: {TEXT};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QTabWidget::pane {{ border: none; top: 0; }}
QTabBar::tab {{
    background: {PANEL_2};
    border: 1px solid {BORDER};
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 7px 14px;
    margin-right: 4px;
    color: {MUTED};
}}
QTabBar::tab:selected {{
    background: {PANEL};
    color: {TEXT};
    border-color: {BORDER};
    border-top: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}
QStatusBar {{
    background: {PANEL};
    border-top: 1px solid {BORDER};
    color: {MUTED};
    padding: 2px 8px;
}}
QComboBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 10px;
    background: {PANEL};
    color: {TEXT};
}}
QComboBox:hover {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {ACCENT_SOFT};
    color: {TEXT};
}}
QMenu {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    color: {TEXT};
}}
QMenu::item {{ padding: 6px 18px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
QDialog {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLabel#muted {{ color: {MUTED}; }}
QToolTip {{
    background: {TEXT};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QListWidget {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QListWidget::item {{ padding: 6px 10px; border-radius: 4px; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
"""
