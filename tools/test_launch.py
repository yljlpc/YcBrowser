"""启动链路验证：确保安装后点击桌面图标能真正拉起程序。

这是"点击图标没反应"问题的回归测试。覆盖：
1. 启动器脚本的路径推导正确（不依赖 dirname "$0"，避免推算出 /usr）；
2. 启动器能正确定位 src 包、Rust 核心与私有 PyQt6 绑定；
3. .desktop 文件字段完整（Exec/TryExec/Icon/Name），且 StartupNotify 关闭
   （否则启动失败会完全静默）；
4. 实际用启动器拉起程序，进程能存活（窗口创建成功）。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

R = []


def check(name, ok, detail=""):
    R.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


LAUNCHER = os.path.join(ROOT, "installer", "omnibrowser-launch.sh")
BUILD = os.path.join(ROOT, "package", "build_debs.sh")

print("\n=== A. 启动器脚本静态检查 ===")
with open(LAUNCHER, encoding="utf-8") as f:
    sh = f.read()

check("启动器存在", os.path.isfile(LAUNCHER))
check("使用固定安装路径 /opt/omnibrowser", "/opt/omnibrowser" in sh)
check("不用 dirname 推算安装目录",
      not re.search(r'DIR="\$\(cd "\$\(dirname "\$0\)', sh),
      "否则会推算出 /usr 导致 No module named src.main")
check("支持 OMNIBROWSER_HOME 覆盖", "OMNIBROWSER_HOME" in sh)
check("设置私有 PyQt6 的 PYTHONPATH", "dist-packages" in sh and "PYTHONPATH" in sh)
check("设置 Rust 核心路径", "OMNIBROWSER_CORE" in sh)
check("探测 Python 解释器", "command -v" in sh)
check("失败时输出原因并非零退出", "exit 1" in sh and ">&2" in sh)

print("\n=== B. .desktop 文件检查 ===")
with open(BUILD, encoding="utf-8") as f:
    build = f.read()
m = re.search(r"cat > \"\$DEST/usr/share/applications/omnibrowser\.desktop\" <<'EOF'\n(.*?)\nEOF",
              build, re.S)
check("打包脚本含 desktop 文件", m is not None)
if m:
    d = m.group(1)
    check("含 Exec 行", re.search(r"^Exec=omnibrowser %U$", d, re.M) is not None)
    check("含 TryExec（图标缺失时桌面能提示）",
          re.search(r"^TryExec=omnibrowser$", d, re.M) is not None)
    check("含 Icon 行", re.search(r"^Icon=omnibrowser$", d, re.M) is not None)
    check("含中文名称", "Name=Yc浏览器" in d)
    check("显示名为 Yc浏览器", re.search(r"^Name=Yc浏览器$", d, re.M) is not None)
    check("无英文旧名", "OmniBrowser" not in d)
    check("关闭 StartupNotify（失败不再静默）",
          re.search(r"^StartupNotify=false$", d, re.M) is not None)
    check("声明为浏览器类别", "Categories=Network;WebBrowser;" in d)

print("\n=== C. 模拟安装布局并真实启动 ===")
# 用解包的 deb 模拟安装后布局
deb = os.path.join(ROOT, "package", "omnibrowser_1.1.0_amd64.deb")
# 暂存目录必须放在容量充足的分区（/tmp 常是 10MB tmpfs，放不下安装布局）
STAGE_ROOT = os.environ.get("OMNIBROWSER_TMP") or os.path.join(
    os.path.expanduser("~"), ".cache", "omnibrowser-test")
os.makedirs(STAGE_ROOT, exist_ok=True)
stage = tempfile.mkdtemp(prefix="omni_launch_", dir=STAGE_ROOT)
have_deb = False
if os.path.isfile(deb):
    subprocess.run(["dpkg-deb", "-x", deb, stage], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    have_deb = os.path.isdir(os.path.join(stage, "opt", "omnibrowser", "src"))
if not have_deb:
    # 退而用源码目录模拟（结构一致：src/ 在 HOME 下）
    home = os.path.join(stage, "opt", "omnibrowser")
    os.makedirs(home, exist_ok=True)
    shutil.copytree(os.path.join(ROOT, "src"), os.path.join(home, "src"),
                    dirs_exist_ok=True)
    core = os.path.join(ROOT, "core", "target", "release", "omnibrowser-core")
    if os.path.isfile(core):
        shutil.copy2(core, os.path.join(home, "omnibrowser-core"))
        os.chmod(os.path.join(home, "omnibrowser-core"), 0o755)

launcher = os.path.join(stage, "usr", "bin", "omnibrowser")
os.makedirs(os.path.dirname(launcher), exist_ok=True)
shutil.copy2(LAUNCHER, launcher)
os.chmod(launcher, 0o755)
home_dir = os.path.join(stage, "opt", "omnibrowser")

# 启动器在 /usr/bin 之外时，OMNIBROWSER_HOME 必须生效
env = dict(os.environ)
env["OMNIBROWSER_HOME"] = home_dir
env.setdefault("QT_QPA_PLATFORM", "offscreen")
env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-gpu --disable-dev-shm-usage"

proc = subprocess.Popen([launcher], env=env, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True)
time.sleep(10)
alive = proc.poll() is None
check("启动器拉起的进程存活（窗口已创建）", alive,
      "进程已退出" if not alive else "")
if not alive:
    try:
        out = proc.stdout.read()[:800]
    except Exception:  # noqa: BLE001
        out = ""
    check("失败时无 Python 导入错误",
          "No module named" not in out and "ModuleNotFoundError" not in out, out[:200])
    check("失败时无 src 路径错误", "src.main" not in out, out[:200])
else:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        proc.kill()
    check("启动无 src 导入错误", True)

print("\n=== D. 启动器在异常环境下的报错友好性 ===")
bad_env = dict(os.environ)
bad_env["OMNIBROWSER_HOME"] = "/nonexistent/omnibrowser"
r = subprocess.run([launcher], env=bad_env, capture_output=True, text=True, timeout=30)
check("路径缺失时返回非零码", r.returncode != 0, f"rc={r.returncode}")
check("路径缺失时输出中文原因",
      "缺少" in r.stderr or "不存在" in r.stderr, r.stderr.strip()[:120])

print("\n=== E. 点击响应速度 ===")
# 独立进程测响应耗时：既不污染主进程状态，也贴近真实点击
resp_script = os.path.join(ROOT, "tools", "measure_response.py")
if os.path.isfile(resp_script):
    env2 = dict(os.environ)
    env2["QT_QPA_PLATFORM"] = "offscreen"
    env2["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-gpu --disable-dev-shm-usage"
    env2["PYTHONPATH"] = ROOT + os.pathsep + env2.get("PYTHONPATH", "")
    rr = subprocess.run([sys.executable, resp_script], env=env2,
                        capture_output=True, text=True, timeout=300)
    vals = {}
    for line in rr.stdout.splitlines():
        if line.startswith("RESP:"):
            name, _, v = line[5:].partition("=")
            try:
                vals[name] = float(v)
            except ValueError:
                pass
    check("响应耗时测量成功", len(vals) >= 8, f"测得 {len(vals)} 项")
    slow = [f"{k}={v:.0f}ms" for k, v in vals.items() if v > 100]
    check("无超过 100ms 的慢操作", not slow, "; ".join(slow))
    # 关键路径：新标签按钮应走复用逻辑，明显快于强制新建
    if "新标签" in vals and "新标签(强制新建)" in vals:
        check("新标签按钮已走复用优化",
              vals["新标签"] < vals["新标签(强制新建)"],
              f"{vals['新标签']:.1f}ms vs {vals['新标签(强制新建)']:.1f}ms")
    check("测量脚本无异常退出", rr.returncode == 0,
          rr.stderr[-200:] if rr.returncode else "")

print("\n=== F. 历史记录防抖（性能优化不能丢数据）===")
deb_script = os.path.join(ROOT, "tools", "test_debounce.py")
if os.path.isfile(deb_script):
    env3 = dict(os.environ)
    env3["QT_QPA_PLATFORM"] = "offscreen"
    env3["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-gpu --disable-dev-shm-usage"
    r3 = subprocess.run([sys.executable, deb_script], env=env3,
                        capture_output=True, text=True, timeout=180)
    line = [l for l in r3.stdout.splitlines() if l.startswith("DEB:")]
    if line:
        added, mem, now, after, closed = map(int, line[0][4:].split(","))
        check("历史新增 5 条", added == 5, f"added={added}")
        check("防抖生效（未每次都写盘）", now < mem, f"立即={now} 内存={mem}")
        check("防抖窗口后全部落盘", after == mem, f"落盘={after} 内存={mem}")
        # 关闭时又推入 1 条，closeEvent 应把它也落盘 → 关闭后 = 内存 + 1
        check("关闭窗口时立即落盘（含最后一条）", closed == mem + 1,
              f"关闭后={closed} 应为 {mem + 1}")
    else:
        check("防抖脚本可运行", False, r3.stderr[-200:])

print("\n=== 汇总 ===")
passed = sum(1 for _, ok in R if ok)
print(f"通过 {passed}/{len(R)}")
fails = [n for n, ok in R if not ok]
if fails:
    print("失败项: " + ", ".join(fails))
    shutil.rmtree(stage, ignore_errors=True)
    sys.exit(1)
print("全部通过")
shutil.rmtree(stage, ignore_errors=True)
sys.exit(0)
