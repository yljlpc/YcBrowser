"""整页翻译端到端验证：真实网络 + 真实 Blink 渲染 + 真实 DOM 回填。

流程与用户在软件中点击「翻译」按钮时完全一致：
  英文页面 → EXTRACT_JS 提取正文 → 逐句送译（含润色）→ FILL_JS 回填 → 页面显示中文
  → RESTORE_JS 还原为原文。
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer",
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from src.core_client import CoreClient
from src.translate import EXTRACT_JS, FILL_JS, RESTORE_JS, TranslateClient
from src.window import MainWindow

R = []


def check(name, ok, detail=""):
    R.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def wait_ms(ms):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        QApplication.processEvents()
        time.sleep(0.01)


def js(tab, code, timeout=8000):
    """同步执行 JS 并返回结果。"""
    out = {}
    loop = QEventLoop()
    tab.page.runJavaScript(code, lambda v: (out.__setitem__("v", v), loop.quit()))
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    return out.get("v")


app = QApplication.instance() or QApplication(sys.argv)
core = CoreClient()
win = MainWindow(core)

EN_PAGE = """<html><head><title>English Page</title></head><body>
<h1>Welcome to the browser</h1>
<p>Download the browser and install it on your computer.</p>
<p>The installation is finished, so you can open the application now.</p>
<p>This feature was disabled by the administrator.</p>
</body></html>"""

tab = win.add_tab(None)
tab.set_html(EN_PAGE)
wait_ms(1200)

print("\n=== A. 提取英文正文 ===")
items = js(tab, EXTRACT_JS)
check("提取到正文段落", isinstance(items, list) and len(items) >= 3, str(items))

client = TranslateClient(core=core, backend="mymemory", timeout=25)
todo = [t for t in items if client.should_translate(t, "zh")]
check("筛选出需翻译段落", len(todo) >= 3, f"{len(todo)}/{len(items)}")

print("\n=== B. 真实翻译（含润色）===")
pairs = {}
for t in todo:
    try:
        out = client.translate(t, "auto", "zh")
    except Exception as exc:  # noqa: BLE001
        out = ""
        print(f"    翻译失败: {t[:30]} -> {exc}")
    if out:
        pairs[t] = out
        print(f"    {t[:44]}")
        print(f"    → {out}")

check("多数段落翻译成功", len(pairs) >= max(1, len(todo) // 2), f"{len(pairs)}/{len(todo)}")
check("译文含中文", all(any('一' <= c <= '鿿' for c in v) for v in pairs.values()) if pairs else False)
check("译文已去机翻腔（无'已已被'）",
      all("已已被" not in v for v in pairs.values()))

print("\n=== C. 回填页面 ===")
import json
js_code = FILL_JS.replace("__PAIRS__", json.dumps(pairs, ensure_ascii=False))
applied = js(tab, js_code)
check("回填生效（applied>0）", isinstance(applied, int) and applied > 0, str(applied))

body = js(tab, "document.body ? document.body.innerText : ''")
check("页面显示中文", any('一' <= c <= '鿿' for c in (body or "")), (body or "")[:70].replace("\n", " "))
check("页面不再显示英文原文",
      "Welcome to the browser" not in (body or ""), (body or "")[:70].replace("\n", " "))

print("\n=== D. 还原原文 ===")
restored = js(tab, RESTORE_JS)
check("还原生效（restored>0）", isinstance(restored, int) and restored > 0, str(restored))
body2 = js(tab, "document.body ? document.body.innerText : ''")
check("原文已恢复", "Welcome to the browser" in (body2 or ""), (body2 or "")[:70].replace("\n", " "))

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
