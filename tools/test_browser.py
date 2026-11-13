"""OmniBrowser 无头逐项功能测试。

运行方式（必须在导入 PyQt 之前设好环境变量）：
    QT_QPA_PLATFORM=offscreen python3 tools/test_browser.py

覆盖：
  A. Rust 核心 IPC（导航归一化 / 引擎规格 / 文档模式协商）
  B. 前端 GUI（字体注册 / 多标签 / 渲染加载 / JS 取标题 / 前进后退 /
     引擎切换 UA / 内部页 / 分辨率自适应）
"""
import os
import sys
import time

# 必须在导入任何 PyQt / WebEngine 之前设置运行环境。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer",
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEventLoop, QTimer, QUrl
from PyQt6.QtWidgets import QApplication

from src.core_client import CoreClient
from src.fonts import available_families, register_fonts
from src.profile import get_app_profile
from src.window import ENGINES, MainWindow

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail else ""))


def wait_loaded(tab, timeout=12000):
    loop = QEventLoop()
    done = {}

    def on_progress(v):
        if v >= 100:
            done["ok"] = True
            loop.quit()

    tab.load_progress.connect(on_progress)
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    return done.get("ok", False)


def wait_ms(ms):
    """等待指定毫秒（供异步 JS 回调落地）。"""
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        QApplication.processEvents()
        time.sleep(0.01)


def get_title(tab, timeout=8000):
    for _ in range(6):
        result = {}

        def cb(val):
            result["v"] = val
            loop.quit()

        loop = QEventLoop()
        tab.page.runJavaScript("document.title", cb)
        QTimer.singleShot(timeout, loop.quit)
        loop.exec()
        if result.get("v"):
            return result["v"]
        time.sleep(0.3)
    return result.get("v")


def get_ua(tab, timeout=8000):
    result = {}

    def cb(val):
        result["v"] = val
        loop.quit()

    loop = QEventLoop()
    tab.page.runJavaScript("navigator.userAgent", cb)
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    return result.get("v")


# --------------------------------------------------------------------------
# A. Rust 核心 IPC
# --------------------------------------------------------------------------
def test_core():
    print("\n=== A. Rust 核心 IPC ===")
    try:
        core = CoreClient()
    except Exception as exc:  # noqa: BLE001
        check("核心进程启动", False, str(exc))
        return None

    check("ping", core.ping().get("pong") is True)

    r = core.resolve_nav("example.org", "bing")
    check("导航: 裸域名补 https", r.get("kind") == "url" and r.get("url") == "https://example.org", str(r))
    r = core.resolve_nav("localhost:8080", "bing")
    check("导航: host:port", r.get("kind") == "url" and r.get("url").startswith("http://localhost:8080"), str(r))
    r = core.resolve_nav("rust 语言", "baidu")
    check("导航: 含空格->搜索", r.get("kind") == "search" and "baidu.com" in r.get("url", ""), str(r))
    r = core.resolve_nav("https://example.com", "bing")
    check("导航: 保留 scheme", r.get("kind") == "url" and r.get("url") == "https://example.com", str(r))
    r = core.resolve_nav("omni://settings", "bing")
    check("导航: 内部协议", r.get("kind") == "internal", str(r))

    for label, backend in ENGINES:
        spec = core.engine_spec(backend, "ie11" if backend == "trident" else "edge")
        ok = isinstance(spec, dict) and bool(spec.get("ua"))
        check(f"引擎规格: {label}", ok, str(spec)[:80])

    tr = core.engine_spec("trident", "ie8")
    check("Trident UA 含 MSIE/Trident", "Trident" in tr.get("ua", ""), tr.get("ua", ""))
    bl = core.engine_spec("blink", "edge")
    check("Blink UA 含 Chrome", "Chrome" in bl.get("ua", ""), bl.get("ua", ""))

    neg = core.negotiate_docmode("IE=EmulateIE7")
    check("文档模式协商: EmulateIE7->IE7", neg.get("doc_mode") == "IE7", str(neg))
    neg = core.negotiate_docmode("IE=edge")
    check("文档模式协商: edge->Edge", neg.get("doc_mode") == "Edge", str(neg))

    core.close()
    return True


