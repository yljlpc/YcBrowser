#!/usr/bin/env python3
"""Windows 11 构建脚本：在 Windows 上构建 Yc浏览器 并适配 Win11。

前置（在 Windows 上执行）：
    pip install pyinstaller PyQt6 PyQt6-WebEngine
    # Rust 工具链已安装（cargo），用于编译 omnibrowser-core.exe
    # NSIS 已安装：winget install NSIS.NSIS

产出：
    dist/OmniBrowser/                          -- 便携程序（PyInstaller one-folder）
    installer/Yc浏览器-Windows11-<版本>-setup.exe -- 安装包（NSIS）

设计要点：
- 便携程序的构建复用 installer/build_windows.py（PyInstaller 阶段只有一份实现，
  避免两份命令参数各自漂移）。
- 安装包使用 installer/omnibrowser_win11.nsi（Win11 专用：DPI 感知、
  ManifestSupportedOS WIN11、透明度、任务栏固定等）。
- 版本号唯一来源是 src/version.py，与 Linux 打包、关于页保持一致。
"""
import os
import re
import shutil
import subprocess
import sys
import argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
INSTALLER = os.path.join(ROOT, "installer")
NSI = os.path.join(INSTALLER, "omnibrowser_win11.nsi")


def read_version():
    """从 src/version.py 读取版本号（与 Linux 打包、关于页保持唯一来源）。"""
    with open(os.path.join(ROOT, "src", "version.py"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("VERSION"):
                return line.split('"')[1]
    return "0.0.0"


def bump_version():
    """自动递增版本号（修订号 +1）。"""
    bump_script = os.path.join(ROOT, "tools", "bump_version.py")
    if not os.path.isfile(bump_script):
        print("警告：找不到版本递增脚本", bump_script)
        return
    print("==> 自动递增版本号...")
    subprocess.check_call([sys.executable, bump_script], cwd=ROOT)


def find_makensis():
    """定位 makensis.exe（NSIS 编译器）。"""
    exe = shutil.which("makensis")
    if exe:
        return exe
    for base in (
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        r"C:\Program Files (x86)",
        r"C:\Program Files",
    ):
        for sub in ("NSIS", "NSIS 3", "nsis"):
            cand = os.path.join(base, sub, "makensis.exe")
            if os.path.isfile(cand):
                return cand
    return None


def build_portable(auto_bump):
    """调用 installer/build_windows.py 完成 PyInstaller 打包。"""
    print("==> [1/2] 构建便携程序（PyInstaller）...")
    builder = os.path.join(INSTALLER, "build_windows.py")
    cmd = [sys.executable, builder, "--no-installer"]
    if auto_bump:
        cmd.append("--auto-bump")
    subprocess.check_call(cmd, cwd=ROOT)
    return os.path.join(ROOT, "dist", "OmniBrowser")


def build_installer(version):
    """用 NSIS 的 Win11 脚本打成安装包。"""
    print("==> [2/2] 构建 Win11 安装包（NSIS）...")
    makensis = find_makensis()
    if not makensis:
        print("❌ 未找到 NSIS（makensis.exe）。请安装：winget install NSIS.NSIS")
        return None
    if not os.path.isfile(NSI):
        print("❌ 未找到 NSIS 脚本:", NSI)
        return None

    # NSIS 的 Icon / OutFile / File 路径都相对脚本所在目录解析，
    # 因此把 ico 复制到 installer/，并在 installer/ 目录内编译。
    ico_src = os.path.join(ROOT, "assets", "omnibrowser.ico")
    ico_dst = os.path.join(INSTALLER, "omnibrowser.ico")
    if os.path.isfile(ico_src) and not os.path.isfile(ico_dst):
        shutil.copy2(ico_src, ico_dst)

    # 同步版本号（nsi 里是硬编码的）
    with open(NSI, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r'!define VERSION "[^"]*"', f'!define VERSION "{version}"', content)
    with open(NSI, "w", encoding="utf-8") as f:
        f.write(content)

    r = subprocess.run(
        [makensis, os.path.basename(NSI)],
        cwd=INSTALLER,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        print("❌ NSIS 编译失败:")
        print(r.stdout[-3000:])
        print(r.stderr[-2000:])
        return None

    out = os.path.join(INSTALLER, f"Yc浏览器-Windows11-{version}-setup.exe")
    if not os.path.isfile(out):
        cands = [f for f in os.listdir(INSTALLER) if f.endswith("-setup.exe")]
        if cands:
            out = os.path.join(INSTALLER, cands[0])
    return out if os.path.isfile(out) else None


def main():
    parser = argparse.ArgumentParser(description="Windows 11 构建脚本 (Yc浏览器)")
    parser.add_argument("--bump", action="store_true", help="构建前自动递增版本号")
    parser.add_argument("--no-installer", action="store_true", help="只构建便携程序")
    args = parser.parse_args()

    if sys.platform != "win32":
        print("提示：本脚本应在 Windows 上运行以产出 .exe。")
        return 1

    if args.bump:
        bump_version()

    version = read_version()
    print(f"当前版本号: {version}")

    dist = build_portable(False)
    print("便携程序:", dist)

    if args.no_installer:
        return 0

    exe = build_installer(version)
    if not exe:
        print("⚠️ 安装包未生成，便携程序仍可用:", dist)
        return 1

    print(f"\n✅ 安装包创建成功：{exe}")
    print(f"   大小：{os.path.getsize(exe) / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
