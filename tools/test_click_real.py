"""Yc浏览器「真实输入」点击响应测试（xdotool 注入真实 X11 输入事件）。

为什么不用 QTest 合成事件：
  QTest.mouseClick 走的是 Qt 内部合成事件路径，在 QtWebEngine 上
  press/release 不会进入渲染进程（实测网页侧 mousedown/click 监听全空），
  且不随 zoomFactor 换算坐标。xdotool 用 XTEST 在 X 服务器层面生成
  真实指针事件，与用户真实点击走完全相同的路径。

坐标换算：
  网页 CSS 像素 → 控件像素 = css * view.zoomFactor()
  控件像素 → 屏幕像素 = widget.mapToGlobal(QPoint(0,0))

**为什么每个用例独立进程**：
  实测在同一个 Qt 进程内连续跑多个用例会互相污染：
  外部真实站点（baidu / github / openkylin）加载后，同进程内其它标签页的
  runJavaScript 回调会被推迟甚至超时（渲染进程繁忙），
  表现为后续用例大面积「❌ 无反应」，其实是测试环境的假象。
  因此本脚本用 --case N 单独跑一个用例，由外层脚本逐个进程执行并汇总，
  结论才可信。

运行（单用例）：
    bash tools/run_xvfb.sh tools/test_click_real.py --case R2
运行（全部，由外层调度）：
    bash tools/run_click_cases.sh
产出：outputs/click_real_report.txt
"""
import argparse
import os
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer",
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEventLoop, QPoint, QTimer
from PyQt6.QtWidgets import QApplication

from src.core_client import CoreClient
from src.fonts import register_fonts
from src.window import MainWindow

OUT = os.path.join(ROOT, "outputs")
os.makedirs(OUT, exist_ok=True)

report = []


def log(m):
    print(m, flush=True)
    report.append(m)


def wait_ms(ms):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        QApplication.processEvents()
        time.sleep(0.01)


def js(tab, code, timeout=15000, retries=5):
    """执行 JS 并等待回调；渲染进程繁忙时自动重试。

    另注：QTimer.singleShot 排的 loop.quit 可能在 QEventLoop 已被 Python GC
    回收后才触发，此时调用 quit() 会抛
    "wrapped C/C++ object of type QEventLoop has been deleted" 并导致进程 abort。
    这里统一用 _quit() 包一层并捕获 RuntimeError。
    """
    for _ in range(retries):
        out = {}
        loop = QEventLoop()

        def _quit(*_a):
            try:
                loop.quit()
            except RuntimeError:
                pass  # loop 已被回收，忽略

        cb = lambda v: (out.__setitem__("v", v), _quit())
        tab.page.runJavaScript(code, cb)
        QTimer.singleShot(timeout, _quit)
        loop.exec()
        if "v" in out:
            return out["v"]
        wait_ms(2500)
    return None


def wait_url_change(tab, old, timeout=20000):
    got = {"v": None}
    loop = QEventLoop()

    def _quit(*_a):
        try:
            loop.quit()
        except RuntimeError:
            pass

    def on_url(u):
        if u.toString() != old:
            got["v"] = u.toString()
            _quit()

    tab.page.urlChanged.connect(on_url)
    QTimer.singleShot(timeout, _quit)
    loop.exec()
    try:
        tab.page.urlChanged.disconnect(on_url)
    except Exception:  # noqa: BLE001
        pass
    return got["v"]


def xdo(*args):
    return subprocess.run(["xdotool", *args], capture_output=True, text=True)


