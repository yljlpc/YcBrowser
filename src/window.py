"""主窗口：工具栏、地址栏、引擎切换、多标签、状态栏、查找栏、下载管理、
历史自动补全、开发者工具、快捷键帮助与分辨率自适应。

UI 完整性约束（用户明确）：功能栏的图标 + 文字 + 快捷键必须完整显示、不重叠不叠加；
图标按 Windows 工具栏尺寸规范（16/20/24/28/32，随 DPI 取档）高清渲染；
字体图标清晰；功能全面。
"""
import json
import os

from PyQt6.QtCore import QSize, Qt, QTimer, QStandardPaths, QSettings, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineDownloadRequest
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QCheckBox,
    QSizePolicy,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QToolButton,
    QWidget,
    QCompleter,
    QVBoxLayout,
    QMenu,
)

from .core_client import CoreClient
from .downloader import DownloadTask, human_size
from .download_ui import DownloadManagerDialog
from .icons import icon as _ic, make_logo, win_icon_size
from .internal import about_html, help_html, home_html
from .layout import dialog_size, looks_like_url
from .media import MEDIA_SNIFF_JS, is_stream, media_filename, parse_media_items
from .profile import get_app_profile
from .translate import (
    DEFAULT_GLOSSARY,
    EXTRACT_JS,
    FILL_JS,
    RESTORE_JS,
    TranslateClient,
)
from .version import VERSION
from .zh import zh_buttons, zh_msg_info, zh_msg_question, zh_msg_warning
from .tab import BrowserTab
from .theme import STYLE

# 渲染引擎（显示名附中文说明，便于非技术用户理解）
ENGINES = [
    ("Blink 引擎（Chromium 内核）", "blink"),
    ("WebKit 引擎（兼容模式）", "webkit"),
    ("Trident 引擎（IE 兼容）", "trident"),
]

# 搜索引擎（显示名附中文说明）
SEARCH_ENGINES = [
    ("必应（微软）", "bing"),
    ("百度", "baidu"),
    ("谷歌（Google）", "google"),
    ("DuckDuckGo（开源搜索）", "ddg"),
]

# 翻译后端（网络请求在前端发起，核心只做语言学处理）。
TRANSLATE_BACKENDS = [
    ("MyMemory（免费公开，无需密钥）", "mymemory"),
    ("谷歌翻译（公开接口）", "google"),
    ("LibreTranslate（自建或公共实例）", "libretranslate"),
    ("自定义接口（自行填写地址）", "custom"),
]

# 翻译目标语言。
TRANSLATE_TARGETS = [
    ("简体中文", "zh"),
    ("繁体中文", "zh-tw"),
    ("英语", "en"),
    ("日语", "ja"),
    ("韩语", "ko"),
    ("法语", "fr"),
    ("德语", "de"),
    ("西班牙语", "es"),
    ("俄语", "ru"),
]

# 快捷键集中定义（用于按钮 / 动作 / 帮助展示），避免重复与冲突。
SHORTCUTS = {
    "back": "Alt+Left",
    "forward": "Alt+Right",
    "reload": "F5",
    "stop": "Esc",
    "home": "Alt+Home",
    "newtab": "Ctrl+T",
    "find": "Ctrl+F",
    "downloads": "Ctrl+J",
    "devtools": "F12",
    "address": "Ctrl+L",
    "zoom_in": "Ctrl++",
    "zoom_out": "Ctrl+-",
    "zoom_reset": "Ctrl+0",
    "bookmark": "Ctrl+D",
}


def _sc_text(key):
    return QKeySequence(SHORTCUTS[key]).toString(QKeySequence.SequenceFormat.NativeText)


def _js_obj(d):
    """把 Python 字典安全地转成可注入的 JS 对象字面量。

    译文来自网络，必须转义引号/反斜杠/换行，否则会破坏页面脚本甚至注入。
    """
    return json.dumps(d, ensure_ascii=False)


class TranslateWorker(QThread):
    """后台翻译线程：网络请求绝不在 GUI 线程发起，避免界面卡死。"""

    progress = pyqtSignal(int, int)          # 已完成, 总数
    finished_ok = pyqtSignal(dict)          # {原文: 译文}
    failed = pyqtSignal(str)                 # 错误信息

    def __init__(self, client, items, source="auto", target="zh", glossary=None, parent=None):
        super().__init__(parent)
        self.client = client
        self.items = list(items)
        self.source = source
        self.target = target
        self.glossary = glossary
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            result = {}
            total = len(self.items)
            for i, item in enumerate(self.items, 1):
                if self._cancel:
                    break
                text = (item or "").strip()
                if text:
                    try:
                        result[item] = self.client.translate(text, self.source, self.target, self.glossary)
                    except Exception as exc:  # noqa: BLE001
                        result[item] = ""
                        self._last_err = str(exc)
                self.progress.emit(i, total)
                if self._cancel:
                    break
            if self._cancel:
                self.failed.emit("已取消")
            else:
                self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("设置")
        form = QFormLayout(self)

        self.engine = QComboBox()
        for label, val in ENGINES:
            self.engine.addItem(label, val)
        self.engine.setCurrentIndex(self._idx(ENGINES, settings.get("default_engine", "blink")))

        self.search = QComboBox()
        for label, val in SEARCH_ENGINES:
            self.search.addItem(label, val)
        self.search.setCurrentIndex(self._idx(SEARCH_ENGINES, settings.get("search_engine", "bing")))

        self.home = QLineEdit(settings.get("home_page", "omni://home"))

        self.font_scale = QSpinBox()
        self.font_scale.setRange(80, 200)
        self.font_scale.setSuffix("%")
        self.font_scale.setValue(int(settings.get("font_scale", 100)))

        self.adaptive = QCheckBox("根据分辨率自动调整界面与网页缩放")
        self.adaptive.setChecked(bool(settings.get("adaptive", True)))

        # —— 翻译设置 ——
        self.tr_backend = QComboBox()
        for label, val in TRANSLATE_BACKENDS:
            self.tr_backend.addItem(label, val)
        self.tr_backend.setCurrentIndex(
            self._idx(TRANSLATE_BACKENDS, settings.get("translate_backend", "mymemory"))
        )

        self.tr_target = QComboBox()
        for label, val in TRANSLATE_TARGETS:
            self.tr_target.addItem(label, val)
        self.tr_target.setCurrentIndex(
            self._idx(TRANSLATE_TARGETS, settings.get("translate_target", "zh"))
        )

        self.tr_endpoint = QLineEdit(settings.get("translate_endpoint", ""))
        self.tr_endpoint.setPlaceholderText(
            "自定义后端地址，可含 {text} {source} {target} 占位符"
        )

        self.tr_glossary = QTextEdit(settings.get("translate_glossary", ""))
        self.tr_glossary.setPlaceholderText(
            "自定义术语表，每行一条：原文,译词\n例：web browser,浏览器"
        )
        self.tr_glossary.setFixedHeight(96)

        # —— 下载设置 ——
        self.dl_connections = QSpinBox()
        self.dl_connections.setRange(1, 32)
        self.dl_connections.setSuffix(" 个连接")
        self.dl_connections.setValue(int(settings.get("download_connections", 8)))

        self.dl_speed = QSpinBox()
        self.dl_speed.setRange(0, 102400)
        self.dl_speed.setSpecialValueText("不限速")
        self.dl_speed.setSuffix(" KB/s")
        self.dl_speed.setValue(int(settings.get("download_speed_limit", 0)))

        form.addRow("默认渲染内核", self.engine)
        form.addRow("默认搜索引擎", self.search)
        form.addRow("主页 / 启动页", self.home)
        form.addRow("界面与网页缩放", self.font_scale)
        form.addRow(self.adaptive)
        form.addRow("翻译后端", self.tr_backend)
        form.addRow("翻译目标语言", self.tr_target)
        form.addRow("自定义后端地址", self.tr_endpoint)
        form.addRow("自定义术语表", self.tr_glossary)
        form.addRow("下载连接数", self.dl_connections)
        form.addRow("下载限速", self.dl_speed)

        form.addRow(zh_buttons(self, ok="确定", cancel="取消"))

    @staticmethod
    def _idx(pairs, value):
        for i, (_, v) in enumerate(pairs):
            if v == value:
                return i
        return 0

    def collect(self):
        return {
            "default_engine": self.engine.currentData(),
            "search_engine": self.search.currentData(),
            "home_page": self.home.text().strip() or "omni://home",
            "font_scale": self.font_scale.value(),
            "adaptive": self.adaptive.isChecked(),
            "translate_backend": self.tr_backend.currentData(),
            "translate_target": self.tr_target.currentData(),
            "translate_endpoint": self.tr_endpoint.text().strip(),
            "translate_glossary": self.tr_glossary.toPlainText().strip(),
            "download_connections": self.dl_connections.value(),
            "download_speed_limit": self.dl_speed.value() * 1024,
        }


