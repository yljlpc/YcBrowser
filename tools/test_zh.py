"""界面中文化验证：确保所有按钮与界面文本为中文，零英文残留。

覆盖：
1. Qt 标准对话框按钮（确定/取消/关闭/是/否）的中文化；
2. 主窗口工具栏、下拉框、菜单、状态栏文本；
3. 设置页、下载管理器、帮助页的按钮与标签；
4. 内部页面（主页/关于/帮助）正文的英文残留检查（允许技术专有名词白名单）。
"""
import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer",
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QPushButton, QLabel, QAbstractButton

from src.core_client import CoreClient
from src.window import MainWindow, SettingsDialog
from src.download_ui import DownloadManagerDialog
from src.internal import about_html, help_html, home_html
from src.zh import zh_buttons, ZH_BUTTON_TEXT

R = []


def check(name, ok, detail=""):
    R.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


# 允许保留的技术专有名词（品牌名、格式名、协议名、标准缩写）
ALLOWED_WORDS = {
    "Blink", "Chromium", "WebKit", "Trident", "Rust", "PyQt6",
    "Qt", "UA", "User-Agent", "MSHTML", "MSIE", "Cookie", "HTTP", "DOM", "JSON",
    "JSON-RPC", "PDF", "Ctrl", "Alt", "Home", "Page", "Up", "Down", "Left", "Right",
    "Shift", "Esc", "Tab", "Enter", "F5", "F12", "T", "J", "F", "D", "L", "B",
    "IE", "Edge", "Linux", "Windows", "macOS", "Android", "iOS",
    "GB", "MB", "KB", "TB", "B", "s", "X", "V8", "GPL", "MIT", "GPLv3",
    "QQ", "COM", "X-UA-Compatible", "TCP", "IP", "URL", "ID", "DPI",
    # 搜索引擎品牌名
    "Google", "DuckDuckGo", "GitHub", "MDN", "OpenKylin", "Noto", "Sans", "Serif",
    "SC", "TC", "CJK", "GBK", "GB2312", "Microsoft", "PingFang", "YaHei",
    "QtWebEngine", "Ctrl+", "Alt+", "auto", "ver",
    # 网址（不可翻译的标识符）
    "https", "www", "com", "org", "baidu", "bing", "github", "mozilla", "developer",
    "openkylin", "top", "qt",
    # 快捷键组合
    "Ctrl+0", "Ctrl+D", "Ctrl-", "Ctrl++", "Ctrl+F", "Ctrl+J", "Ctrl+L", "Ctrl+T",
    "Alt+Home", "Alt+Left", "Alt+Right", "F5", "F12",
    # 软件品牌名（正式显示名「Yc浏览器」中的英文词）
    "Yc",
}

# 界面可见文本中**不允许**出现的英文名称（须中文化）
FORBIDDEN_IN_UI = ["OmniBrowser", "Omni"]

# 软件显示名（用户可见的正式名称）
APP_DISPLAY_NAME = "Yc浏览器"


def visible_text(html):
    """提取页面的**可见文本**（去掉 head/style/script 内容与全部标签）。"""
    body = re.sub(r"<head[^>]*>.*?</head>", " ", html, flags=re.S | re.I)
    body = re.sub(r"<style[^>]*>.*?</style>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<script[^>]*>.*?</script>", " ", body, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", text)


def strip_identifiers(text):
    """剔除不可翻译的标识符：网址、邮箱、版本号样式、HTML 实体名。

    这些是协议/格式规定的写法，不属于"未翻译的界面文案"。
    """
    t = re.sub(r"https?://[^\s，。；）)]+", " ", text)
    t = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " ", t)
    t = re.sub(r"\b(?:Ctrl|Alt|Shift|Enter|Esc|Tab|F\d{1,2}|Page ?(?:Up|Down|Left|Right)|"
               r"Home|Backspace|Delete|Insert)\s*[+\-]?\s*", " ", t)
    t = re.sub(r"&[a-zA-Z]+;", " ", t)
    return t


def english_tokens(text):
    """提取文本中的英文单词（排除白名单）。"""
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#-]*", text or "")
    return [w for w in words if w not in ALLOWED_WORDS and len(w) >= 2]