def real_click(tab, selector, index=0):
    """用 xdotool 真实点击网页中的第 index 个匹配元素。

    关键点：元素必须先滚动到视口内再取坐标。
    getBoundingClientRect() 返回的是**视口相对**坐标，若元素在页面下方
    （例如关于页底部的「返回主页」链接，CSS y≈1256，而窗口只有 860px 高），
    换算出的屏幕坐标会落到屏幕之外，xdotool 点击落空 —— 表现为「点了没反应」。
    所以这里先 scrollIntoView，再取坐标，并用 elementFromPoint 校验命中。
    """
    rect = js(
        tab,
        f"""(() => {{
            const els = document.querySelectorAll({selector!r});
            if (!els[{index}]) return null;
            const el = els[{index}];
            el.scrollIntoView({{block:'center', inline:'center'}});
            const r = el.getBoundingClientRect();
            const x = r.left + r.width/2;
            const y = r.top + r.height/2;
            const hit = document.elementFromPoint(x, y);
            const ok = !!hit && (hit === el || el.contains(hit) || hit.contains(el));
            return {{x: x, y: y, ok: ok,
                     vh: window.innerHeight, vw: window.innerWidth,
                     hitTag: hit ? hit.tagName : null}};
        }})()""",
    )
    if not rect:
        info = js(tab, """(() => ({
            href: location.href, title: document.title,
            ready: document.readyState,
            bodyLen: document.body ? document.body.innerHTML.length : -1,
            aCount: document.querySelectorAll('a').length
        }))()""")
        log(f"    [诊断] 元素未找到，页面状态: {info}")
        return None, None
    if not rect.get("ok"):
        log(f"    [诊断] 命中校验失败，hitTag={rect.get('hitTag')} "
            f"视口={rect.get('vw')}x{rect.get('vh')}")
    z = tab.view.zoomFactor()
    ctl = QPoint(int(round(rect["x"] * z)), int(round(rect["y"] * z)))
    origin = tab.view.mapToGlobal(QPoint(0, 0))
    sx, sy = origin.x() + ctl.x(), origin.y() + ctl.y()
    xdo("mousemove", "--sync", str(sx), str(sy))
    time.sleep(0.15)
    xdo("click", "--delay", "100", "1")
    return rect, (sx, sy)


# 本地页：链接指向一个稳定可达的外站，用于验证「同窗口普通链接」导航
LOCAL_HTML = (
    "<html><body style='margin:0;font-family:sans-serif'>"
    "<div style='height:200px;background:#eee'>占位区</div>"
    "<a id='lnk' href='https://github.com' "
    "style='display:block;padding:20px;font-size:20px'>去 GitHub</a>"
    "</body></html>"
)


def setup():
    app = QApplication.instance() or QApplication(sys.argv)
    register_fonts()
    core = CoreClient()
    win = MainWindow(core)
    win.resize(1360, 860)
    win.show()
    win.raise_()
    win.activateWindow()
    wait_ms(3000)
    return app, core, win


# ---------------- 各用例 ----------------

def case_R2(win, core):
    """内部页二级目录：主页 → 关于 → 返回主页。"""
    tab = win._cur()
    log("--- R2 内部页二级目录链接（主页 → 关于 → 返回主页） ---")
    win.tabs.setCurrentIndex(win.tabs.indexOf(tab))
    wait_ms(1200)
    win.open_internal(tab, "home")
    wait_ms(3000)

    rect, scr = real_click(tab, ".nav a", 0)
    log(f"  主页'关于'链接 CSS 坐标 {rect} → 屏幕坐标 {scr}")
    wait_ms(3000)
    title = tab.page.title() or ""
    ok_about = "关于" in title
    log(f"  主页→关于: {'✅ 有反应' if ok_about else '❌ 无反应'}  标题: {title!r}")
    log(f"  内部页标记: {getattr(tab, '_internal_page', '')!r}")

    rect2, scr2 = real_click(tab, ".nav a", 0)
    log(f"  关于页'返回主页'链接 CSS 坐标 {rect2} → 屏幕坐标 {scr2}")
    wait_ms(3000)
    title2 = tab.page.title() or ""
    ok_back = "主页" in title2
    log(f"  关于→主页: {'✅ 有反应' if ok_back else '❌ 无反应'}  标题: {title2!r}")
    log(f"  内部页标记: {getattr(tab, '_internal_page', '')!r}")
    return [("R2 主页→关于 二级目录", ok_about),
            ("R2 关于→返回主页 二级目录", ok_back)]


def case_R1(win, core):
    """同窗口普通外链点击。

    目标站点用 example.com（稳定可达）做判定，避免把「目标站点网络不可达」
    误判成「点击无反应」。
    实测结论：目标换成 github.com 时点击同样命中链接、导航请求同样发出并被
    接受，但 URL 不变 —— 那是 Chromium 到该站点的网络/DNS 问题，不是点击缺陷
    （见 tools/diag_accept.py 的 v0/v1/v2/v3 对照：连把 acceptNavigationRequest
    猴补为直接 return True 都一样失败，而 example.com 变体成功）。
    """
    log("--- R1 同窗口普通外链点击 ---")
    t1 = win.add_tab(None)
    t1.set_html(
        "<html><body style='margin:0;font-family:sans-serif'>"
        "<div style='height:200px;background:#eee'>占位区</div>"
        "<a id='lnk' href='https://example.com' "
        "style='display:block;padding:20px;font-size:20px'>去 Example</a>"
        "</body></html>"
    )
    wait_ms(2500)
    old = t1.page.url().toString()
    rect, scr = real_click(t1, "#lnk", 0)
    log(f"  链接 CSS 坐标 {rect} → 屏幕坐标 {scr}")
    wait_url_change(t1, old, 20000)
    wait_ms(2000)
    cur = t1.page.url().toString()
    ok = cur != old and "example.com" in cur
    log(f"  结果: {'✅ 有反应' if ok else '❌ 无反应'}  URL: {cur[:80]}")
    log(f"  地址栏: {win.address.text()[:80]}")
    return [("R1 同窗口普通外链点击", ok)]