class MainWindow(QMainWindow):
    def __init__(self, core: CoreClient):
        super().__init__()
        self.core = core
        self.settings = self._load_settings()
        self._ui_scale = 1.0
        self._icon_targets = []  # (obj, name, is_logo)
        self._history = self._load_history()
        self._bookmarks = self._load_bookmarks()
        self._downloads = []
        self._dl_dlg = None
        self._dl_tasks = []       # 多连接下载任务
        self._bm_dlg = None
        self._hist_dlg = None
        self._last_find = (0, 0)
        # 翻译相关
        self._tr_client = TranslateClient(core=core, backend="mymemory")
        self._tr_worker = None
        self._tr_items = []       # 提取到的原文段落
        self._tr_originals = []   # 与 _tr_items 对应的原始 nodeValue（含首尾空白）
        self._tr_active = False
        self._private_window = False   # 无痕窗口：标签使用 off-the-record profile
        # 历史记录防抖保存定时器（避免每次导航都做磁盘 IO）
        self._history_save_timer = None
        # 加载进度的上次显示台阶（避免高频重绘）
        self._last_progress = -1
        # 内部页 data URL → 可读 omni:// 地址的映射（避免地址栏显示乱码）
        self._internal_urls = {}
        self.setWindowTitle("Yc浏览器")
        self.resize(1360, 860)
        self.setStyleSheet(STYLE)
        self.setWindowIcon(make_logo(64))

        self._build_toolbar()
        self._build_findbar()
        self._build_tabs()
        self._build_statusbar()
        self._connect_screens()
        self._connect_profile()

        # 首个标签：延后到事件循环启动后再创建。
        #
        # BrowserTab 里会实例化 QWebEngineView，这一步会触发 Chromium
        # 初始化（约 1~2 秒）。若在窗口显示之前同步创建，用户从「双击图标」
        # 到「看到界面」要干等这一整段时间；改成显示窗口后再建标签，
        # 界面先出来、Chromium 在后台预热，感知延迟显著降低。
        self._first_tab = None
        QTimer.singleShot(0, self._create_first_tab)
        self.apply_ui_scale()
        self._apply_window_geometry()  # 按分辨率自动设定窗口大小并居中
        self._refresh_bookmark_state()

    def _create_first_tab(self):
        """事件循环启动后创建首个标签页并加载主页。"""
        if self._first_tab is not None:
            return
        self._first_tab = self.add_tab(None)
        self.open_internal(self._first_tab, "home")

    # ---------------- 工具栏 ----------------
    def _add_act(self, name, text, sc_key, slot):
        act = QAction(_ic(name, self._sz()), text, self)
        if sc_key:
            act.setShortcut(QKeySequence(SHORTCUTS[sc_key]))
            act.setToolTip(f"{text}（{_sc_text(sc_key)}）")
        else:
            act.setToolTip(text)
        act.triggered.connect(slot)
        self.toolbar.addAction(act)
        self._icon_targets.append((act, name, False))
        return act

    def _add_btn(self, name, text, sc_key, slot):
        b = QPushButton()
        b.setIcon(_ic(name, self._sz()))
        b.setText(text)
        if sc_key:
            b.setShortcut(QKeySequence(SHORTCUTS[sc_key]))
            b.setToolTip(f"{text}（{_sc_text(sc_key)}）")
        else:
            b.setToolTip(text)
        # 点击后立刻给一次状态栏反馈，避免"点了没反应"的错觉。
        b.clicked.connect(lambda _c=False, t=text, s=slot: self._click_feedback(t, s))
        self.toolbar.addWidget(b)
        self._icon_targets.append((b, name, False))
        return b

    def _click_feedback(self, text, slot):
        """按钮点击的即时反馈：先更新状态栏，再执行动作。

        某些动作（新建标签、打开内部页）会触发 Chromium 渲染，
        在真实桌面上可能耗时几十毫秒；若界面毫无变化，用户会以为点击无效。
        这里先写状态栏，让反馈立即可见。
        """
        self._status_label.setText(f"{text}…")
        QApplication.processEvents()
        slot()

    def _build_toolbar(self):
        tb = QToolBar("导航")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.setIconSize(QSize(self._sz(), self._sz()))
        self.toolbar = tb
        self.addToolBar(tb)

        # 品牌 Logo（仅图标，点击回主页）
        self.logo_btn = QToolButton()
        self.logo_btn.setIcon(make_logo(28))
        self.logo_btn.setToolTip("Yc浏览器")
        self.logo_btn.setAutoRaise(True)
        self.logo_btn.clicked.connect(self._go_home)
        tb.addWidget(self.logo_btn)
        self._icon_targets.append((self.logo_btn, "logo", True))
        tb.addSeparator()

        self._act_back = self._add_act("back", "后退", "back", self._on_back)
        self._act_forward = self._add_act("forward", "前进", "forward", self._on_forward)
        self._add_act("reload", "刷新", "reload", self._on_reload)
        self._add_act("stop", "停止", "stop", self._on_stop)
        self._add_act("home", "主页", "home", self._go_home)
        tb.addSeparator()

        self.engine_combo = QComboBox()
        for label, val in ENGINES:
            self.engine_combo.addItem(label, val)
        self.engine_combo.setCurrentIndex(self._idx(ENGINES, self.settings.get("default_engine", "blink")))
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        tb.addWidget(self.engine_combo)

        self.search_combo = QComboBox()
        for label, val in SEARCH_ENGINES:
            self.search_combo.addItem(label, val)
        self.search_combo.setCurrentIndex(self._idx(SEARCH_ENGINES, self.settings.get("search_engine", "bing")))
        tb.addWidget(self.search_combo)

        self.btn_new = self._add_btn("newtab", "新标签", "newtab", self._new_tab)
        self.btn_find = self._add_btn("find", "查找", "find", self._toggle_find)
        self.btn_translate = self._add_btn("translate", "翻译", None, self._translate_page)
        self.btn_download = self._add_btn("download", "下载", "downloads", self._open_downloads)
        self.btn_bookmark = self._add_btn("bookmark", "收藏", "bookmark", self._add_bookmark)
        tb.addWidget(self._build_zoom())
        tb.addSeparator()
        # 菜单（书签管理 / 历史 / 清除数据 / 关于）
        self.menu_btn = QToolButton()
        self.menu_btn.setIcon(_ic("menu", self._sz()))
        self.menu_btn.setText("菜单")
        self.menu_btn.setMenu(self._build_app_menu())
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.menu_btn.setToolTip("菜单（书签 / 历史 / 清除浏览数据 / 关于）")
        tb.addWidget(self.menu_btn)
        self._icon_targets.append((self.menu_btn, "menu", False))
        self.btn_settings = self._add_btn("settings", "设置", None, self._open_settings)
        # 说明：帮助入口并入「菜单」（☰ → 帮助 / 快捷键），不再单设工具栏按钮。</new_string>
        # F12 开发者工具
        dt_act = QAction(self)
        dt_act.setShortcut(QKeySequence(SHORTCUTS["devtools"]))
        dt_act.triggered.connect(self._open_devtools)
        self.addAction(dt_act)
        # 缩放快捷键（按钮已在 _build_zoom 内，这里提供全局快捷键）
        for _sc, _slot in (
            ("zoom_in", self._zoom_in),
            ("zoom_out", self._zoom_out),
            ("zoom_reset", self._zoom_reset),
        ):
            _a = QAction(self)
            _a.setShortcut(QKeySequence(SHORTCUTS[_sc]))
            _a.triggered.connect(_slot)
            self.addAction(_a)

        # 地址栏单独成行：与功能按钮解耦，独占一行，输入完整网址可直接前往且不弹补全。
        self.addToolBarBreak()
        self._build_addrbar()

    def _build_addrbar(self):
        bar = QToolBar("地址栏")
        bar.setMovable(False)
        bar.setIconSize(QSize(self._sz(), self._sz()))
        self.addr_bar = bar

        self.address = QLineEdit()
        self.address.setPlaceholderText("输入完整网址或搜索词，回车 / 点击「前往」打开")
        self.address.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.address.returnPressed.connect(self.navigate)
        self.address.textChanged.connect(self._on_address_text)
        self._completer = QCompleter(self._history, self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.address.setCompleter(self._completer)

        # 覆盖默认右键菜单，确保所有菜单项都是中文
        address_menu = QMenu(self)
        address_menu.addAction("复制", lambda: self.address.copy())
        address_menu.addAction("粘贴", lambda: self.address.paste())
        address_menu.addAction("剪切", lambda: self.address.cut())
        address_menu.addAction("删除", lambda: self.address.delete())
        address_menu.addAction("全选", lambda: self.address.selectAll())
        address_menu.addSeparator()
        # 如果剪贴板有 URLs，添加快捷操作
        address_menu.addAction("访问剪贴板", lambda: (self.address.setText(self._get_clipboard_url()), self.navigate()))

        self.address.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.address.customContextMenuRequested.connect(lambda pos: address_menu.exec(self.address.mapToGlobal(pos) if pos else self.address.rect().bottomLeft()))


        self.btn_go = QPushButton()
        self.btn_go.setIcon(_ic("reload", self._sz()))
        self.btn_go.setText("前往")
        self.btn_go.setToolTip("打开地址栏中的网址（回车键）")
        self.btn_go.clicked.connect(self.navigate)
        self._icon_targets.append((self.btn_go, "reload", False))

        self.btn_clear_addr = QPushButton()
        self.btn_clear_addr.setIcon(_ic("clear", self._sz()))
        self.btn_clear_addr.setText("清除")
        self.btn_clear_addr.setToolTip("清空地址栏")
        self.btn_clear_addr.clicked.connect(
            lambda: (self.address.clear(), self.address.setFocus())
        )
        self._icon_targets.append((self.btn_clear_addr, "stop", False))

        bar.addWidget(self.address)
        bar.addWidget(self.btn_go)
        bar.addWidget(self.btn_clear_addr)

        # Ctrl+L 聚焦地址栏（标准快捷键）
        focus_act = QAction(self)
        focus_act.setShortcut(QKeySequence(SHORTCUTS["address"]))
        focus_act.triggered.connect(lambda: self.address.setFocus())
        self.addAction(focus_act)

        self.addToolBar(bar)

    @staticmethod
    def _looks_like_url(text):
        """判断是否为「完整网址」：带协议，或省略协议但形如 host.tld[/...]。"""
        return looks_like_url(text)

    def _on_address_text(self, text):
        # 完整网址：直接可前往，不显示历史 / 搜索补全下拉，避免遮挡与误选。
        if self._looks_like_url(text.strip()):
            self._completer.popup().hide()
            if self.address.completer() is not None:
                self.address.setCompleter(None)
        else:
            if self.address.completer() is None:
                self.address.setCompleter(self._completer)

    def _sz(self):
        return win_icon_size()

    # ---------------- 缩放控件 ----------------
    def _build_zoom(self):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        self.zoom_out_btn = QPushButton("−")
        self.zoom_reset_btn = QPushButton("100%")
        self.zoom_in_btn = QPushButton("+")
        for b in (self.zoom_out_btn, self.zoom_reset_btn, self.zoom_in_btn):
            b.setObjectName("zoombtn")
        self.zoom_out_btn.setToolTip(f"缩小（{_sc_text('zoom_out')}）")
        self.zoom_in_btn.setToolTip(f"放大（{_sc_text('zoom_in')}）")
        self.zoom_reset_btn.setToolTip(f"重置缩放（{_sc_text('zoom_reset')}）")
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        self.zoom_reset_btn.clicked.connect(self._zoom_reset)
        h.addWidget(self.zoom_out_btn)
        h.addWidget(self.zoom_reset_btn)
        h.addWidget(self.zoom_in_btn)
        return w

    # ---------------- 应用菜单 ----------------
    def _build_app_menu(self):
        m = QMenu(self)
        a = m.addAction(_ic("bookmark", 16), "书签管理…")
        a.triggered.connect(self._open_bookmarks)
        a = m.addAction("历史记录…")
        a.triggered.connect(self._open_history)
        a = m.addAction(_ic("translate", 16), "翻译此页为中文…")
        a.triggered.connect(self._translate_page)
        a = m.addAction("还原页面原文")
        a.triggered.connect(self._restore_original)
        a = m.addAction(_ic("download", 16), "下载页面媒体…")
        a.triggered.connect(self._open_media_downloader)
        a = m.addAction("清除浏览数据…")
        a.triggered.connect(self._clear_data)
        m.addSeparator()
        a = m.addAction("新建无痕窗口")
        a.triggered.connect(self._new_private_window)
        a = m.addAction("打印当前页面…")
        a.triggered.connect(self._print_page)
        a = m.addAction("导出为 PDF…")
        a.triggered.connect(self._export_pdf)
        m.addSeparator()
        a = m.addAction(_ic("settings", 16), "设置…")
        a.triggered.connect(self._open_settings)
        a = m.addAction(_ic("help", 16), "帮助 / 快捷键")
        a.triggered.connect(self._open_help)
        a = m.addAction("关于 Yc浏览器")
        a.triggered.connect(lambda: self.open_internal(self._cur() or self.add_tab("omni://home"), "about"))
        return m

    def _open_menu(self):
        self.menu_btn.menu().popup(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    # ---------------- 无痕 / 打印 ----------------
    def _new_private_window(self):
        """新建无痕窗口：独立 off-the-record profile，不写磁盘缓存与 Cookie。"""
        w = MainWindow(self.core)
        w.setWindowTitle("Yc浏览器（无痕）")
        w._private_window = True
        w.add_tab("omni://home", private=True)
        w.apply_ui_scale()
        w._apply_window_geometry()
        w.show()
        self._status_label.setText("已打开无痕窗口")
        return w

    def _print_page(self):
        """打印当前页面（调用系统打印对话框）。"""
        cur = self._cur()
        if cur is None:
            self._status_label.setText("没有可打印的页面")
            return
        try:
            cur.print_preview(self)
        except Exception as exc:  # noqa: BLE001
            zh_msg_warning(self, "打印失败", f"无法打开打印对话框：{exc}")

    def _export_pdf(self):
        """把当前页面导出为 PDF 文件。"""
        cur = self._cur()
        if cur is None:
            self._status_label.setText("没有可导出的页面")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("导出为 PDF")
        dlg.resize(self._dialog_size(0.32, 0.3, 480, 300, 380, 240))
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("选择 PDF 保存位置："))
        name = QLineEdit("页面.pdf")
        lay.addWidget(name)
        row = QHBoxLayout()
        b_ok = QPushButton("导出")
        b_ok.setObjectName("accent")
        b_ok.clicked.connect(dlg.accept)
        b_cancel = QPushButton("取消")
        b_cancel.clicked.connect(dlg.reject)
        row.addWidget(b_ok)
        row.addWidget(b_cancel)
        row.addStretch(1)
        lay.addLayout(row)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        fname = name.text().strip() or "页面.pdf"
        if not fname.lower().endswith(".pdf"):
            fname += ".pdf"
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        if not base:
            base = os.path.expanduser("~")
        path = os.path.join(base, os.path.basename(fname))
        self._status_label.setText("正在导出 PDF…")

        def done(p, err):
            if err:
                self._status_label.setText(f"导出失败：{err}")
                zh_msg_warning(self, "导出失败", str(err))
            else:
                self._status_label.setText(f"已导出：{p}")
                zh_msg_info(self, "导出完成", f"已保存到：\n{p}")

        cur.print_to_pdf(path, done)

    # ---------------- 页面翻译 ----------------
    def _translate_page(self):
        """整页翻译：提取正文段落 → 后台翻译 → 回填译文。

        流程刻意分三步：
        1. JS 提取可见文本节点（跳过代码/脚本/输入框），得到待译段落；
        2. 后台线程逐句送译（网络请求不阻塞 GUI），进度实时反馈到状态栏；
        3. 译文按段落回填 DOM，同时保存原文，便于「还原页面原文」。
        """
        cur = self._cur()
        if cur is None:
            self._status_label.setText("没有可翻译的页面")
            return
        if self._tr_active:
            self._status_label.setText("翻译进行中…")
            return
        url = cur.view.page().url().toString()
        if url.startswith(("omni://", "about:", "data:")):
            self._status_label.setText("内部页面无需翻译")
            return
        self._tr_active = True
        self._status_label.setText("正在提取页面内容…")
        cur.view.page().runJavaScript(EXTRACT_JS, self._on_extract_done)

    def _on_extract_done(self, items):
        if not isinstance(items, list) or not items:
            self._tr_active = False
            self._status_label.setText("未找到可翻译的文本")
            return
        # 过滤：已是中文/纯代码/URL 的段落不送译
        todo = []
        for it in items:
            if not isinstance(it, str):
                continue
            t = it.strip()
            if len(t) < 2:
                continue
            if self._tr_client.should_translate(t, "zh"):
                todo.append(it)
        if not todo:
            self._tr_active = False
            self._status_label.setText("页面已是中文，无需翻译")
            return
        self._tr_items = todo
        total = len(todo)
        self._status_label.setText(f"正在翻译 0/{total} …")
        self._tr_worker = TranslateWorker(
            self._tr_client, todo, "auto", "zh", self._glossary_spec(), self
        )
        self._tr_worker.progress.connect(self._on_tr_progress)
        self._tr_worker.finished_ok.connect(self._on_tr_done)
        self._tr_worker.failed.connect(self._on_tr_failed)
        self._tr_worker.start()

    def _on_tr_progress(self, done, total):
        self._status_label.setText(f"正在翻译 {done}/{total} …")

    def _on_tr_done(self, result):
        self._tr_active = False
        pairs = {}
        for src, dst in result.items():
            if dst:
                pairs[src] = dst
        if not pairs:
            self._status_label.setText("翻译失败：后端未返回有效译文")
            return
        cur = self._cur()
        if cur is None:
            return
        js = FILL_JS.replace("__PAIRS__", _js_obj(pairs))
        cur.view.page().runJavaScript(js, self._on_fill_done)

    def _on_fill_done(self, applied):
        n = applied if isinstance(applied, int) else 0
        self._status_label.setText(f"翻译完成：已替换 {n} 段（菜单可「还原页面原文」）")
        self._set_translate_button_state(True)

    def _on_tr_failed(self, msg):
        self._tr_active = False
        self._status_label.setText(f"翻译失败：{msg}")

    def _restore_original(self):
        """把已翻译的页面还原为原文。"""
        cur = self._cur()
        if cur is None:
            return
        cur.view.page().runJavaScript(RESTORE_JS, self._on_restore_done)

    def _on_restore_done(self, n):
        cnt = n if isinstance(n, int) else 0
        self._status_label.setText(
            f"已还原 {cnt} 段原文" if cnt else "当前页面没有已翻译的内容"
        )
        self._set_translate_button_state(False)

    def _set_translate_button_state(self, translated):
        if getattr(self, "btn_translate", None):
            self.btn_translate.setText("还原原文" if translated else "翻译")
            self.btn_translate.setToolTip(
                "把页面正文翻译成中文" if not translated else "把页面还原为原文"
            )

    def _glossary_spec(self):
        """术语表：默认表 + 用户自定义（设置中维护），格式「原词,译词」每行一条。"""
        spec = DEFAULT_GLOSSARY
        custom = str(self.settings.get("translate_glossary", "") or "")
        if custom.strip():
            spec = spec + "\n" + custom
        return spec

    # ---------------- 页面媒体下载 ----------------
    def _open_media_downloader(self):
        """嗅探当前页面的视频/音频直链，列出后交给多连接下载引擎。"""
        cur = self._cur()
        if cur is None:
            self._status_label.setText("没有可嗅探的页面")
            return
        url = cur.view.page().url().toString()
        if url.startswith(("omni://", "about:", "data:")):
            self._status_label.setText("内部页面没有媒体资源")
            return
        self._status_label.setText("正在嗅探页面媒体…")
        cur.view.page().runJavaScript(MEDIA_SNIFF_JS, self._on_media_sniffed)

    def _on_media_sniffed(self, raw):
        items = parse_media_items(raw)
        # 嗅探脚本返回的是 store 对象，真正的列表在 items 字段
        if isinstance(raw, dict):
            items = parse_media_items(raw.get("items"))
        if not items:
            self._status_label.setText("未发现可下载的媒体（播放视频后再试）")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("下载页面媒体")
        dlg.resize(self._dialog_size(0.42, 0.55, 720, 520))
        lay = QVBoxLayout(dlg)
        hint = QLabel("选择要下载的媒体文件（多连接分片下载，支持断点续传）：")
        hint.setObjectName("muted")
        lay.addWidget(hint)
        lst = QListWidget()
        lay.addWidget(lst)
        for kind, murl, ext, label in items:
            tag = {"video": "视频", "audio": "音频", "stream": "流媒体"}.get(kind, "其他")
            name = media_filename(murl, kind, ext, label)
            note = f"[{tag}] {name}"
            if is_stream(kind):
                note += "（流媒体，需外部合并工具）"
            it = QListWidgetItem(note)
            it.setData(Qt.ItemDataRole.UserRole, (murl, name, kind))
            it.setToolTip(murl)
            lst.addItem(it)
        row = QHBoxLayout()
        b_dl = QPushButton("下载")
        b_dl.setObjectName("accent")
        b_dl.clicked.connect(lambda: self._download_media(lst, dlg))
        b_close = QPushButton("关闭")
        b_close.clicked.connect(dlg.accept)
        row.addWidget(b_dl)
        row.addWidget(b_close)
        row.addStretch(1)
        lay.addLayout(row)
        dlg.exec()

    def _download_media(self, lst, dlg):
        it = lst.currentItem()
        if it is None:
            if lst.count():
                it = lst.item(0)
            else:
                return
        murl, name, kind = it.data(Qt.ItemDataRole.UserRole)
        if is_stream(kind):
            zh_msg_info(
                self, "无法直接下载",
                "这是流媒体（HLS/DASH）地址，需要外部合并工具处理。\n"
                "可改用浏览器自身的下载，或复制地址到专业工具。",
            )
            return
        dldir = self._download_dir()
        category = self._dl_category(name)
        if category and category != "其他":
            cat_dir = os.path.join(dldir, category)
            os.makedirs(cat_dir, exist_ok=True)
            dldir = cat_dir
        task = DownloadTask(
            url=murl,
            dest_dir=dldir,
            filename=name,
            connections=int(self.settings.get("download_connections", 8)),
            referer=self._cur().view.page().url().toString() if self._cur() else "",
            on_state=self._on_dl_state,
        )
        try:
            task.probe()
        except Exception as exc:  # noqa: BLE001
            zh_msg_warning(self, "下载失败", f"无法探测该媒体：{exc}")
            return
        self._dl_tasks.append(task)
        self._status_label.setText(f"开始下载媒体：{task.filename}")
        task.start()
        dlg.accept()
        self._open_downloads()

    # ---------------- 查找栏 ----------------
    def _build_findbar(self):
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(6)
        h.addWidget(QLabel("查找:"))
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("输入关键字，回车查找下一处")
        self.find_edit.returnPressed.connect(lambda: self._find_do(False))
        h.addWidget(self.find_edit, 1)
        self.btn_find_prev = QPushButton("上一个")
        self.btn_find_next = QPushButton("下一个")
        self.btn_find_close = QPushButton("✕")
        self.btn_find_prev.setObjectName("ghost")
        self.btn_find_next.setObjectName("accent")
        self.btn_find_prev.clicked.connect(lambda: self._find_do(True))
        self.btn_find_next.clicked.connect(lambda: self._find_do(False))
        self.btn_find_close.clicked.connect(self._close_find)
        h.addWidget(self.btn_find_prev)
        h.addWidget(self.btn_find_next)
        h.addWidget(self.btn_find_close)
        self.find_label = QLabel("")
        self.find_label.setObjectName("muted")
        h.addWidget(self.find_label)
        self.find_bar = bar
        self.find_bar.setVisible(False)

    def _toggle_find(self):
        if self.find_bar.isVisible():
            self._close_find()
        else:
            self.find_bar.setVisible(True)
            self.find_edit.setFocus()
            self.find_edit.selectAll()

    def _close_find(self):
        self.find_bar.setVisible(False)
        self._find_do_clear()

    def _find_do(self, backward):
        tab = self._cur()
        text = self.find_edit.text()
        if tab and text:
            tab.find(text, backward)
        self._find_status()

    def _find_do_clear(self):
        tab = self._cur()
        if tab:
            tab.find("", False)
        self._last_find = (0, 0)
        self._find_status()

    def _on_find_result(self, tab, n, a):
        self._last_find = (n, a)
        self._find_status()

    def _find_status(self):
        n, a = self._last_find
        if self.find_edit.text():
            self.find_label.setText(f"{a}/{n}")
        else:
            self.find_label.setText("")

    # ---------------- 标签管理 ----------------
    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_current_changed)
        # 标签页右键菜单：复制地址 / 在新标签打开 / 关闭其他 / 关闭右侧
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self._on_tab_context_menu)

        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.find_bar)
        v.addWidget(self.tabs)
        self.setCentralWidget(container)

    def _build_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self._status_label = QLabel("就绪")
        self._status_label.setObjectName("muted")
        self.statusbar.addWidget(self._status_label, 1)
        self._zoom_label = QLabel("")
        self.statusbar.addPermanentWidget(self._zoom_label)

    def closeEvent(self, event):
        """关闭窗口：把防抖期内尚未落盘的历史立即写入。"""
        try:
            if self._history_save_timer is not None and self._history_save_timer.isActive():
                self._history_save_timer.stop()
                self._save_history()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)

    def _new_tab(self):
        """「新标签」按钮的处理。

        性能：新建标签要创建一个 QWebEngineView（约 40ms，是最慢的操作）。
        若当前标签停在自己的内部主页（空白状态），直接复用它并刷新，
        既省去一次渲染进程创建，又符合"回到空白页"的直觉。
        """
        cur = self._cur()
        if cur is not None and getattr(cur, "_internal_page", "") == "omni://home":
            # 复用当前空白标签：重新渲染主页即可
            self.open_internal(cur, "home")
            self.tabs.setCurrentIndex(self.tabs.currentIndex())
            return cur
        return self.add_tab("omni://home")

    def add_tab(self, target, html=None, private=False):
        # 无痕窗口内的标签一律使用私有 profile
        if private or self._private_window:
            private = True
        tab = BrowserTab(self.core, self, private=private)
        engine = self.engine_combo.currentData() or "blink"
        doc_mode = "ie11" if engine == "trident" else "edge"
        # 默认内核（blink/edge）无需每次都向核心请求，直接用共享 profile，提速。
        if engine != "blink" or doc_mode != "edge":
            tab.set_engine(engine, doc_mode)
        tab.apply_ui_scale(self._ui_scale)

        idx = self.tabs.addTab(tab, "新标签页")
        self.tabs.setCurrentIndex(idx)

        tab.title_changed.connect(lambda t, _tab=tab: self._on_title(_tab, t))
        tab.icon_changed.connect(lambda ic, _tab=tab: self._on_icon(_tab, ic))
        tab.url_changed.connect(lambda u, _tab=tab: self._on_url(_tab, u))
        tab.load_progress.connect(self._on_progress)
        tab.open_internal.connect(lambda name, _tab=tab: self.open_internal(_tab, name))
        tab.find_result.connect(lambda n, a, _tab=tab: self._on_find_result(_tab, n, a))

        if html is not None:
            tab.set_html(html)
        elif target and target.startswith("omni://"):
            self.open_internal(tab, target[len("omni://"):] or "home")
        elif target:
            tab.load_url(target)
        return tab

    def close_tab(self, idx):
        if self.tabs.count() <= 1:
            return
        widget = self.tabs.widget(idx)
        self.tabs.removeTab(idx)
        if widget:
            widget.deleteLater()

    def _on_tab_context_menu(self, pos):
        """标签页右键菜单。"""
        idx = self.tabs.tabBar().tabAt(pos)
        if idx < 0:
            return
        widget = self.tabs.widget(idx)
        m = QMenu(self)
        url = ""
        if isinstance(widget, BrowserTab):
            try:
                url = widget.view.page().url().toString()
            except Exception:  # noqa: BLE001
                url = ""
        a = m.addAction("复制标签页地址")
        a.setEnabled(bool(url))
        a.triggered.connect(lambda: self._copy_to_clipboard(url))
        a = m.addAction("在新标签中打开")
        a.setEnabled(bool(url) and not url.startswith(("omni://", "about:", "data:")))
        a.triggered.connect(lambda: self.add_tab(url))
        m.addSeparator()
        a = m.addAction("刷新标签页")
        a.triggered.connect(lambda: self._reload_tab(idx))
        a = m.addAction("关闭标签页")
        a.triggered.connect(lambda: self.close_tab(idx))
        a = m.addAction("关闭其他标签页")
        a.triggered.connect(lambda: self._close_other_tabs(idx))
        a = m.addAction("关闭右侧标签页")
        a.triggered.connect(lambda: self._close_right_tabs(idx))
        m.exec(self.tabs.tabBar().mapToGlobal(pos))

    def _copy_to_clipboard(self, text):
        if not text:
            return
        QApplication.clipboard().setText(text)
        self._status_label.setText("已复制到剪贴板")

    def _get_clipboard_url(self):
        """获取剪贴板中的URL，如果可行就直接使用。"""
        text = QApplication.clipboard().text()
        if looks_like_url(text):
            return text
        return ""

    def _reload_tab(self, idx):
        w = self.tabs.widget(idx)
        if isinstance(w, BrowserTab):
            w.reload()

    def _close_other_tabs(self, keep_idx):
        for i in range(self.tabs.count() - 1, -1, -1):
            if i != keep_idx:
                self.close_tab(i)

    def _close_right_tabs(self, idx):
        for i in range(self.tabs.count() - 1, idx, -1):
            self.close_tab(i)

    def _cur(self):
        w = self.tabs.currentWidget()
        return w if isinstance(w, BrowserTab) else None

    # ---------------- 信号处理 ----------------
    def _on_title(self, tab, title):
        idx = self.tabs.indexOf(tab)
        if idx >= 0:
            self.tabs.setTabText(idx, (title or "新标签页")[:24])

    def _on_icon(self, tab, icon):
        idx = self.tabs.indexOf(tab)
        if idx >= 0 and not icon.isNull():
            self.tabs.setTabIcon(idx, icon)

    def _on_url(self, tab, url):
        if tab is self._cur():
            self.address.setText(self._display_url(url))
        self._push_history(url.toString())
        self._refresh_bookmark_state()

    def _display_url(self, url):
        """地址栏显示用的 URL。

        内部页（主页 / 关于）由 setHtml 渲染，Qt 会生成一段很长的
        百分号编码 data: URL，直接显示会让地址栏被乱码撑满。
        内部页在标签上有标记，据此显示为可读的 omni:// 地址。
        """
        s = url.toString() if hasattr(url, "toString") else str(url)
        cur = self._cur()
        if cur is not None and getattr(cur, "_internal_page", None):
            return cur._internal_page
        if s.startswith("data:"):
            return s if len(s) <= 120 else s[:117] + "…"
        return s

    def _on_progress(self, value):
        """加载进度回调。

        性能：加载进度信号触发频繁（每几个百分点一次），每次都更新状态栏
        会造成不必要的重绘。这里按 10% 粒度更新，加载完成时必更新。
        """
        if value >= 100:
            self._status_label.setText("就绪")
            self._sync_nav_buttons()
            self._last_progress = -1
            return
        # 只在跨过 10% 台阶时更新，避免高频重绘
        step = (value // 10) * 10
        if step != self._last_progress:
            self._last_progress = step
            self._status_label.setText(f"加载中… {value}%")
        self._sync_nav_buttons()

    def _on_current_changed(self, _idx):
        self._sync_nav_buttons()
        cur = self._cur()
        if cur:
            self.address.setText(self._display_url(cur.view.page().url()))

    def _sync_nav_buttons(self):
        cur = self._cur()
        self._act_back.setEnabled(bool(cur and cur.can_go_back()))
        self._act_forward.setEnabled(bool(cur and cur.can_go_forward()))

    def _on_engine_changed(self, _i):
        engine = self.engine_combo.currentData()
        doc_mode = "ie11" if engine == "trident" else "edge"
        cur = self._cur()
        if cur:
            cur.set_engine(engine, doc_mode)
            cur.reload()

    # ---------------- 导航 ----------------
    def navigate(self):
        text = self.address.text().strip()
        if not text:
            return
        engine = self.search_combo.currentData() or "bing"
        # 立即给出反馈，缩短“输入后反应”的等待感。
        self._status_label.setText("正在打开…")
        cur = self._cur()
        if cur is None:
            cur = self.add_tab(None)
        res = self.core.resolve_nav(text, engine)
        if isinstance(res, dict) and res.get("ok") is False:
            self._status_label.setText(f"解析失败：{res.get('error', '')}")
            return
        url = res.get("url", "") if isinstance(res, dict) else ""
        if url:
            cur.load_url(url)

    def _on_back(self):
        cur = self._cur()
        if cur:
            cur.back()

    def _on_forward(self):
        cur = self._cur()
        if cur:
            cur.forward()

    def _on_reload(self):
        cur = self._cur()
        if cur:
            cur.reload()

    def _on_stop(self):
        cur = self._cur()
        if cur:
            cur.stop()

    def _go_home(self):
        cur = self._cur()
        if cur:
            self.open_internal(cur, "home")

    def open_internal(self, tab, name):
        """渲染内部页（主页 / 关于）。

        内部页用 setHtml 加载，Qt 会生成一段很长的百分号编码 data: URL，
        若直接显示到地址栏会出现乱码。故在标签上打内部页标记，
        显示地址时替换为可读的 omni:// 地址。
        """
        if name == "about":
            html = about_html()
            friendly = "omni://about"
        else:
            engine_label = self.engine_combo.currentText()
            html = home_html(engine_label)
            friendly = "omni://home"
        tab.set_html(html)
        tab._internal_page = friendly
        if tab is self._cur():
            self.address.setText(friendly)

    # ---------------- 下载 ----------------
    def _connect_profile(self):
        prof = get_app_profile()
        try:
            prof.downloadRequested.connect(self._on_download)
        except Exception:  # noqa: BLE001
            pass

    def _download_dir(self):
        d = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if not d:
            d = os.path.expanduser("~/Downloads")
        os.makedirs(d, exist_ok=True)
        return d

    def _on_download(self, dl: QWebEngineDownloadRequest):
        """接管 WebEngine 的下载请求。

        交给多连接分片引擎处理（SwiftDL 移植版）：多连接并发、可续传、可暂停。
        若引擎不可用（探测失败等），退回 WebEngine 自带的下载，保证功能不缺失。
        """
        url = dl.url().toString()
        dldir = self._download_dir()
        name = dl.suggestedFileName() or "download.bin"
        # 分类目录：视频/音乐/程序/压缩包/文档
        category = self._dl_category(name)
        if category and category != "其他":
            cat_dir = os.path.join(dldir, category)
            os.makedirs(cat_dir, exist_ok=True)
            dldir = cat_dir

        try:
            task = DownloadTask(
                url=url,
                dest_dir=dldir,
                filename=name,
                connections=int(self.settings.get("download_connections", 8)),
                referer=self._cur().view.page().url().toString() if self._cur() else "",
                speed_limit=int(self.settings.get("download_speed_limit", 0)),
                on_state=self._on_dl_state,
            )
            task.probe()
        except Exception as exc:  # noqa: BLE001
            # 探测失败 → 退回 Qt 原生下载，功能不缺失
            self._downloads.append(dl)
            dl.setDownloadPath(os.path.join(dldir, name))
            dl.accept()
            dl.stateChanged.connect(lambda _s, d=dl: self._refresh_downloads())
            self._status_label.setText(f"已改用内置下载：{name}（{exc}）")
            self._refresh_downloads()
            return

        self._dl_tasks.append(task)
        self._status_label.setText(
            f"开始下载：{task.filename}（{task.connections} 线程，"
            f"{'可续传' if task.resumable else '单线程'}，{human_size(task.total)}）"
        )
        task.start()
        self._open_downloads()

    @staticmethod
    def _dl_category(filename):
        """按扩展名归类（与核心 classify_file 规则一致）。"""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return {
            "mp4": "视频", "mkv": "视频", "avi": "视频", "mov": "视频", "webm": "视频",
            "flv": "视频", "wmv": "视频", "m4v": "视频", "mpg": "视频", "mpeg": "视频",
            "mp3": "音乐", "flac": "音乐", "wav": "音乐", "aac": "音乐", "ogg": "音乐",
            "m4a": "音乐", "wma": "音乐", "ape": "音乐",
            "exe": "程序", "msi": "程序", "deb": "程序", "rpm": "程序", "apk": "程序",
            "dmg": "程序", "pkg": "程序", "appimage": "程序", "run": "程序", "sh": "程序",
            "zip": "压缩包", "rar": "压缩包", "7z": "压缩包", "tar": "压缩包",
            "gz": "压缩包", "bz2": "压缩包", "xz": "压缩包", "zst": "压缩包", "iso": "压缩包",
            "pdf": "文档", "doc": "文档", "docx": "文档", "xls": "文档", "xlsx": "文档",
            "ppt": "文档", "pptx": "文档", "txt": "文档", "md": "文档", "epub": "文档",
        }.get(ext, "其他")

    def _on_dl_state(self, task, state):
        if state == "completed":
            self._status_label.setText(f"下载完成：{task.filename}")
        elif state == "failed":
            self._status_label.setText(f"下载失败：{task.filename} — {task.error}")
        if self._dl_dlg:
            self._dl_dlg.refresh()

    def _open_downloads(self):
        if self._dl_dlg is None:
            self._dl_dlg = DownloadManagerDialog(self)
            # 五列（文件/状态/大小/进度/速度）需要足够宽度，默认给 880
            self._dl_dlg.setMinimumSize(self._dialog_size(0.48, 0.55, 880, 560, 640, 380))
            self._dl_dlg.resize(self._dialog_size(0.48, 0.55, 880, 560, 640, 380))
        for t in self._dl_tasks:
            if not any(id(t) == k for k in self._dl_dlg._rows):
                self._dl_dlg.add_task(t)
        self._dl_dlg.show()
        self._dl_dlg.raise_()

    def _refresh_downloads(self):
        if self._dl_dlg is None:
            return
        self._dl_dlg.refresh()

    # ---------------- 开发者工具 ----------------
    def _open_devtools(self):
        tab = self._cur()
        if not tab:
            return
        if tab._devtools_view is None:
            dt_page = QWebEnginePage(get_app_profile(), self)
            tab.page.setDevToolsPage(dt_page)
            view = QWebEngineView()
            view.setPage(dt_page)
            dlg = QDialog(self)
            dlg.setWindowTitle("开发者工具")
            dlg.resize(self._dialog_size(0.7, 0.75, 1100, 820, 640, 420))
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(view)
            dlg.finished.connect(lambda _, t=tab: t.page.setDevToolsPage(None) if t.page else None)
            tab._devtools_view = dlg
        tab._devtools_view.show()
        tab._devtools_view.raise_()

    # ---------------- 书签 ----------------
    def _current_nav(self):
        cur = self._cur()
        if not cur:
            return None, None
        try:
            url = cur.view.page().url().toString()
            title = cur.view.page().title() or url
        except Exception:  # noqa: BLE001
            return None, None
        return url, title

    def _is_bookmarked(self, url):
        return bool(url) and any(b.get("url") == url for b in self._bookmarks)

    def _add_bookmark(self):
        url, title = self._current_nav()
        if not url or url.startswith(("omni://", "data:", "about:")):
            self._status_label.setText("当前页面不支持收藏")
            return
        if self._is_bookmarked(url):
            self._bookmarks = [b for b in self._bookmarks if b.get("url") != url]
            self._status_label.setText("已取消收藏")
        else:
            self._bookmarks.insert(0, {"title": title or url, "url": url})
            self._status_label.setText("已加入收藏")
        self._save_bookmarks()
        self._refresh_bookmark_state()

    def _refresh_bookmark_state(self):
        url, _ = self._current_nav()
        on = bool(url) and self._is_bookmarked(url)
        if getattr(self, "btn_bookmark", None):
            self.btn_bookmark.setIcon(_ic("bookmark_on" if on else "bookmark", self._sz()))
            self.btn_bookmark.setText("已收藏" if on else "收藏")
            self.btn_bookmark.setToolTip(
                f"取消收藏（{_sc_text('bookmark')}）" if on else f"加入收藏（{_sc_text('bookmark')}）"
            )

    def _open_bookmarks(self):
        if self._bm_dlg is None:
            self._bm_dlg = QDialog(self)
            self._bm_dlg.setWindowTitle("书签管理")
            self._bm_dlg.resize(self._dialog_size(0.42, 0.55, 720, 560))
            lay = QVBoxLayout(self._bm_dlg)
            self._bm_list = QListWidget()
            self._bm_list.itemDoubleClicked.connect(lambda _i: self._open_bookmark_item())
            lay.addWidget(self._bm_list)
            row = QHBoxLayout()
            b_open = QPushButton("打开")
            b_del = QPushButton("删除")
            b_clr = QPushButton("清空")
            b_open.setObjectName("accent")
            b_open.clicked.connect(self._open_bookmark_item)
            b_del.clicked.connect(self._delete_bookmark_item)
            b_clr.clicked.connect(self._clear_bookmarks)
            row.addWidget(b_open)
            row.addWidget(b_del)
            row.addWidget(b_clr)
            row.addStretch(1)
            lay.addLayout(row)
        self._refresh_bookmarks()
        self._bm_dlg.show()
        self._bm_dlg.raise_()

    def _refresh_bookmarks(self):
        if self._bm_dlg is None:
            return
        self._bm_list.clear()
        for b in self._bookmarks:
            it = QListWidgetItem(f"{b.get('title', '')}  ·  {b.get('url', '')}")
            it.setData(Qt.ItemDataRole.UserRole, b.get("url"))
            self._bm_list.addItem(it)

    def _open_bookmark_item(self):
        it = self._bm_list.currentItem() if self._bm_list else None
        if not it:
            return
        url = it.data(Qt.ItemDataRole.UserRole)
        cur = self._cur() or self.add_tab(None)
        cur.load_url(url)
        if self._bm_dlg:
            self._bm_dlg.hide()

    def _delete_bookmark_item(self):
        it = self._bm_list.currentItem() if self._bm_list else None
        if not it:
            return
        url = it.data(Qt.ItemDataRole.UserRole)
        self._bookmarks = [b for b in self._bookmarks if b.get("url") != url]
        self._save_bookmarks()
        self._refresh_bookmarks()
        self._refresh_bookmark_state()

    def _clear_bookmarks(self):
        if not self._bookmarks:
            return
        if not zh_msg_question(self, "清空书签", "确定清空所有书签？此操作不可撤销。"):
            return
        self._bookmarks = []
        self._save_bookmarks()
        self._refresh_bookmarks()
        self._refresh_bookmark_state()

    # ---------------- 缩放 ----------------
    def _zoom_in(self):
        self._zoom_by(1.1)

    def _zoom_out(self):
        self._zoom_by(1 / 1.1)

    def _zoom_reset(self):
        cur = self._cur()
        if cur:
            cur.set_user_zoom(1.0)
        self._update_zoom_label()

    def _zoom_by(self, factor):
        cur = self._cur()
        if not cur:
            return
        z = max(0.25, min(cur._user_zoom * factor, 5.0))
        cur.set_user_zoom(z)
        self._update_zoom_label()

    def _update_zoom_label(self):
        cur = self._cur()
        eff = (cur._user_zoom if cur else 1.0) * self._ui_scale
        self._zoom_label.setText(f"缩放 {eff * 100:.0f}%")
        if cur and getattr(self, "zoom_reset_btn", None):
            self.zoom_reset_btn.setText(f"{int(round(cur._user_zoom * 100))}%")

    # ---------------- 历史管理 ----------------
    def _open_history(self):
        if self._hist_dlg is None:
            self._hist_dlg = QDialog(self)
            self._hist_dlg.setWindowTitle("历史记录")
            self._hist_dlg.resize(self._dialog_size(0.42, 0.55, 720, 560))
            lay = QVBoxLayout(self._hist_dlg)
            self._hist_list = QListWidget()
            self._hist_list.itemDoubleClicked.connect(lambda _i: self._open_history_item())
            lay.addWidget(self._hist_list)
            row = QHBoxLayout()
            b_open = QPushButton("打开")
            b_del = QPushButton("删除")
            b_clr = QPushButton("清空")
            b_open.setObjectName("accent")
            b_open.clicked.connect(self._open_history_item)
            b_del.clicked.connect(self._delete_history_item)
            b_clr.clicked.connect(self._clear_history)
            row.addWidget(b_open)
            row.addWidget(b_del)
            row.addWidget(b_clr)
            row.addStretch(1)
            lay.addLayout(row)
        self._refresh_history()
        self._hist_dlg.show()
        self._hist_dlg.raise_()

    def _refresh_history(self):
        if self._hist_dlg is None:
            return
        self._hist_list.clear()
        for u in self._history:
            self._hist_list.addItem(u)

    def _open_history_item(self):
        it = self._hist_list.currentItem() if self._hist_list else None
        if not it:
            return
        url = it.text()
        cur = self._cur() or self.add_tab(None)
        cur.load_url(url)
        if self._hist_dlg:
            self._hist_dlg.hide()

    def _delete_history_item(self):
        it = self._hist_list.currentItem() if self._hist_list else None
        if not it:
            return
        u = it.text()
        if u in self._history:
            self._history.remove(u)
        self._completer.model().setStringList(self._history)
        self._save_history()
        self._refresh_history()

    def _clear_history(self):
        if not self._history:
            return
        if not zh_msg_question(self, "清空历史", "确定清空浏览历史？此操作不可撤销。"):
            return
        self._history = []
        self._completer.model().setStringList(self._history)
        self._save_history()
        self._refresh_history()

    # ---------------- 清除浏览数据 ----------------
    def _clear_data(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("清除浏览数据")
        dlg.resize(self._dialog_size(0.32, 0.42, 480, 380, 380, 280))
        lay = QVBoxLayout(dlg)
        self._cd_cache = QCheckBox("浏览缓存（HTTP 缓存）")
        self._cd_cookies = QCheckBox("Cookie 与网站数据")
        self._cd_history = QCheckBox("浏览历史")
        self._cd_visited = QCheckBox("已访问链接")
        self._cd_cache.setChecked(True)
        self._cd_cookies.setChecked(True)
        self._cd_history.setChecked(False)
        self._cd_visited.setChecked(False)
        for c in (self._cd_cache, self._cd_cookies, self._cd_history, self._cd_visited):
            lay.addWidget(c)
        lay.addWidget(zh_buttons(dlg, ok="确定", cancel="取消"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._do_clear_data()

    def _do_clear_data(self):
        prof = get_app_profile()
        if self._cd_cache.isChecked():
            prof.clearHttpCache()
        if self._cd_cookies.isChecked():
            try:
                prof.cookieStore().deleteAllCookies()
            except Exception:  # noqa: BLE001
                pass
        if self._cd_history.isChecked():
            self._history = []
            self._completer.model().setStringList(self._history)
            self._save_history()
        if self._cd_visited.isChecked():
            try:
                prof.clearAllVisitedLinks()
            except Exception:  # noqa: BLE001
                pass
        self._status_label.setText("已清除所选浏览数据")

    # ---------------- 历史 ----------------
    def _push_history(self, url):
        """记录一条历史。

        性能：这里原先每次导航都同步写 QSettings（磁盘 IO，会阻塞 GUI 线程，
        在慢磁盘上表现为"点击后界面卡一下"）。现改为**防抖合并写入**：
        连续导航只写最后一次，停顿 800ms 后落盘。
        """
        if not url or url.startswith(("omni://", "data:", "about:")):
            return
        if url in self._history:
            self._history.remove(url)
        self._history.insert(0, url)
        self._history = self._history[:200]
        self._completer.model().setStringList(self._history)
        self._schedule_history_save()

    def _schedule_history_save(self):
        """防抖：延迟保存历史，避免每次导航都做磁盘 IO。"""
        if self._history_save_timer is None:
            self._history_save_timer = QTimer(self)
            self._history_save_timer.setSingleShot(True)
            self._history_save_timer.setInterval(800)
            self._history_save_timer.timeout.connect(self._save_history)
        self._history_save_timer.start()

    @staticmethod
    def _qsettings():
        return QSettings("Yc浏览器", "Yc浏览器")

    def _load_history(self):
        return self._qsettings().value("history", [])

    def _save_history(self):
        self._qsettings().setValue("history", self._history)

    # ---------------- 书签持久化 ----------------
    def _load_bookmarks(self):
        try:
            data = self._qsettings().value("bookmarks", [])
        except Exception:  # noqa: BLE001
            return []
        if not isinstance(data, list):
            return []
        out = []
        for d in data:
            if isinstance(d, dict) and d.get("url"):
                out.append({"title": d.get("title", ""), "url": d["url"]})
        return out

    def _save_bookmarks(self):
        self._qsettings().setValue("bookmarks", self._bookmarks)

    # ---------------- 设置 ----------------
    def _open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings.update(dlg.collect())
            self._save_settings()
            self.engine_combo.setCurrentIndex(
                self._idx(ENGINES, self.settings.get("default_engine", "blink"))
            )
            # 翻译后端配置即时生效
            self._tr_client.backend = self.settings.get("translate_backend", "mymemory")
            self._tr_client.endpoint = self.settings.get("translate_endpoint", "")
            self.apply_ui_scale()

    def _open_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("帮助 / 关于")
        dlg.resize(self._dialog_size(0.6, 0.74, 780, 760, 480, 380))
        dlg.setMinimumSize(440, 320)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setOpenExternalLinks(True)
        te.setHtml(self._help_html())
        lay.addWidget(te)
        lay.addWidget(zh_buttons(dlg, close="关闭", with_ok=False, with_cancel=False))
        dlg.exec()

    def _help_html(self):
        # 内容生成下沉到 internal.help_html（纯函数、无 Qt 依赖，便于测试与复用）
        return help_html()

    def _load_settings(self):
        s = self._qsettings()
        return {
            "default_engine": s.value("default_engine", "blink"),
            "search_engine": s.value("search_engine", "bing"),
            "home_page": s.value("home_page", "omni://home"),
            "font_scale": int(s.value("font_scale", 100)),
            "adaptive": bool(s.value("adaptive", True)),
            "translate_backend": s.value("translate_backend", "mymemory"),
            "translate_target": s.value("translate_target", "zh"),
            "translate_endpoint": s.value("translate_endpoint", ""),
            "translate_glossary": s.value("translate_glossary", ""),
            "download_connections": int(s.value("download_connections", 8)),
            "download_speed_limit": int(s.value("download_speed_limit", 0)),
        }

    def _save_settings(self):
        s = self._qsettings()
        for k, v in self.settings.items():
            s.setValue(k, v)

    # ---------------- 分辨率自适应 ----------------
    def compute_ui_scale(self):
        screen = self.screen() or (QApplication.primaryScreen() if QApplication.instance() else None)
        if not screen:
            return 1.0
        dpr = screen.devicePixelRatio()
        g = screen.geometry()
        base = ((g.width() / 1920.0) + (g.height() / 1080.0)) / 2.0
        scale = base * (0.85 + 0.15 * min(dpr, 2.0))
        return max(0.8, min(scale, 2.2))

    def _apply_window_geometry(self):
        """按主屏分辨率自动设定窗口大小（约 92% 宽、90% 高），并居中。"""
        screen = self.screen() or (
            QApplication.primaryScreen() if QApplication.instance() else None
        )
        if not screen:
            self.resize(1360, 860)
            return
        g = screen.availableGeometry()  # 排除任务栏等保留区域
        w = int(min(g.width() * 0.92, 1700))
        h = int(min(g.height() * 0.90, 1050))
        self.resize(w, h)
        fr = self.frameGeometry()
        fr.moveCenter(g.center())
        self.move(fr.topLeft())

    def _dialog_size(self, frac_w=0.5, frac_h=0.6, max_w=900, max_h=720, min_w=420, min_h=300):
        """按主屏分辨率推导对话框尺寸（算法在 layout.dialog_size，纯函数可测）。"""
        screen = self.screen() or (
            QApplication.primaryScreen() if QApplication.instance() else None
        )
        if not screen:
            return QSize(max_w, max_h)
        g = screen.availableGeometry()
        return dialog_size(g.width(), g.height(), frac_w, frac_h, max_w, max_h, min_w, min_h)

    def apply_ui_scale(self):
        if bool(self.settings.get("adaptive", True)):
            scale = self.compute_ui_scale()
        else:
            scale = 1.0
        font_scale = int(self.settings.get("font_scale", 100)) / 100.0
        scale *= font_scale
        self._ui_scale = scale

        # 图标按 Windows 工具栏尺寸规范取档（与分辨率解耦，避免图标过大）。
        sz = self._sz()
        self.toolbar.setIconSize(QSize(sz, sz))
        self.addr_bar.setIconSize(QSize(sz, sz))
        for obj, name, is_logo in self._icon_targets:
            if is_logo:
                obj.setIcon(make_logo(max(24, sz)))
            else:
                obj.setIcon(_ic(name, sz))

        font = max(9, round(11 * scale))
        for w in (
            self.address, self.engine_combo, self.search_combo,
            self.btn_new, self.btn_find, self.btn_download,
            self.btn_bookmark, self.menu_btn,
            self.zoom_out_btn, self.zoom_reset_btn, self.zoom_in_btn,
            self.btn_settings, self.logo_btn,
            self.btn_go, self.btn_clear_addr,
        ):
            f = w.font()
            f.setPointSize(font)
            w.setFont(f)
        self.address.setMinimumHeight(max(28, round(34 * scale)))
        self._update_zoom_label()
        self._refresh_bookmark_state()
        for i in range(self.tabs.count()):
            t = self.tabs.widget(i)
            if isinstance(t, BrowserTab):
                t.apply_ui_scale(scale)

    def _connect_screens(self):
        app = QApplication.instance()
        if not app:
            return
        # 切换主屏（如接入不同分辨率显示器）时，重新适配界面缩放与窗口尺寸。
        app.primaryScreenChanged.connect(
            lambda: (self.apply_ui_scale(), self._apply_window_geometry())
        )
        try:
            for sc in app.screens():
                sc.physicalDotsPerInchChanged.connect(lambda: self.apply_ui_scale())
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _idx(pairs, value):
        for i, (_, v) in enumerate(pairs):
            if v == value:
                return i
        return 0
