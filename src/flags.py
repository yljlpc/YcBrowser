"""自适应 Chromium 运行参数。

目标：
- 真实桌面（非 root、有 DISPLAY、非容器）：不关闭 GPU，让 QtWebEngine 走 GPU 加速渲染，
  启动与翻页明显更快；
- 沙箱 / 容器 / 无显示环境：退回软件渲染并关闭沙箱（避免子进程直接崩溃）。

环境变量 OMNIBROWSER_CHROMIUM_FLAGS 可完全覆盖本逻辑。
"""
import os
import sys


def _in_restricted_env():
    """root 或容器内运行，需要 --no-sandbox 并更保守。"""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return True
    if os.path.exists("/.dockerenv"):
        return True
    if os.environ.get("container"):
        return True
    return False


def _is_offscreen():
    qpa = os.environ.get("QT_QPA_PLATFORM", "")
    if qpa == "offscreen":
        return True
    if qpa and qpa != "offscreen":
        return False
    # Windows 默认就是桌面环境，没有 DISPLAY 是正常现象，不应误判为离屏。
    if sys.platform == "win32":
        return False
    # Linux/macOS：既无 X11 也无 Wayland 显示，才是离屏（无头）环境。
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return True
    return False


def chromium_flags():
    env = os.environ.get("OMNIBROWSER_CHROMIUM_FLAGS")
    if env:
        return env
    flags = []
    if _in_restricted_env():
        # 受限环境：关闭沙箱，并改用 /tmp 而非 /dev/shm，避免崩溃。
        flags += ["--no-sandbox", "--disable-dev-shm-usage"]
    if _is_offscreen():
        # 无头：软件渲染（避免 GPU 探测报错，且离屏本就无 GPU 收益）。
        flags += ["--disable-gpu", "--disable-software-rasterizer"]
    # 真实桌面：不加 --disable-gpu，QtWebEngine 自动走 GPU 加速合成。
    return " ".join(flags)


if __name__ == "__main__":
    print(chromium_flags())