# --------------------------------------------------------------------------
# B. 前端 GUI（offscreen）
# --------------------------------------------------------------------------
def test_gui():
    print("\n=== B. 前端 GUI（offscreen）===")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("OmniBrowser")

    try:
        core = CoreClient()
    except Exception as exc:  # noqa: BLE001
        check("核心启动(GUI)", False, str(exc))
        return

    # 字体注册
    fams = register_fonts()
    check("字体注册非空", len(fams) > 0, f"{len(fams)} 个字族")

    win = MainWindow(core)

    # 自适应缩放范围
    scale = win.compute_ui_scale()
    check("自适应缩放取值合理", 0.8 <= scale <= 2.2, f"scale={scale:.3f}")
    win.apply_ui_scale()
    check("apply_ui_scale 不崩溃", win._ui_scale > 0, f"ui_scale={win._ui_scale:.3f}")
    check("工具栏图标尺寸>0", win.toolbar.iconSize().width() > 0)

    # 新增标签并用 data: URL 渲染（data URL 内不要放非 ASCII，避免 URL 层编码歧义；
    # 中文渲染已通过下面的“内部关于页”用例用 setHtml+UTF-8 meta 验证）。
    tab = win.add_tab("data:text/html,<html><head><title>PageA</title></head><body>AAA</body></html>")
    ok = wait_loaded(tab)
    check("标签加载 data URL", ok)
    title = get_title(tab)
    check("JS 读取标题=PageA", title == "PageA", f"title={title!r}")

    # 前进/后退
    tab.load_url("data:text/html,<html><head><title>PageB</title></head><body>BBB</body></html>")
    wait_loaded(tab)
    check("第二次加载后标题=PageB", get_title(tab) == "PageB")
    check("可后退", tab.can_go_back())
    tab.back()
    wait_loaded(tab)
    check("后退后标题=PageA", get_title(tab) == "PageA")
    tab.forward()
    wait_loaded(tab)
    check("前进后标题=PageB", get_title(tab) == "PageB")

    # 引擎切换 UA
    win.engine_combo.setCurrentIndex(win._idx(ENGINES, "trident"))
    win._on_engine_changed(0)
    time.sleep(0.3)
    ua = get_ua(tab)
    check("切换到 Trident 后 UA 含 Trident", bool(ua) and "Trident" in ua, f"ua={ua}")
    win.engine_combo.setCurrentIndex(win._idx(ENGINES, "blink"))
    win._on_engine_changed(0)
    time.sleep(0.3)
    ua = get_ua(tab)
    check("切回 Blink 后 UA 含 Chrome", bool(ua) and "Chrome" in ua, f"ua={ua}")

    # 内部页
    win.open_internal(tab, "about")
    wait_loaded(tab)
    title = get_title(tab)
    check("内部关于页渲染", title == "关于 Yc浏览器", f"title={title!r}")

    # 多标签
    before = win.tabs.count()
    win.add_tab("data:text/html,<html><title>T2</title></html>")
    check("新增标签页计数+1", win.tabs.count() == before + 1, f"count={win.tabs.count()}")

    # 缩放因子随自适应变化
    zf = tab.view.zoomFactor()
    check("网页缩放因子>0", zf > 0, f"zoom={zf:.3f}")

    # 新增功能完整性（书签 / 缩放 / 菜单 / 清除数据）
    test_features(win)

    # 翻译 / 下载 / 媒体嗅探
    test_translate_and_download(win)

    # 无痕 / 打印 / 标签页菜单
    test_extras(win)

    win.close()
    core.close()


def test_features(win):
    """验证新补全功能的稳定性：书签、缩放、菜单、清除数据对话框均不崩溃。"""
    print("\n=== C. 新增功能完整性 ===")

    # 应用菜单动作齐全
    menu = win._build_app_menu()
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    expected = ["书签管理…", "历史记录…", "清除浏览数据…", "设置…", "帮助 / 快捷键",
                "关于 Yc浏览器"]
    check("应用菜单动作齐全", all(t in texts for t in expected), str(texts))
    # 用 data URL 标签测试书签守卫：data: 页面不应被收藏
    t = win.add_tab("data:text/html,<html><head><title>BM</title></head><body>x</body></html>")
    wait_loaded(t)
    url = t.view.page().url().toString()
    check("测试标签 URL 就绪", url.startswith("data:"), url[:24])

    before = len(win._bookmarks)
    win._add_bookmark()
    check("data: 页面被书签守卫拒绝", len(win._bookmarks) == before, f"n={len(win._bookmarks)}")

    # 注入一条真实书签，验证管理器可展示并支持删除
    win._bookmarks.append({"title": "Example", "url": "https://example.com"})
    win._save_bookmarks()
    win._open_bookmarks()
    win._refresh_bookmarks()
    check("书签管理器展示已注入书签", win._bm_list.count() >= 1, f"count={win._bm_list.count()}")
    win._bm_list.setCurrentRow(0)
    win._delete_bookmark_item()
    check(
        "从管理器删除书签生效",
        "https://example.com" not in [b.get("url") for b in win._bookmarks],
    )
    win._bm_dlg.close()
    # 还原书签列表到注入前状态（避免污染持久化）
    win._bookmarks = win._bookmarks[:before]
    win._save_bookmarks()

    # 缩放：放大 / 缩小 / 重置
    z0 = t._user_zoom
    win._zoom_in()
    check("放大后 user_zoom 增大", t._user_zoom > z0, f"{z0} -> {t._user_zoom}")
    win._zoom_out()
    win._zoom_out()
    check("缩小后 user_zoom 减小", t._user_zoom < z0, f"{t._user_zoom}")
    win._zoom_reset()
    check("重置缩放=1.0", abs(t._user_zoom - 1.0) < 1e-6, f"{t._user_zoom}")

    # 书签管理器 / 历史管理器可构建并刷新（不阻塞）
    win._open_bookmarks()
    win._refresh_bookmarks()
    check("书签管理器可构建", win._bm_dlg is not None and win._bm_dlg.isVisible())
    win._bm_dlg.close()
    win._open_history()
    win._refresh_history()
    check("历史管理器可构建", win._hist_dlg is not None)
    win._hist_dlg.close()

    # 清除浏览数据能力（直接验证底层 API，避免触发模态确认框阻塞）
    prof = get_app_profile()
    try:
        prof.clearHttpCache()
        prof.cookieStore().deleteAllCookies()
        check("可清除 HTTP 缓存 / Cookie", True)
    except Exception as exc:  # noqa: BLE001
        check("可清除 HTTP 缓存 / Cookie", False, str(exc))

    # 地址栏 / 书签状态刷新不崩溃
    win._refresh_bookmark_state()
    win._update_zoom_label()


