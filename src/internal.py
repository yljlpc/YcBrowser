"""内置页面：主页（快速拨号）与关于页。均以 setHtml 渲染。"""

from .version import VERSION

FONT_STACK = '"方正书宋简体","仿宋_GB2312","Noto Sans CJK SC",sans-serif'
HEADING_STACK = '"方正小标宋简体","方正小标宋_GBK","Noto Serif CJK SC",serif'

DIALED_SITES = [
    ("百度", "https://www.baidu.com"),
    ("必应", "https://www.bing.com"),
    ("GitHub", "https://github.com"),
    ("OpenKylin", "https://www.openkylin.top"),
    ("Qt", "https://www.qt.io"),
    ("MDN", "https://developer.mozilla.org"),
]


def home_html(engine_label="Blink"):
    cards = "".join(
        f'<a class="card" href="{url}"><span class="t">{name}</span>'
        f'<span class="u">{url}</span></a>'
        for name, url in DIALED_SITES
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Yc浏览器 主页</title>
<style>
  body {{ font-family:{FONT_STACK}; background:#f6f7f9; color:#1f2329; margin:0;
         display:flex; flex-direction:column; align-items:center; padding:48px 16px; }}
  h1 {{ font-family:{HEADING_STACK}; font-weight:normal; letter-spacing:2px; margin:8px 0 4px; }}
  .sub {{ color:#8a9099; margin-bottom:28px; }}
  .grid {{ display:grid; grid-template-columns:repeat(3, 220px); gap:14px; }}
  .card {{ display:flex; flex-direction:column; text-decoration:none; color:#1f2329;
           background:#fff; border:1px solid #e2e5ea; border-radius:10px; padding:16px 18px; }}
  .card:hover {{ border-color:#2b6cff; }}
  .t {{ font-size:16px; }}
  .u {{ color:#8a9099; font-size:12px; margin-top:4px; }}
</style></head>
<body>
  <h1>Yc浏览器</h1>
  <div class="sub">当前渲染内核：{engine_label} · 在地址栏输入网址或搜索词即可开始</div>
  <div class="grid">{cards}</div>
</body></html>"""


def about_html(version=None):
    version = version or VERSION
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>关于 Yc浏览器</title>
<style>
  body {{ font-family:{FONT_STACK}; background:#f6f7f9; color:#1f2329;
         max-width:760px; margin:0 auto; padding:40px 16px; line-height:1.8; }}
  h1 {{ font-family:{HEADING_STACK}; font-weight:normal; letter-spacing:2px; margin-bottom:2px; }}
  .ver {{ color:#2f6fed; font-size:15px; margin-bottom:18px; }}
  h2 {{ font-family:{HEADING_STACK}; font-weight:normal; font-size:18px;
        border-left:4px solid #2f6fed; padding-left:10px; margin-top:26px; }}
  code {{ background:#eef1f5; padding:1px 6px; border-radius:4px; font-size:13px; }}
  ul {{ margin:6px 0 6px 0; }}
  li {{ margin:4px 0; }}
  .foot {{ color:#8a9099; font-size:13px; margin-top:28px; border-top:1px solid #e2e5ea; padding-top:12px; }}
</style></head>
<body>
  <h1>Yc浏览器</h1>
  <div class="ver">版本 {version} · Yc浏览器</div>

  <h2>软件简介</h2>
  <p>Yc浏览器 是一款以 <b>Blink（QtWebEngine / Chromium）</b> 为渲染核心的
  多功能桌面浏览器，由 <b>Rust 原生核心</b> 负责引擎调度、导航归一化与 Trident 兼容协商，
  前端界面基于 <b>PyQt6（Qt 6）</b> 构建，采用浅色简约风格并随系统分辨率与 DPI 自适应。</p>

  <h2>核心架构</h2>
  <ul>
    <li><b>原生核心（Rust）</b>：零第三方依赖，通过行式 JSON-RPC（逐行 JSON 远程调用）与前端进程通信，
        负责地址解析、搜索引擎拼接、引擎规格与文档模式协商。</li>
    <li><b>渲染前端（PyQt6 / Qt 6）</b>：多标签页、地址栏、查找、下载管理、
        开发者工具、书签、历史、缩放、清除浏览数据等完整功能。</li>
    <li><b>共享持久化配置档</b>：磁盘 HTTP 缓存 + 单网络服务进程，重复访问显著提速。</li>
  </ul>

  <h2>渲染引擎</h2>
  <ul>
    <li><b>Blink（Chromium 内核 + V8 脚本引擎）</b>：默认现代内核。</li>
    <li><b>WebKit 兼容模式</b>：以兼容的浏览器标识（User-Agent）适配老站点。</li>
    <li><b>Trident 兼容</b>：按 <code>X-UA-Compatible</code> 协商文档模式并伪装浏览器标识，
        注入遗留 DOM 垫片让老站点按 IE 语义加载（属兼容模拟，并非原生 MSHTML 内核）。</li>
  </ul>

  <h2>主要特性</h2>
  <ul>
    <li>多标签 / 多引擎实时切换，地址栏历史自动补全。</li>
    <li>页面内查找、下载管理、开发者工具（F12）。</li>
    <li>书签管理（Ctrl+D）、历史记录、清除浏览数据。</li>
    <li>页面缩放（Ctrl+/Ctrl-/Ctrl+0）、按分辨率自适应界面与网页缩放。</li>
    <li><b>实时翻译</b>：整页英译中，术语统一 + 口语化改写，非逐字直译。</li>
    <li><b>高速下载</b>：多连接分片（最多 32 连接）+ 动态再平衡 + 断点续传，
        按类型自动归档，页面媒体可一键嗅探下载。</li>
    <li><b>隐私与输出</b>：无痕窗口（不落盘缓存与 Cookie）、系统打印、导出 PDF。</li>
    <li>22 款随附中文字体，界面与中文网页渲染清晰。</li>
  </ul>

  <div class="foot">提示：Trident 兼容为模拟实现，并非 Windows 原生 MSHTML；
  它通过浏览器标识伪装与 DOM 垫片提供 IE 兼容语义。本软件遵循系统 Qt 6 运行时许可。<br><br>
  <b>版权所有 © 杨凌雨晨商贸有限公司</b> 提供　·　联系邮箱：554669500@QQ.COM</div>
</body></html>"""


# 快捷键的展示文本（纯字符串，不依赖 Qt，便于无 GUI 环境测试与复用）
SHORTCUT_LABELS = {
    "back": "Alt+←",
    "forward": "Alt+→",
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

_HELP_ROWS = [
    ("back", "后退"),
    ("forward", "前进"),
    ("reload", "刷新"),
    ("stop", "停止"),
    ("home", "主页"),
    ("newtab", "新标签"),
    ("find", "页面内查找"),
    ("downloads", "下载管理"),
    ("bookmark", "加入 / 取消收藏"),
    ("zoom_in", "放大"),
    ("zoom_out", "缩小"),
    ("zoom_reset", "重置缩放"),
    ("devtools", "开发者工具"),
    ("address", "聚焦地址栏"),
]


def help_html(version=VERSION):
    """帮助 / 关于对话框的 HTML（可滚动展示，内容完整不截断）。"""
    sc = "".join(
        "<tr><td style='padding:3px 14px;'><b>{}</b></td>"
        "<td style='padding:3px 14px;'>{}</td></tr>".format(
            SHORTCUT_LABELS.get(k, k), label
        )
        for k, label in _HELP_ROWS
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
 body{{font-family:'Microsoft YaHei','PingFang SC','Noto Sans CJK SC',sans-serif;
      font-size:13px;color:#1f2329;line-height:1.7;padding:14px 18px;}}
 h2{{font-size:16px;margin:14px 0 6px;color:#2b6cff;}}
 h3{{font-size:14px;margin:12px 0 4px;}}
 table{{border-collapse:collapse;}}
 td{{border-bottom:1px solid #e6e8eb;}}
 .muted{{color:#6b7280;}}
 .copy{{margin-top:14px;border-top:1px solid #e2e5ea;padding-top:12px;color:#3a3f47;}}
</style></head><body>
<h2>Yc浏览器 帮助 / 关于</h2>
<p>一款以 <b>Rust 原生核心</b> + <b>PyQt6（Qt 6）</b> 构建的多功能桌面浏览器，
渲染核心为 <b>Blink（QtWebEngine）</b>，并提供 WebKit 兼容 UA 与 Trident 兼容模式。</p>

<h3>快捷键</h3>
<table>{sc}</table>

<h3>渲染内核</h3>
<ul>
 <li><b>Blink</b>（Chromium 内核 + V8 脚本引擎）—— 默认现代内核</li>
 <li><b>WebKit</b> —— 兼容 UA 模式</li>
 <li><b>Trident 兼容</b> —— 按 X-UA-Compatible 协商文档模式并伪装 UA</li>
</ul>

<h3>主要功能</h3>
<ul>
 <li>独立地址栏：输入完整网址直接前往且不弹补全；支持历史与搜索建议</li>
 <li>多标签、页面内查找、下载管理、开发者工具（F12）</li>
 <li>书签管理、历史记录、页面缩放、清除浏览数据</li>
 <li>无痕窗口（不写入磁盘缓存与 Cookie）、打印、导出 PDF</li>
 <li>标签页右键：复制地址、在新标签打开、关闭其他 / 关闭右侧</li>
 <li>按主屏分辨率与 DPI 自动调整界面与网页缩放</li>
</ul>

<h3>实时翻译</h3>
<p class="muted">点击工具栏「翻译」或菜单「翻译此页为中文」，即可把英文网页即时译为中文。
译文经过术语统一与口语化改写（去除机翻直译腔、拆分长句、统一标点），
不是逐字硬译。菜单「还原页面原文」可一键还原。目标语言、翻译后端与
自定义术语表可在「设置」中调整。</p>

<h3>高速下载</h3>
<p class="muted">下载采用多连接分片引擎：单个文件最多 32 个连接并行下载，
某连接完成后会立即接手剩余量最大的一段，保证末尾不空转；
服务器不支持分段时自动退化为单线程。下载可暂停、继续、断点续传，
并按类型自动归入「视频 / 音乐 / 程序 / 压缩包 / 文档」目录。
菜单「下载页面媒体」可嗅探页面中的视频与音频直链并直接下载。</p>

<h3>自适应</h3>
<p class="muted">窗口与功能页面随主屏分辨率自动设定大小；界面与网页缩放可在「设置」中微调。</p>

<div class="copy">
 <b>版权所有 © 杨凌雨晨商贸有限公司</b> 提供<br>
 联系邮箱：<a href="mailto:554669500@QQ.COM">554669500@QQ.COM</a><br>
 版本：Yc浏览器 {version}
</div>
</body></html>"""