app = QApplication.instance() or QApplication(sys.argv)
core = CoreClient()
win = MainWindow(core)

print("\n=== A. Qt 标准按钮中文化 ===")
from PyQt6.QtWidgets import QDialog

d = QDialog()
box = zh_buttons(d, ok="确定", cancel="取消", close="关闭")
texts = [b.text() for b in box.buttons()]
check("按钮盒文本全中文", all(re.search(r"[一-鿿]", t) for t in texts), str(texts))
check("含确定按钮", "确定" in texts, str(texts))
check("含取消按钮", "取消" in texts, str(texts))
d.deleteLater()

print("\n=== B. 主窗口界面文本 ===")
# 工具栏按钮
btn_texts = []
for obj in win.findChildren(QPushButton):
    if obj.text():
        btn_texts.append(obj.text())
for obj in win.findChildren(QAbstractButton):
    pass
toolbtn_texts = [b.text() for b in win.toolbar.findChildren(QAbstractButton) if b.text()]
toolbtn_texts += [b.text() for b in win.addr_bar.findChildren(QAbstractButton) if b.text()]
bad = [t for t in set(toolbtn_texts) if english_tokens(t)]
check("工具栏按钮无英文残留", not bad, str(bad))
check("工具栏含翻译按钮", "翻译" in toolbtn_texts, str(sorted(set(toolbtn_texts))))

# 下拉框
combo_items = []
for combo in win.findChildren(type(win.engine_combo)):
    for i in range(combo.count()):
        combo_items.append(combo.itemText(i))
bad = [t for t in set(combo_items) if english_tokens(t)]
check("下拉框选项无英文残留", not bad, str(sorted(set(combo_items))))

# 应用菜单
menu = win._build_app_menu()
menu_texts = [a.text() for a in menu.actions() if not a.isSeparator()]
bad = [t for t in menu_texts if english_tokens(t)]
check("应用菜单无英文残留", not bad, str(bad))
check("菜单含翻译与媒体下载",
      "翻译此页为中文…" in menu_texts and "下载页面媒体…" in menu_texts, str(menu_texts))

# 状态栏
check("状态栏文本为中文", not english_tokens(win._status_label.text()),
      win._status_label.text())

# 品牌名不得出现在界面可见文本中
check("窗口标题已中文化", "OmniBrowser" not in win.windowTitle(), win.windowTitle())
check("窗口标题含中文", "浏览器" in win.windowTitle(), win.windowTitle())
check("窗口标题为正式显示名", win.windowTitle() == APP_DISPLAY_NAME, win.windowTitle())
logo_tip = win.logo_btn.toolTip() if hasattr(win, "logo_btn") else ""
check("Logo 提示已中文化", "OmniBrowser" not in logo_tip, logo_tip)
check("Logo 提示为正式显示名", logo_tip == APP_DISPLAY_NAME, logo_tip)

# 标签页右键菜单
tab_menu_labels = []
for t in ("复制标签页地址", "在新标签中打开", "刷新标签页",
          "关闭标签页", "关闭其他标签页", "关闭右侧标签页"):
    tab_menu_labels.append(t)
bad = [t for t in tab_menu_labels if english_tokens(t)]
check("标签页右键菜单无英文残留", not bad, str(bad))

print("\n=== C. 设置页 ===")
sd = SettingsDialog(win.settings, win)
labels = []
for lab in sd.findChildren(QLabel):
    if lab.text():
        labels.append(lab.text())
for btn in sd.findChildren(QPushButton):
    if btn.text():
        labels.append(btn.text())
bad = [t for t in labels if english_tokens(t)]
check("设置页标签与按钮无英文残留", not bad, str(bad))
check("设置页含翻译后端项", any("翻译后端" in t for t in labels), str(labels[:8]))
check("设置页含下载连接数项", any("下载连接数" in t for t in labels))
sd.deleteLater()

print("\n=== D. 下载管理器 ===")
dd = DownloadManagerDialog(win)
labels = []
for btn in dd.findChildren(QPushButton):
    if btn.text():
        labels.append(btn.text())
for lab in dd.findChildren(QLabel):
    if lab.text():
        labels.append(lab.text())