def test_translate_and_download(win):
    """验证翻译流程、下载管理器与媒体嗅探在真实渲染环境下的可用性。"""
    print("\n=== D. 翻译 / 下载 / 媒体嗅探 ===")

    # ---- 1. 翻译：注入英文页面 → 提取 → 回填 ----
    html = ("<html><head><title>EN</title></head><body>"
            "<h1>Install the browser</h1>"
            "<p>This feature was disabled by the administrator.</p>"
            "</body></html>")
    t = win.add_tab(None)
    t.set_html(html)
    wait_loaded(t)

    # 提取脚本能拿到正文段落
    extracted = []
    t.view.page().runJavaScript(
        "(function(){var o=[];var w=document.createTreeWalker(document.body,"
        "NodeFilter.SHOW_TEXT,null);var n;while((n=w.nextNode())){"
        "if(n.nodeValue.trim().length>2)o.push(n.nodeValue.trim());}return o;})()",
        lambda v: extracted.extend(v or []),
    )
    wait_ms(400)
    check("页面正文可被提取", len(extracted) >= 2, str(extracted))

    # 核心判定：这些英文应翻译、已中文的不应翻译
    should_en = win._tr_client.should_translate("Install the browser", "zh")
    should_zh = win._tr_client.should_translate("安装浏览器", "zh")
    check("英文段落判定为需翻译", should_en is True)
    check("中文段落不重复翻译", should_zh is False)

    # 译文回填：注入固定译文，验证 DOM 被替换
    win._on_tr_done({"Install the browser": "安装浏览器",
                     "This feature was disabled by the administrator.": "此功能已被管理员禁用。"})
    wait_ms(500)
    body_text = []
    t.view.page().runJavaScript(
        "document.body ? document.body.innerText : ''",
        lambda v: body_text.append(v or ""),
    )
    wait_ms(400)
    text = body_text[0] if body_text else ""
    check("译文已写入页面", "安装浏览器" in text, text[:60])

    # 还原原文
    win._restore_original()
    wait_ms(600)
    restored = []
    t.view.page().runJavaScript(
        "document.body ? document.body.innerText : ''",
        lambda v: restored.append(v or ""),
    )
    wait_ms(400)
    check("可还原页面原文", "Install the browser" in (restored[0] if restored else ""),
          (restored[0][:60] if restored else ""))

    # ---- 2. 媒体嗅探 ----
    media_html = ("<html><head><title>MEDIA</title></head><body>"
                  "<video src='https://cdn.example.com/v/clip.mp4'></video>"
                  "<audio src='https://cdn.example.com/a/song.mp3'></audio>"
                  "</body></html>")
    t2 = win.add_tab(None)
    t2.set_html(media_html)
    wait_loaded(t2)
    sniffed = []
    t2.view.page().runJavaScript(
        "(function(){var o=[];var els=document.querySelectorAll('video,audio');"
        "for(var i=0;i<els.length;i++){var s=els[i].currentSrc||els[i].src||'';"
        "if(s)o.push({url:s,kind:'video',ext:(s.split('.').pop()||''),mime:els[i].type||''});}"
        "return o;})()",
        lambda v: sniffed.extend(v or []),
    )
    wait_ms(400)
    from src.media import media_filename, parse_media_items
    items = parse_media_items(sniffed)
    check("页面媒体可被嗅探", len(items) >= 2, str(len(items)))
    if items:
        name = media_filename(items[0][1], items[0][0], items[0][2], items[0][3])
        check("媒体文件名可生成", bool(name), name)

    # ---- 3. 下载管理器 UI ----
    from src.downloader import DownloadTask
    from src.download_ui import DownloadManagerDialog

    dlg = win._dl_dlg
    win._open_downloads()
    check("下载管理器可打开", win._dl_dlg is not None)
    check("下载管理器为正确类型", isinstance(win._dl_dlg, DownloadManagerDialog))

    # 注册一个任务，验证行渲染与状态刷新
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="omnidl_gui_")
    task = DownloadTask("https://example.com/file.bin", tmpdir,
                        filename="file.bin", connections=4)
    task.filename = "file.bin"
    task.total = 1024 * 1024
    task.downloaded = 512 * 1024
    task.state = "downloading"
    task.speed = 1024 * 512
    win._dl_tasks.append(task)
    win._open_downloads()
    win._dl_dlg.refresh()
    row = win._dl_dlg.tree.topLevelItem(0)
    check("下载管理器展示任务行", row is not None)
    if row is not None:
        check("下载行显示进度", "50%" in row.text(3), row.text(3))
        check("下载行显示大小", "512.0 KB" in row.text(2), row.text(2))
        check("下载行显示状态", row.text(1) == "下载中", row.text(1))
        check("下载行显示速度", "KB/s" in row.text(4), row.text(4))
    win._dl_dlg.close()


