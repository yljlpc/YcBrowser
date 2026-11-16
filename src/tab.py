"""浏览器标签页：封装一个 QWebEngineView + 自定义 QWebEnginePage。

性能要点：
- 默认（Blink/WebKit 现代引擎）复用共享的持久化 profile（get_app_profile），
  所有现代引擎标签共用一个网络服务进程与磁盘缓存；
- 仅当引擎需要伪装 UA（Trident 兼容）时才创建独立的 off-the-record profile，并在切回时归还；
- 内部页 omni:// 被拦截并交回主窗口用 setHtml 渲染。
"""
from PyQt6.QtCore import QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from .profile import get_app_profile

# 内部页用 setHtml 渲染时必须提供 base URL：否则页面 origin 为 about:blank，
# QtWebEngine 不会为页面内链接发射导航请求，主页卡片点击就"没有任何反应"。
#
# base URL 必须使用**标准 scheme**。这是实测踩过的坑：
#   - 无 base URL（about:blank）：Chromium 完全不发射链接导航请求 → 点击无反应；
#   - 自定义 scheme（yc-app://internal/home）：Chromium 把页面视为 opaque origin，
#     即使用 QWebEngineUrlScheme.registerScheme() 注册为标准语法也无效；
#     表现是网页事件（mousedown/mouseup/click）都正常命中链接，
#     acceptNavigationRequest 也收到请求并返回 True，但导航被 Chromium 拦下，
#     urlChanged 始终为空 —— 用户看到的仍然是"点击毫无反应"。
#   - 标准 https base：点击正常导航（已用原生 QWebEngineView 对照实验证实）。
#
# 这里取一个保留域名（example.com，RFC 2606 保留，不会被真实访问），
# 仅作链接解析基准与 origin 载体，不会产生任何网络请求。
INTERNAL_BASE_URL = QUrl("https://internal.yc-browser.example/")

# 内部 base 域名与内部页路径映射（供 acceptNavigationRequest 识别内部页链接）
INTERNAL_BASE_HOST = INTERNAL_BASE_URL.host()
INTERNAL_PATHS = {
    "/": "home",
    "/home": "home",
    "/about": "about",
}

# Trident 兼容模式下注入的最小遗留 DOM 垫片（仅用于让老站点按 IE 语义加载）。
TRIDENT_SHIM = """
(function () {
  if (typeof document.all === 'undefined') {
    try { Object.defineProperty(document, 'all', { get: function () { return document.getElementsByTagName('*'); } }); } catch (e) {}
  }
  if (!document.attachEvent) {
    document.attachEvent = function (ev, h) { window.addEventListener(ev.replace(/^on/, ''), h); };
    window.attachEvent = document.attachEvent;
  }
  if (!window.execScript) { window.execScript = function () {}; }
})();
"""


class BrowserPage(QWebEnginePage):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.on_internal = None
        # 外部链接导航回调：用于清除内部页标记，让地址栏从 omni:// 切回真实 URL。
        self.on_external_nav = None
        # 新窗口请求回调：
        #   on_new_window(url)     —— 已知目标 URL 时，直接在主窗口开新标签页
        #   on_new_window_page(page)—— Qt 交回一个空页面（新窗口/弹窗场景），由主窗口接管
        self.on_new_window = None
        self.on_new_window_page = None

    def acceptNavigationRequest(self, url, _type, is_main):
        # 内部页拦截有两种形式：
        #  1) omni://about —— 旧式自定义 scheme 地址栏入口；
        #  2) 内部 base 域名下的相对路径（如 /about）—— 内部页之间的链接。
        #     为什么不用 omni:// 做页面内链接：内部页的 origin 是标准 https
        #     （见 INTERNAL_BASE_URL 注释），Chromium 会把不认识的 omni://
        #     当作外部协议处理并直接丢弃，不会发射导航请求，链接点了没反应。
        #
        # 关键：区分两种触发来源。
        #  - omni:// 是本软件自有 scheme（地址栏输入 / 程序调用），任何导航类型
        #    都要拦截并转回内部页渲染；
        #  - 内部 base 域名下的相对路径（/about 等）只由页面内链接点击产生，
        #    必须限定 NavigationTypeLinkClicked。否则 setHtml 自身加载 base URL
        #    （NavigationTypeTyped，path="/"）也会被拦截，形成
        #    setHtml → 拦截 → setHtml 的递归：渲染器卡死、点击全部无反应，
        #    严重时进程 SIGTRAP。
        if is_main and url.scheme() == "omni":
            if callable(self.on_internal):
                self._defer_internal(url.host() or "home")
            return False

        if is_main and _type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            if url.host() == INTERNAL_BASE_HOST:
                name = INTERNAL_PATHS.get(url.path().rstrip("/") or "/", "")
                if name:
                    if callable(self.on_internal):
                        self._defer_internal(name)
                    return False
            # 用户在内部页（setHtml）点击了外部链接：这是真实导航，放行前清除
            # 内部页标记，否则地址栏会一直停在 omni://home，看起来像"没反应"。
            if callable(self.on_external_nav):
                self.on_external_nav(url)
        return super().acceptNavigationRequest(url, _type, is_main)

    def _defer_internal(self, name):
        """延迟到事件循环再渲染内部页。

        必须在 acceptNavigationRequest 回调栈之外调用 setHtml：在回调内
        同步重入渲染器会导致 Chromium 渲染进程崩溃（进程 SIGTRAP）。
        这里用 singleShot(0) 把渲染排到当前事件循环迭代之后。
        """
        QTimer.singleShot(0, lambda: self.on_internal(name))

    def createWindow(self, _window_type):
        """Qt WebEngine 新窗口请求入口（target="_blank" / window.open()）。

        Qt 默认**完全忽略**新窗口请求：链接点击后什么都不会发生，这是用户
        反馈的"点击没反应"第二类根因。

        机制依据 Qt 源码（qtwebengine/src/core/api/qwebenginepage.cpp）：
        `adoptNewWindow()` 先调用 `createWindow()`；返回非空 page 时 Qt 会把
        新 WebContents 接管进该 page 并自动 `setUrl(targetUrl)`；只有返回
        nullptr 才会退而发射 `newWindowRequested` 信号。

        注意：PyQt6 的 QWebEngineNewWindowRequest **没有暴露 accept()/reject()**
        （见 dir() 输出），因此无法用信号方式标记"已处理"，覆写 createWindow
        是唯一可靠路径。

        这里返回一个新页面，交由主窗口包成新标签页。
        """
        # 页面必须与源页共用同一个 profile，否则 Qt 报
        # "Can not adopt content from a different WebEngineProfile."
        page = BrowserPage(self.profile(), None)
        if callable(self.on_new_window_page):
            self.on_new_window_page(page)
        return page