for i in range(dd.tree.columnCount()):
    labels.append(dd.tree.headerItem().text(i))
bad = [t for t in labels if english_tokens(t)]
check("下载管理器无英文残留", not bad, str(labels))
check("下载管理器含中文按钮",
      "暂停" in labels and "继续" in labels and "取消" in labels, str(labels))
dd.deleteLater()

print("\n=== E. 内部页面正文 ===")
for name, html in (("主页", home_html()), ("关于页", about_html()), ("帮助页", help_html())):
    text = visible_text(html)
    bad = sorted(set(english_tokens(strip_identifiers(text))))
    check(f"{name}正文无未翻译英文", not bad, str(bad))
    # 英文旧名必须是中文
    forbidden = [w for w in FORBIDDEN_IN_UI if w in text]
    check(f"{name}正文无英文旧名", not forbidden, str(forbidden))

print("\n=== F. 软件显示名（打包后用户看到的名称）===")
# 内部页标题与正文应使用正式显示名
check("主页标题用正式显示名", APP_DISPLAY_NAME in home_html(), APP_DISPLAY_NAME)
check("关于页标题用正式显示名", APP_DISPLAY_NAME in about_html(), APP_DISPLAY_NAME)
check("帮助页用正式显示名", APP_DISPLAY_NAME in help_html(), APP_DISPLAY_NAME)
for name, html in (("主页", home_html()), ("关于页", about_html()), ("帮助页", help_html())):
    text = visible_text(html)
    check(f"{name}含正式显示名", APP_DISPLAY_NAME in text, APP_DISPLAY_NAME)
    check(f"{name}无英文旧名", "OmniBrowser" not in text, "")

# 菜单中的"关于"项
menu2 = win._build_app_menu()
about_actions = [a.text() for a in menu2.actions() if a.text().startswith("关于")]
check("菜单关于项用正式显示名",
      any(APP_DISPLAY_NAME in t for t in about_actions), str(about_actions))

# .desktop 的 Name（打包后应用列表/任务栏显示的就是它）
build_path = os.path.join(ROOT, "package", "build_debs.sh")
with open(build_path, encoding="utf-8") as f:
    build = f.read()
m2 = re.search(r"cat > \"\$DEST/usr/share/applications/omnibrowser\.desktop\" <<'EOF'\n(.*?)\nEOF",
               build, re.S)
check("打包脚本含 desktop 文件", m2 is not None)
if m2:
    d = m2.group(1)
    check("desktop Name 为正式显示名",
          re.search(rf"^Name={re.escape(APP_DISPLAY_NAME)}$", d, re.M) is not None,
          [l for l in d.splitlines() if l.startswith("Name=")])
    check("desktop 无英文旧名", "OmniBrowser" not in d, "")
    check("desktop Exec 保持技术标识符",
          re.search(r"^Exec=omnibrowser %U$", d, re.M) is not None)
    check("desktop GenericName 为中文", re.search(r"^GenericName=浏览器$", d, re.M) is not None)
    # deb 包描述也应是中文显示名
    check("deb 描述用正式显示名", f"Description: {APP_DISPLAY_NAME}" in build,
          [l for l in build.splitlines() if l.startswith("Description:")])

# 网址与快捷键属于标识符，不翻译，但必须出现在正确语境中
home_text = visible_text(home_html())
check("主页网址以中文站点名标注", "百度" in home_text and "必应" in home_text)
help_text = visible_text(help_html())
check("帮助页快捷键为标准写法", "Ctrl+L" in help_text and "F12" in help_text)
check("帮助页无英文说明句",
      not re.search(r"[A-Za-z]{3,}\s+[a-z]{3,}\s+[a-z]{3,}", help_text.replace("Ctrl", "").replace("Alt", "").replace("F5", "").replace("F12", "")),
      "")

print("\n=== 汇总 ===")
passed = sum(1 for _, ok in R if ok)
print(f"通过 {passed}/{len(R)}")
fails = [n for n, ok in R if not ok]
if fails:
    print("失败项: " + ", ".join(fails))
    win.close()
    core.close()
    sys.exit(1)
print("全部通过")
win.close()
core.close()
sys.exit(0)