def test_extras(win):
    """验证无痕模式、打印/PDF、标签页右键菜单等补全功能。"""
    print("\n=== E. 无痕 / 打印 / 标签页菜单 ===")

    # ---- 1. 无痕标签使用独立 off-the-record profile ----
    priv = win.add_tab("omni://home", private=True)
    check("无痕标签已创建", priv is not None)
    check("无痕标签标记为私有", getattr(priv, "_private", False) is True)
    check("无痕标签不共享持久化 profile",
          priv.profile is not None and priv.profile.isOffTheRecord() is True,
          str(priv.profile.isOffTheRecord() if priv.profile else None))
    win.close_tab(win.tabs.indexOf(priv))

    # ---- 2. 打印 / 导出 PDF ----
    t = win.add_tab(None)
    t.set_html("<html><head><title>PDF</title></head><body><p>hello</p></body></html>")
    wait_loaded(t)
    check("标签具备导出 PDF 能力", hasattr(t, "print_to_pdf"))
    check("标签具备打印能力", hasattr(t, "print_preview"))

    # 真实导出一次 PDF，验证文件确实生成
    import tempfile
    out = os.path.join(tempfile.mkdtemp(prefix="omnipdf_"), "out.pdf")
    done = {"ok": False}
    t.print_to_pdf(out, lambda p, e: done.update(ok=(p is not None and e is None)))
    t0 = time.time()
    while not done["ok"] and time.time() - t0 < 15:
        QApplication.processEvents()
        time.sleep(0.05)
    check("PDF 导出成功", done["ok"] and os.path.exists(out)
          and os.path.getsize(out) > 500,
          f"{os.path.getsize(out) if os.path.exists(out) else 0} bytes")

    # ---- 3. 标签页右键菜单动作 ----
    menu = win._build_app_menu()
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    for name in ("新建无痕窗口", "打印当前页面…", "导出为 PDF…"):
        check(f"菜单含「{name}」", name in texts, str(texts))

    # ---- 4. 关闭其他 / 关闭右侧 ----
    base = win.tabs.count()
    win.add_tab("data:text/html,<html><title>X1</title></html>")
    win.add_tab("data:text/html,<html><title>X2</title></html>")
    check("新增两个标签", win.tabs.count() == base + 2, f"{win.tabs.count()}")
    win._close_other_tabs(0)
    check("关闭其他标签后仅剩 1 个", win.tabs.count() == 1, f"{win.tabs.count()}")
    win.add_tab("data:text/html,<html><title>Y1</title></html>")
    win.add_tab("data:text/html,<html><title>Y2</title></html>")
    win._close_right_tabs(0)
    check("关闭右侧标签后仅剩 1 个", win.tabs.count() == 1, f"{win.tabs.count()}")

    # ---- 5. 复制到剪贴板 ----
    from PyQt6.QtWidgets import QApplication as _App
    win._copy_to_clipboard("https://example.com/x")
    check("复制到剪贴板生效",
          _App.clipboard().text() == "https://example.com/x",
          _App.clipboard().text())


if __name__ == "__main__":
    test_core()
    test_gui()
    print("\n=== 汇总 ===")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"通过 {passed}/{len(RESULTS)}")
    fails = [n for n, ok, _ in RESULTS if not ok]
    if fails:
        print("失败项: " + ", ".join(fails))
        sys.exit(1)
    print("全部通过")
    sys.exit(0)