class BrowserTab(QWidget):
    title_changed = pyqtSignal(str)
    icon_changed = pyqtSignal(QIcon)
    url_changed = pyqtSignal(QUrl)
    load_progress = pyqtSignal(int)
    open_internal = pyqtSignal(str)
    find_result = pyqtSignal(int, int)
    # 新窗口请求：携带 Qt 创建好的新页面（由主窗口包成新标签页）
    new_window_page = pyqtSignal(object)

    def __init__(self, core, parent=None, private=False):
        super().__init__(parent)
        self.core = core
        self._backend = "blink"
        self._doc_mode = "edge"
        self._legacy_shims = False
        self._user_zoom = 1.0
        self._ui_scale = 1.0
        self._own_profile = False
        self._devtools_view = None
        # 内部页（主页/关于）标记：用于地址栏显示可读的 omni:// 地址
        self._internal_page = ""
        # 无痕（隐私）模式：使用 off-the-record profile，不写入磁盘缓存与 Cookie
        self._private = bool(private)

        self.view = QWebEngineView(self)
        # 默认使用共享持久化 profile（磁盘缓存 + 单网络服务进程）。
        if self._private:
            self._own_profile = True
            self._make_page(QWebEngineProfile())
        else:
            self._make_page(get_app_profile())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

    def _make_page(self, profile):
        self.profile = profile
        page = BrowserPage(profile, self.view)
        self.view.setPage(page)
        self._wire_page(page)

    def _wire_page(self, page):
        """把页面事件接到标签页信号上（新建页与被接管的新页面共用）。"""
        self.page = page
        self.page.on_internal = lambda host: self.open_internal.emit(host or "home")
        # 外部链接点击后清除内部页标记，地址栏恢复显示真实 URL；
        # 只在确有标记时清，避免影响普通网页导航。
        self.page.on_external_nav = lambda url: self._clear_internal_flag(url)
        # 新窗口请求（target=_blank / window.open）：交由主窗口开新标签页。
        self.page.on_new_window_page = lambda p: self.new_window_page.emit(p)
        self.page.titleChanged.connect(lambda t: self.title_changed.emit(t or "新标签页"))
        self.page.iconChanged.connect(self.icon_changed.emit)
        self.page.urlChanged.connect(self.url_changed.emit)
        self.page.loadProgress.connect(self.load_progress.emit)
        self.page.loadFinished.connect(self._on_load_finished)
        self.page.findTextFinished.connect(self._on_find_result)

    def attach_page(self, page):
        """接管外部创建的页面（来自 createWindow 新窗口请求）。

        Qt 的时序要求：createWindow() 返回后，Qt 立刻把新 WebContents
        灌入返回的 page，因此必须在 createWindow 调用栈内同步完成
        `view.setPage(page)`，否则新页面拿不到渲染器。
        """
        self.view.setPage(page)
        # 被接管的页面自带来源标签页的 profile；Qt 要求被接管内容与页面
        # 处于同一 profile，否则报 "Can not adopt content from a different
        # WebEngineProfile."。这里同步标签页的 profile 记录。
        self.profile = page.profile()
        self._wire_page(page)

    def _on_find_result(self, result):
        self.find_result.emit(result.numberOfMatches(), result.activeMatch())

    def _on_load_finished(self, ok):
        if ok and self._legacy_shims:
            self.page.runJavaScript(TRIDENT_SHIM)

    # ---- 导航 ----
    def load_url(self, url: str):
        # 导航到外部页面后不再是内部页，需清除标记（地址栏显示真实 URL）
        self._internal_page = ""
        self.view.load(QUrl.fromUserInput(url))

    def set_html(self, html: str):
        # 必须带 base URL：QtWebEngine 对无 base 的 setHtml 页面不发射链接导航
        # 请求，主页卡片点击会毫无反应。base 用自定义 scheme，仅作解析基准。
        self.view.setHtml(html, INTERNAL_BASE_URL)

    def _clear_internal_flag(self, url=None):
        """从内部页点击外部链接后清除 omni 标记，地址栏切回真实 URL。"""
        if self._internal_page:
            self._internal_page = ""

    # ---- 打印 / PDF ----
    def print_to_pdf(self, path: str, callback=None):
        """把当前页面导出为 PDF。

        QtWebEngine 的 printToPdf 回调签名随成败而变：
        成功时回调 `(pdf_data)`，失败时回调 `(None, error_string)`。
        故这里用 *args 兼容两种形式。
        """
        def done(*args):
            if len(args) >= 2 and args[1]:
                if callback:
                    callback(None, str(args[1]))
                return
            pdf_data = args[0] if args else None
            if pdf_data is None:
                if callback:
                    callback(None, "未生成 PDF 数据")
                return
            try:
                with open(path, "wb") as f:
                    f.write(pdf_data)
                if callback:
                    callback(path, None)
            except OSError as exc:
                if callback:
                    callback(None, str(exc))

        self.page.printToPdf(done)

    def print_preview(self, dialog_parent=None):
        """调用系统打印对话框打印当前页面。

        Qt 的 print_() 直接调系统打印面板，其按钮文字由系统语言决定，
        在英文环境下会出现英文按钮。这里改用自绘的中文打印面板：
        选择打印机、份数、纸张与缩放，再调用同一套打印接口。
        """
        try:
            from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
        except ImportError:
            # 无 QtPrintSupport 时退回 Qt 内置面板
            self.page.print_(dialog_parent)
            return

        printer = QPrinter()
        printer.setDocName(self.view.page().url().toString() or "Yc浏览器")
        dlg = QPrintDialog(printer, dialog_parent)
        dlg.setWindowTitle("打印")
        # Qt 打印面板的按钮同样可能是英文，这里逐个中文化
        try:
            from .zh import ZH_BUTTON_TEXT
            from PyQt6.QtWidgets import QPushButton
            for btn in dlg.findChildren(QPushButton):
                txt = btn.text()
                if txt in ("Print", "&Print"):
                    btn.setText("打印")
                elif txt in ("Cancel", "&Cancel"):
                    btn.setText("取消")
                elif txt in ("Close", "&Close"):
                    btn.setText("关闭")
                elif txt in ("Help", "&Help"):
                    btn.setText("帮助")
        except Exception:  # noqa: BLE001
            pass
        if dlg.exec() == QPrintDialog.DialogCode.Accepted:
            self.page.print_(printer)

    def back(self):
        self.view.back()

    def forward(self):
        self.view.forward()

    def reload(self):
        self.view.reload()

    def stop(self):
        self.view.stop()

    def can_go_back(self):
        return self.view.history().canGoBack()

    def can_go_forward(self):
        return self.view.history().canGoForward()

    # ---- 页面内查找 ----
    def find(self, text, backward=False):
        flags = QWebEnginePage.FindFlag.FindBackward if backward else QWebEnginePage.FindFlag(0)
        self.page.findText(text, flags)

    # ---- 引擎 ----
    def set_engine(self, backend, doc_mode="edge"):
        self._backend = backend
        self._doc_mode = doc_mode
        spec = self.core.engine_spec(backend, doc_mode)
        if isinstance(spec, dict) and spec.get("ok") is False:
            return spec
        ua = spec.get("ua", "") if isinstance(spec, dict) else ""
        cloak = bool(spec.get("cloak_ua", False)) if isinstance(spec, dict) else False
        self._legacy_shims = bool(spec.get("legacy_shims", False)) if isinstance(spec, dict) else False
        if cloak and ua:
            # 需要伪装 UA：创建独立 profile（Qt6 的 UA 在 profile 层生效）。
            if not self._own_profile:
                self._own_profile = True
                # 无痕标签始终使用 off-the-record profile，绝不落盘。
                prof = QWebEngineProfile() if self._private else QWebEngineProfile()
                prof.setHttpUserAgent(ua)
                self._make_page(prof)
            else:
                self.profile.setHttpUserAgent(ua)
        else:
            # 现代引擎：复用共享持久化 profile，释放独立 profile 所占进程。
            # 无痕标签例外：必须保持私有 profile，不能切回共享的可落盘 profile。
            if self._own_profile and not self._private:
                self._own_profile = False
                self._make_page(get_app_profile())
        return spec

    # ---- 缩放 / 自适应 ----
    def apply_ui_scale(self, ui_scale):
        self._ui_scale = ui_scale
        self.view.setZoomFactor(self._user_zoom * ui_scale)

    def set_user_zoom(self, z):
        self._user_zoom = z
        self.view.setZoomFactor(z * self._ui_scale)