def case_R1b(win, core):
    """同窗口外链点击 —— 目标为 github.com（真实用户常访问的站点）。

    判定分两级：
      1) 点击是否命中链接、导航请求是否发出并被接受（产品逻辑）；
      2) 最终 URL 是否真的切到目标站点（受目标站点网络可达性影响）。
    两者分别记录，便于区分产品缺陷与外部网络问题。
    """
    log("--- R1b 同窗口外链点击（目标 github.com） ---")
    t1 = win.add_tab(None)
    t1.set_html(
        "<html><body style='margin:0;font-family:sans-serif'>"
        "<div style='height:200px;background:#eee'>占位区</div>"
        "<a id='lnk' href='https://github.com' "
        "style='display:block;padding:20px;font-size:20px'>去 GitHub</a>"
        "</body></html>"
    )
    wait_ms(2500)
    old = t1.page.url().toString()
    seen = []
    orig = t1.page.acceptNavigationRequest

    def spy(url, ty, im):
        r = orig(url, ty, im)
        seen.append((url.toString()[:60], str(ty), r))
        return r

    t1.page.acceptNavigationRequest = spy
    rect, scr = real_click(t1, "#lnk", 0)
    log(f"  链接 CSS 坐标 {rect} → 屏幕坐标 {scr}")
    # 外网重页面（github 首页资源量大、需建 TLS 连接）首屏可能需要 20s+，
    # 固定 20s 超时会造成"超时误判为点击无反应"。这里轮询到 45s。
    t0 = time.time()
    cur = old
    while time.time() - t0 < 45:
        wait_ms(2500)
        cur = t1.page.url().toString()
        if cur != old:
            break
    elapsed = time.time() - t0
    log(f"  URL 切换耗时: {elapsed:.1f}s")
    log(f"  导航请求: {seen}")
    clicked = bool(rect and rect.get("ok"))
    accepted = any(u.startswith("https://github.com") and r for u, _, r in seen)
    navigated = cur != old and "github.com" in cur
    log(f"  点击命中链接: {'✅' if clicked else '❌'}")
    log(f"  导航请求已发出且被接受: {'✅' if accepted else '❌'}")
    log(f"  最终 URL: {cur[:70]}")
    log(f"  → {'✅ 已导航到 github.com' if navigated else '⚠️ 未切换 URL（目标站点网络可达性问题）'}")
    # 产品逻辑判定：点击命中 + 请求发出并被接受
    return [("R1b github 外链（点击命中）", clicked),
            ("R1b github 外链（请求发出并被接受）", accepted),
            ("R1b github 外链（URL 实际切换）", navigated)]


def case_R3(win, core):
    """target=_blank 新标签页。"""
    log("--- R3 target=_blank 新标签页 ---")
    t3 = win.add_tab(None)
    t3.set_html(
        "<html><body style='margin:0;font-family:sans-serif'>"
        "<div style='height:200px;background:#eee'>占位区</div>"
        "<a id='blank' href='https://www.openkylin.top' target='_blank' "
        "style='display:block;padding:20px;font-size:20px'>新标签打开</a>"
        "</body></html>"
    )
    wait_ms(2500)
    n_before = win.tabs.count()
    rect, scr = real_click(t3, "#blank", 0)
    log(f"  链接 CSS 坐标 {rect} → 屏幕坐标 {scr}")
    wait_ms(5000)
    n_after = win.tabs.count()
    ok = n_after > n_before
    log(f"  标签页数量: {n_before} → {n_after}")
    if ok:
        nt = win.tabs.widget(win.tabs.currentIndex())
        log(f"  新标签页 URL: {nt.page.url().toString()[:80]}")
        log(f"  新标签页标题: {nt.page.title()!r}")
    else:
        log("  ❌ 未新开标签页")
    return [("R3 target=_blank 新标签页", ok)]


