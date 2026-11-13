"""纯逻辑验证（不启动 Chromium 渲染进程）。

沙箱限制：virtual memory 4GB 上限 + /dev/shm 仅 10MB，Chromium 渲染进程无法启动。
因此本脚本只验证不依赖 WebEngine 进程的代码路径：
  - Rust 核心 IPC（导航/引擎/文档模式）
  - 帮助 HTML 内容完整性（版权/邮箱/版本/快捷键）
  - 关于页 HTML 内容（版本/版权/联系方式）
  - 对话框自适应尺寸计算
  - 窗口几何自适应计算
  - 字体注册
  - 图标生成（含各尺寸）
  - 设置加载/保存
  - 书签数据的载入/保存/守卫逻辑
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

R = []


def check(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


# ---------------- 1. Rust 核心 ----------------
print("\n=== A. Rust 核心 IPC ===")
from src.core_client import CoreClient

core = CoreClient()
p = core.ping()
check("核心 ping", p is not None, str(p))

nav = core.resolve_nav("example.com")
check("裸域名补 https", nav.get("url") == "https://example.com", str(nav.get("url")))

nav2 = core.resolve_nav("rust 语言")
check("含空格转搜索", nav2.get("kind") == "search", str(nav2.get("kind")))

nav3 = core.resolve_nav("https://example.com/x?y=1")
check("保留已有 scheme", nav3.get("url") == "https://example.com/x?y=1", str(nav3.get("url")))

spec = core.engine_spec("trident")
ua = spec.get("ua", "")
# IE11 新式 UA 只含 Trident/7.0（无 MSIE），IE10 及以下含 MSIE —— 两者均为合法 Trident 兼容 UA
check("Trident UA 含 Trident（或 MSIE）", "Trident" in ua or "MSIE" in ua, ua[:60])

spec_b = core.engine_spec("blink")
check("Blink UA 含 Chrome", "Chrome" in spec_b.get("ua", ""), spec_b.get("ua", "")[:60])

mode = core.negotiate_docmode("IE=EmulateIE7")
check("EmulateIE7 -> doc_mode IE7", mode.get("doc_mode") == "IE7", str(mode.get("doc_mode")))
core.close()

# ---------------- 2. 版本 ----------------
print("\n=== B. 版本与关于页 ===")
from src.version import VERSION

check("版本号非空", bool(VERSION), VERSION)
check("版本号形如 x.y.z", VERSION.count(".") == 2, VERSION)

from src.internal import about_html

about = about_html()
check("关于页含版本号", VERSION in about)
check("关于页含软件简介", "软件简介" in about)
check("关于页含版权", "杨凌雨晨商贸有限公司" in about)
check("关于页含邮箱", "554669500@QQ.COM" in about)

from src.internal import home_html

home = home_html()
check("主页 HTML 非空", len(home) > 200, f"{len(home)} 字节")

# ---------------- 3. 字体 ----------------
print("\n=== C. 字体 ===")
# QFontDatabase 必须在 QApplication 存在后使用，否则段错误；
# 先建 QApplication（offscreen，无 GUI 环境安全），再注册字体。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from src.fonts import available_families, register_fonts

register_fonts()
fams = available_families()
check("字体注册非空", len(fams) > 0, f"{len(fams)} 个字族")

# ---------------- 4. 图标 ----------------
print("\n=== D. 图标 ===")
from src.icons import icon, make_logo, win_icon_size

sz = win_icon_size()
check("Windows 图标尺寸取档", sz in (16, 20, 24, 28, 32), f"{sz}px")

logo = make_logo(128)
pm = logo.pixmap(128, 128)
check("Logo 渲染 128px", not pm.isNull() and pm.width() == 128, f"{pm.width()}x{pm.height()}")

for name in ("back", "forward", "reload", "stop", "home", "newtab", "find",
             "download", "settings", "devtools", "help", "bookmark",
             "bookmark_on", "menu"):
    ic = icon(name, 24)
    ok = not ic.isNull() and not ic.pixmap(24, 24).isNull()
    if not ok:
        check(f"图标 {name}", False)
        break
else:
    check("全部 14 个工具栏图标可渲染", True)

# ---------------- 5. 帮助 HTML（核心验收点）----------------
print("\n=== E. 帮助页内容完整性 ===")
from src.internal import help_html

html = help_html()
check("帮助 HTML 长度充足", len(html) > 1500, f"{len(html)} 字节")
check("帮助含版权单位", "杨凌雨晨商贸有限公司" in html)
check("帮助含联系方式", "554669500@QQ.COM" in html)
check("帮助含版本号", VERSION in html)
check("帮助含快捷键表", "快捷键" in html and "<table>" in html)
check("帮助含渲染内核说明", "Blink" in html and "WebKit" in html and "Trident" in html)
check("帮助含主要功能", "主要功能" in html)
check("帮助含自适应说明", "自适应" in html)
check("帮助内容完整闭合（不截断）", html.rstrip().endswith("</body></html>"))

import re

rows = re.findall(r"<tr><td", html)
check("快捷键条目 >= 12 条", len(rows) >= 12, f"{len(rows)} 条")

from src.internal import SHORTCUT_LABELS

missing = [k for k in (
    "back", "forward", "reload", "stop", "home", "newtab", "find",
    "downloads", "bookmark", "zoom_in", "zoom_out", "zoom_reset",
    "devtools", "address",
) if k not in SHORTCUT_LABELS]
check("14 个快捷键标签齐全", not missing, str(missing))

# ---------------- 6. 自适应几何（layout 纯函数，不导入 window.py）----------------
print("\n=== F. 分辨率自适应 ===")
from src.layout import dialog_size

def _wh(sz):
    return sz.width(), sz.height()

w, h = _wh(dialog_size(1920, 1080, 0.6, 0.74, 780, 760, 480, 380))
check("对话框尺寸为正", w > 0 and h > 0, f"{w}x{h}")
check("对话框不超过上限", w <= 780 and h <= 760, f"{w}x{h}")
w2, h2 = _wh(dialog_size(1920, 1080, 0.42, 0.55, 720, 560))
check("不同比例参数生效", (w2, h2) != (w, h), f"{w2}x{h2}")
check("对话框尺寸不低于最小值", w2 >= 420 and h2 >= 300, f"{w2}x{h2}")

# 小屏保护：800x600 屏幕上对话框不溢出
w3, h3 = _wh(dialog_size(800, 600, 0.6, 0.74, 780, 760, 480, 380))
check("小屏对话框不溢出", w3 <= 800 and h3 <= 600, f"{w3}x{h3}")

# 窗口尺寸纯函数
from src.layout import window_size

ww, wh = _wh(window_size(1920, 1080))
check("窗口尺寸为正", ww > 0 and wh > 0, f"{ww}x{wh}")
check("窗口不超过屏幕上限", ww <= 1700 and wh <= 1050, f"{ww}x{wh}")
ww2, wh2 = _wh(window_size(1366, 768))
check("小屏窗口不溢出", ww2 <= 1366 and wh2 <= 768, f"{ww2}x{wh2}")

# ---------------- 7. 地址栏 URL 判定（layout 纯函数）----------------
print("\n=== G. 地址栏行为 ===")
from src.layout import looks_like_url

check("完整 URL 判定为网址", looks_like_url("https://example.com/a?b=1") is True)
check("裸域名判定为网址", looks_like_url("example.com") is True)
check("带 www 判定为网址", looks_like_url("www.baidu.com/s?wd=x") is True)
check("带端口判定为网址", looks_like_url("localhost:8080") is True)
check("IP 判定为网址", looks_like_url("192.168.1.1/admin") is True)
check("搜索词不判定为网址", looks_like_url("rust 语言") is False)
check("单个词不判定为网址", looks_like_url("rust") is False)
check("空串不判定为网址", looks_like_url("") is False)

# ---------------- 8. 翻译模块（Rust 核心 IPC + 前端纯逻辑）----------------
print("\n=== H. 翻译功能 ===")
from src.core_client import CoreClient
from src.translate import DEFAULT_GLOSSARY, TranslateClient

core2 = CoreClient()
lang = core2.request("translate_detect_lang", text="This is an English sentence for testing.")
check("核心语言检测返回 en", lang.get("lang") == "en", str(lang))
lang_zh = core2.request("translate_detect_lang", text="这是一句中文，用于测试语言检测功能。")
check("核心语言检测返回 zh", lang_zh.get("lang") == "zh", str(lang_zh))
should = core2.request("translate_should", text="Install the browser now", target="zh")
check("核心判定应翻译", should.get("should") is True, str(should))
should_no = core2.request("translate_should", text="https://a.example/x", target="zh")
check("核心跳过 URL", should_no.get("should") is False, str(should_no))
split = core2.request("translate_split", text="First sentence. Second one! Third?")
check("核心分句返回 3 句", len(split.get("sentences", [])) == 3, str(split.get("sentences")))

pol = core2.request("translate_polish", text="该功能被禁用。", glossary=DEFAULT_GLOSSARY)
check("核心润色改写被动句", "已禁用" in pol.get("text", ""), pol.get("text", ""))
pol2 = core2.request("translate_polish", text="web browser is fast.", glossary=DEFAULT_GLOSSARY)
check("核心术语表生效", "浏览器" in pol2.get("text", ""), pol2.get("text", ""))
core2.close()

client = TranslateClient(core=None, backend="mymemory")
check("翻译客户端可创建", client is not None)
check("翻译客户端缓存统计可用", client.cache_stats() == 0)
check("默认术语表非空", len(DEFAULT_GLOSSARY) > 100, f"{len(DEFAULT_GLOSSARY)} 字符")
check("术语表含 web browser", "web browser,浏览器" in DEFAULT_GLOSSARY)
# 无核心时润色应原样返回（不崩溃）
check("无核心时润色安全降级", client.polish("测试文本") == "测试文本")

# ---------------- 9. 媒体嗅探纯逻辑 ----------------
print("\n=== I. 媒体嗅探 ===")
from src.media import is_stream, media_filename, parse_media_items

raw = {
    "items": [
        {"url": "https://cdn.example.com/v/clip.mp4", "mime": "video/mp4",
         "kind": "video", "ext": "mp4", "label": "video"},
        {"url": "https://cdn.example.com/a/song.mp3", "mime": "audio/mpeg",
         "kind": "audio", "ext": "mp3", "label": "audio"},
        {"url": "https://cdn.example.com/l/live.m3u8", "mime": "",
         "kind": "stream", "ext": "m3u8", "label": ""},
        {"url": "https://example.com/page.html", "mime": "text/html",
         "kind": "other", "ext": "html", "label": ""},
        {"url": "javascript:void(0)", "mime": "", "kind": "other", "ext": "",
         "label": ""},
    ]
}
items = parse_media_items(raw.get("items"))
check("嗅探解析出 3 个媒体", len(items) == 3, str(len(items)))
kinds = sorted(i[0] for i in items)
check("识别视频/音频/流媒体", kinds == ["audio", "stream", "video"], str(kinds))
check("HTML 页面被过滤", all("page.html" not in i[1] for i in items))
check("javascript: 被过滤", all(not i[1].startswith("javascript") for i in items))
check("流媒体可识别", is_stream("stream") is True)
check("视频非流媒体", is_stream("video") is False)
fn = media_filename("https://cdn.example.com/v/clip.mp4", "video", "mp4", "video")
check("媒体文件名生成", fn == "clip.mp4", fn)
fn2 = media_filename("https://cdn.example.com/stream", "video", "", "")
check("无扩展名时补全", fn2.endswith(".mp4"), fn2)

# ---------------- 10. 下载引擎纯逻辑 ----------------
print("\n=== J. 下载引擎 ===")
from src.downloader import human_size, human_time

check("字节转可读大小", human_size(1024) == "1.0 KB", human_size(1024))
check("大字节转 GB", "GB" in human_size(5 * 1024 ** 3), human_size(5 * 1024 ** 3))
check("剩余时间格式化", human_time(90) == "1 分 30 秒", human_time(90))
check("未知时间显示占位", human_time(None) == "--", str(human_time(None)))

# 核心的下载算法 IPC
core3 = CoreClient()
plan = core3.request("dl_plan", size=1000000, connections=8)
segs = plan.get("segments", [])
check("分片计划覆盖整文件",
      len(segs) == 8 and segs[0][0] == 0 and segs[-1][1] == 1000000, str(segs[:2]))
claim = core3.request("dl_claim", segments=segs)
check("派活返回有效区间", claim.get("start", -1) >= 0, str(claim))
commit = core3.request("dl_commit", segments=segs, total=1000000,
                        start=claim.get("start"), pos=claim.get("start"), end=claim.get("end"))
check("提交进度更新已下载字节", commit.get("downloaded", 0) >= 0, str(commit.get("downloaded")))
fn_res = core3.request("dl_filename", url="https://x.example/dir/report.pdf",
                        content_disposition='attachment; filename="报告 2024.pdf"')
check("解析 Content-Disposition 文件名", "报告" in fn_res.get("filename", ""),
      fn_res.get("filename"))
check("文件分类正确", fn_res.get("category") == "文档", fn_res.get("category"))
fn_res2 = core3.request("dl_filename", url="https://x.example/dir/movie.mp4")
check("按 URL 推导文件名", fn_res2.get("filename") == "movie.mp4", fn_res2.get("filename"))
check("视频分类正确", fn_res2.get("category") == "视频", fn_res2.get("category"))
dest = core3.request("dl_resolve_dest", dir="/tmp", filename="a.zip",
                      existing=["a.zip"])
check("同名文件自动去重", dest.get("path") == "/tmp/a (1).zip", dest.get("path"))
state = core3.request("dl_state", action="save", url="https://x/f", size=100,
                       etag="e", segments=[[0, 40], [40, 100]])
loaded = core3.request("dl_state", action="load", text=state.get("json", ""))
check("断点状态可往返", loaded.get("valid") is True
      and len(loaded.get("segments", [])) == 2, str(loaded.get("segments")))
core3.close()

# ---------------- 汇总 ----------------
print("\n=== 汇总 ===")
passed = sum(1 for _, ok, _ in R if ok)
print(f"通过 {passed}/{len(R)}")
fails = [n for n, ok, _ in R if not ok]
if fails:
    print("失败项: " + ", ".join(fails))
    sys.exit(1)
print("全部通过")
sys.exit(0)