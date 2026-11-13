"""按钮点击响应耗时测量：找出拖慢点击的环节。

在真实渲染环境下依次触发工具栏/菜单各项操作，测量耗时，
用于定位"点击没反应/很慢"的具体瓶颈。
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

from PyQt6.QtWidgets import QApplication

from src.core_client import CoreClient
from src.window import MainWindow

app = QApplication.instance() or QApplication(sys.argv)
core = CoreClient()
win = MainWindow(core)
win.resize(1360, 860)
win.show()


def pump(ms=120):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        QApplication.processEvents()
        time.sleep(0.005)


def measure(name, fn, rounds=8):
    """测量单次操作耗时（含事件循环排空）。"""
    fn()  # 预热
    pump(150)
    samples = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        fn()
        QApplication.processEvents()
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    avg = sum(samples) / len(samples)
    print(f"  {name:<28} 平均 {avg:7.2f} ms   中位 {samples[len(samples)//2]:7.2f} ms")
    return avg


pump(400)
print("\n=== 按钮点击响应耗时 ===")
results = {}

results["新标签"] = measure("新标签（按钮真实路径）", lambda: win._new_tab())
results["新标签(强制新建)"] = measure("新标签（强制新建标签页）", lambda: win.add_tab("omni://home"))
results["关闭标签"] = measure("关闭标签", lambda: win.close_tab(win.tabs.count() - 1))
results["后退"] = measure("后退", lambda: win._on_back())
results["前进"] = measure("前进", lambda: win._on_forward())
results["刷新"] = measure("刷新", lambda: win._on_reload())
results["主页"] = measure("主页", lambda: win._go_home())
results["放大"] = measure("放大", lambda: win._zoom_in())
results["缩小"] = measure("缩小", lambda: win._zoom_out())
results["重置缩放"] = measure("重置缩放", lambda: win._zoom_reset())
results["查找栏"] = measure("查找栏开/关", lambda: (win._toggle_find(), win._toggle_find()))
results["收藏"] = measure("收藏切换", lambda: win._add_bookmark())
results["菜单构建"] = measure("构建应用菜单", lambda: win._build_app_menu())
results["菜单弹出"] = measure("弹出应用菜单", lambda: win._open_menu())
results["翻译按钮"] = measure("翻译（内部页快速返回）", lambda: win._translate_page())
results["缩放标签同步"] = measure("apply_ui_scale", lambda: win.apply_ui_scale())

print("\n=== 慢操作（>100ms 视为需优化）===")
slow = {k: v for k, v in results.items() if v > 100}
if slow:
    for k, v in sorted(slow.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v:.1f} ms")
else:
    print("  无（所有操作均 < 100ms）")

print("\n=== 汇总 ===")
tot = sum(results.values())
print(f"  合计 {tot:.1f} ms；最慢：{max(results, key=results.get)} "
      f"({max(results.values()):.1f} ms)")

# 供自动化测试解析：每行 "RESP:<名称>=<毫秒>"
for name, val in results.items():
    print(f"RESP:{name}={val:.2f}")

win.close()
core.close()
sys.exit(0)