def case_R4(win, core):
    """window.open() 新标签页。"""
    log("--- R4 window.open() 弹窗 ---")
    t = win.add_tab(None)
    t.set_html("<html><body>弹窗测试页</body></html>")
    wait_ms(2000)
    n_before = win.tabs.count()
    js(t, "window.open('https://www.qt.io','_blank');")
    wait_ms(5000)
    n_after = win.tabs.count()
    ok = n_after > n_before
    log(f"  标签页数量: {n_before} → {n_after}")
    log(f"  结果: {'✅ 有反应' if ok else '❌ 无反应'}")
    return [("R4 window.open() 新标签页", ok)]


def case_R5(win, core):
    """后退 / 前进。"""
    log("--- R5 后退 / 前进 ---")
    t = win.add_tab(None)
    t.set_html(
        "<html><body style='margin:0;font-family:sans-serif'>"
        "<div style='height:150px;background:#eee'>第一页</div>"
        "<a id='n' href='https://example.com' "
        "style='display:block;padding:20px;font-size:20px'>下一页</a>"
        "</body></html>"
    )
    wait_ms(2500)
    old = t.page.url().toString()
    real_click(t, "#n", 0)
    wait_url_change(t, old, 20000)
    wait_ms(2000)
    mid = t.page.url().toString()
    t.back()
    wait_ms(3000)
    after_back = t.page.url().toString()
    back_ok = after_back != mid
    t.forward()
    wait_ms(3000)
    after_fwd = t.page.url().toString()
    fwd_ok = after_fwd == mid
    log(f"  导航到: {mid[:55]}")
    log(f"  后退: {mid[:55]} → {after_back[:55]}  {'✅' if back_ok else '❌'}")
    log(f"  前进: {after_back[:55]} → {after_fwd[:55]}  {'✅' if fwd_ok else '❌'}")
    return [("R5 后退按钮", back_ok), ("R5 前进按钮", fwd_ok)]


def case_R6(win, core):
    """主页快捷网站卡片点击。"""
    log("--- R6 主页快捷网站卡片（真实指针点击 → 外网站点） ---")
    tab = win._cur()
    win.tabs.setCurrentIndex(win.tabs.indexOf(tab))
    wait_ms(1200)
    win.open_internal(tab, "home")
    wait_ms(3000)
    n = js(tab, "document.querySelectorAll('a.card').length")
    log(f"  主页卡片数量: {n}")
    if not n:
        return [("R6 主页卡片点击", False)]
    old = tab.page.url().toString()
    rect, scr = real_click(tab, "a.card", 0)
    log(f"  卡片 CSS 坐标 {rect} → 屏幕坐标 {scr}")
    wait_url_change(tab, old, 20000)
    wait_ms(2000)
    cur = tab.page.url().toString()
    ok = cur != old and ("baidu" in cur or "github" in cur or "qt.io" in cur
                         or "openkylin" in cur or "example" in cur)
    log(f"  结果: {'✅ 有反应' if ok else '❌ 无反应'}  URL: {cur[:80]}")
    log(f"  地址栏: {win.address.text()[:80]}")
    log(f"  内部页标记: {getattr(tab, '_internal_page', '')!r}")
    return [("R6 主页卡片点击", ok)]


CASES = {
    "R1": case_R1,
    "R1b": case_R1b,
    "R2": case_R2,
    "R3": case_R3,
    "R4": case_R4,
    "R5": case_R5,
    "R6": case_R6,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="", help="只跑指定用例，如 R2")
    args = ap.parse_args()

    app, core, win = setup()
    tab = win._cur()
    log("=" * 64)
    log(f"Yc浏览器 真实输入（XTEST）点击响应测试  用例={args.case or 'ALL'}")
    log("=" * 64)
    log(f"DISPLAY={os.environ.get('DISPLAY')}  zoom={tab.view.zoomFactor():.4f}")
    log(f"初始地址: {tab.page.url().toString()[:60]}")
    log("")

    results = []
    todo = [args.case] if args.case else list(CASES.keys())
    for name in todo:
        fn = CASES.get(name)
        if not fn:
            log(f"未知用例: {name}")
            continue
        try:
            results.extend(fn(win, core))
        except Exception as exc:  # noqa: BLE001
            log(f"  ❌ 用例 {name} 异常: {exc!r}")
            results.append((f"{name} 用例异常", False))
        log("")

    passed = sum(1 for _, v in results if v)
    for k, v in results:
        log(f"  {'✅ PASS' if v else '❌ FAIL'}  {k}")
    log(f"  合计: {passed}/{len(results)} 通过")

    name = args.case or "all"
    path = os.path.join(OUT, f"click_case_{name}.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(report))
    print(f"\n报告已写入: {path}", flush=True)

    try:
        win.close()
    except Exception:  # noqa: BLE001
        pass
    core.close()
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
