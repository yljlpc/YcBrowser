"""浏览器标签页：封装一个 QWebEngineView + 自定义 QWebEnginePage。

性能要点：
- 默认（Blink/WebKit 现代引擎）复用共享的持久化 profile（get_app_profile），
  所有现代引擎标签共用一个网络服务进程与磁盘缓存；
- 仅当引擎需要伪装 UA（Trident 兼容）时才创建独立的 off-the-record profile，并在切回时归还；
- 内部页 omni:// 被拦截并交回主窗口用 setHtml 渲染。
"""
from PyQt6.QtCore import pyqtSignal, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from .profile import get_app_profile

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

    def acceptNavigationRequest(self, url, _type, is_main):
        if url.scheme() == "omni":
            if callable(self.on_internal):
                self.on_internal(url.host() or "home")
            return False
        return super().acceptNavigationRequest(url, _type, is_main)


class BrowserTab(QWidget):
    title_changed = pyqtSignal(str)
    icon_changed = pyqtSignal(QIcon)
    url_changed = pyqtSignal(QUrl)
    load_progress = pyqtSignal(int)
    open_internal = pyqtSignal(str)
    find_result = pyqtSignal(int, int)

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
        self.page = BrowserPage(profile, self.view)
        self.view.setPage(self.page)
        self.page.on_internal = lambda host: self.open_internal.emit(host or "home")
        self.page.titleChanged.connect(lambda t: self.title_changed.emit(t or "新标签页"))
        self.page.iconChanged.connect(self.icon_changed.emit)
        self.page.urlChanged.connect(self.url_changed.emit)
        self.page.loadProgress.connect(self.load_progress.emit)
        self.page.loadFinished.connect(self._on_load_finished)
        self.page.findTextFinished.connect(self._on_find_result)

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
        self.view.setHtml(html)

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
