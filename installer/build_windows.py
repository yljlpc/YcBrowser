#!/usr/bin/env python3
"""Windows 构建脚本：在 Windows 上把 OmniBrowser 打包为独立可执行程序。

前置（在 Windows 上执行）：
    pip install pyinstaller PyQt6 PyQt6-WebEngine
    # Rust 工具链已安装（cargo），用于编译 omnibrowser-core.exe

产出：
    dist/OmniBrowser/OmniBrowser.exe  —— 单文件夹、可直接运行的便携程序
    （可用 installer/omnibrowser.nsi 进一步打成安装包 OmniBrowser-<ver>-setup.exe）

设计要点：
- 用 PyInstaller 把 Python 解释器 + PyQt6 + 前端 src + 字体 fonts + Rust 核心 exe 一起打包，
  生成"双击即开"的 Windows 程序，无需用户另装 Python/Qt。
- 通过 --icon 嵌入 assets/omnibrowser.ico，使任务栏 / 资源管理器 / 安装器均显示 Yc 图标（固化）。
- QtWebEngine 的二进制与资源由 PyQt6 的 PyInstaller hook 自动收集（--collect-submodules PyQt6）。
"""
import os
import shutil
import subprocess
import sys
import re
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
SRC = os.path.join(ROOT, "src")
CORE_EXE = os.path.join(ROOT, "core", "target", "release", "omnibrowser-core.exe")
ICO = os.path.join(ASSETS, "omnibrowser.ico")


def _find_font_dir():
    """定位中文字体目录。

    字体不入版本库，构建时按以下顺序回退：
      1. 环境变量 OMNIBROWSER_FONTS 指定的目录；
      2. 仓库根的 fonts/ 目录；
      3. 用户桌面 fonts/ 目录（Linux 构建机上字体所在位置）；
      4. 从已解包的 deb 产物中回收字体。
    找不到时返回 None —— 此时不向 PyInstaller 传 --add-data，
    避免因路径不存在直接失败（Windows 自带中文字体，可正常显示）。
    """
    env = os.environ.get("OMNIBROWSER_FONTS")
    candidates = [
        env,
        os.path.join(ROOT, "fonts"),
        os.path.join(os.path.expanduser("~"), "桌面", "fonts"),
        os.path.join(os.path.expanduser("~"), "Desktop", "fonts"),
    ]
    for d in candidates:
        if d and os.path.isdir(d) and any(
            f.lower().endswith((".ttf", ".otf", ".ttc")) for f in os.listdir(d)
        ):
            return d
    # 最后回退：从 package/ 下已解包的 deb 目录回收字体
    pkg = os.path.join(ROOT, "package")
    if os.path.isdir(pkg):
        for name in sorted(os.listdir(pkg), reverse=True):
            cand = os.path.join(pkg, name, "opt", "omnibrowser", "fonts")
            if os.path.isdir(cand) and any(
                f.lower().endswith((".ttf", ".otf", ".ttc")) for f in os.listdir(cand)
            ):
                return cand
    return None


def read_version():
    """从 src/version.py 读取版本号（与 Linux 打包、关于页保持唯一来源）。"""
    with open(os.path.join(SRC, "version.py"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("VERSION"):
                return line.split('"')[1]
    return "0.0.0"


def bump_version():
    """自动递增版本号（修订号 +1）。"""
    bump_script = os.path.join(ROOT, "tools", "bump_version.py")
    if not os.path.isfile(bump_script):
        print(f"警告：找不到版本递增脚本 {bump_script}")
        return
    print("==> 自动递增版本号...")
    subprocess.check_call([sys.executable, bump_script], cwd=ROOT)


def get_version_with_bump(auto_bump):
    """根据 auto_bump 参数决定是否递增版本号。"""
    if auto_bump:
        bump_version()
    return read_version()


VERSION = get_version_with_bump(False)


def run(cmd, cwd=None):
    print("+", " ".join(cmd), (f"(cwd={cwd})" if cwd else ""))
    subprocess.check_call(cmd, cwd=cwd)


def main():
    parser = argparse.ArgumentParser(description="Windows 构建脚本")
    parser.add_argument(
        "--auto-bump",
        action="store_true",
        help="构建前自动递增版本号（默认修订号 +1）"
    )
    parser.add_argument(
        "--no-installer",
        action="store_true",
        help="只构建便携程序，不生成 NSIS 安装包"
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="对安装包执行 Authenticode 签名"
    )
    args = parser.parse_args()

    # 根据参数决定是否递增版本号
    VERSION = get_version_with_bump(args.auto_bump)

    if sys.platform != "win32":
        print("提示：本脚本应在 Windows 上运行以产出 .exe。当前非 Windows，仅做语法/结构校验。")
    if not os.path.isfile(ICO):
        print("缺少图标 assets/omnibrowser.ico，请先运行 tools/gen_icons.py")
        return 1

    # 1) 编译 Rust 核心（Windows 目标 exe）
    if os.path.isfile(CORE_EXE):
        print("发现已编译核心：", CORE_EXE)
    else:
        print("编译 Rust 核心 ...")
        run(["cargo", "build", "--release"], cwd=os.path.join(ROOT, "core"))

    # 2) 准备 PyInstaller 入口：调用 src.main:main
    #
    # 关键：Rust 核心 exe 被 PyInstaller 收进 _MEIPASS 根目录，而 src/core_client.py
    # 的 _find_binary() 只在「src 同级」和「src/../core/target/release」两处找。
    # 冻结后这两个位置都不对，必须用 OMNIBROWSER_CORE 显式指路（core_client 优先读它）。
    entry = os.path.join(ROOT, "installer", "_win_entry.py")
    with open(entry, "w", encoding="utf-8") as f:
        f.write(
            "import os, sys\n"
            "base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))\n"
            "core = os.path.join(base, 'omnibrowser-core.exe')\n"
            "if os.path.isfile(core):\n"
            "    os.environ['OMNIBROWSER_CORE'] = core\n"
            "from src.main import main\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )

    # 3) 打包
    dist = os.path.join(ROOT, "dist", "OmniBrowser")
    if os.path.isdir(dist):
        shutil.rmtree(dist)

    font_dir = _find_font_dir()
    if font_dir:
        print("中文字体目录：", font_dir)
    else:
        print("警告：未找到中文字体目录，将不随包分发字体"
              "（Windows 自带中文字体，界面可正常显示）")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "OmniBrowser",
        "--windowed",
        "--icon", ICO,
        "--paths", SRC,
        "--add-binary", f"{CORE_EXE};.",
        "--collect-submodules", "PyQt6",
        "--hidden-import", "PyQt6.QtWebEngineCore",
        "--hidden-import", "PyQt6.QtWebEngineWidgets",
        "--hidden-import", "PyQt6.QtWebEngineQuick",
        "--noconfirm",
        entry,
    ]
    if font_dir:
        cmd += ["--add-data", f"{font_dir};fonts"]
    run(cmd)

    print("\n完成：", dist)
    print("版本：", VERSION)

    # 4) 打成 NSIS 安装包
    if args.no_installer:
        print("已跳过安装包构建（--no-installer）")
        return 0

    exe_path = build_nsis_installer(VERSION)
    if not exe_path:
        print("⚠️ NSIS 安装包未生成，便携程序仍可用：", dist)
        return 0

    print("✅ 安装包：", exe_path)
    print("   大小：%.1f MB" % (os.path.getsize(exe_path) / 1024 / 1024))

    # 5) Authenticode 签名（可选：需要证书 / Azure Artifact Signing）
    if args.sign:
        sign_artifact(exe_path)
    else:
        print("提示：未启用签名（--sign）。未签名的安装包在用户机器上会显示")
        print("      「未知发布者」并可能触发 SmartScreen 提示。")
        print("      签名方式见 docs/04-windows-code-signing.md")
    return 0


def sign_artifact(path):
    """对产物执行 Authenticode 签名。

    复用 tools/sign_windows.py：
    - 若配置了 Azure Artifact Signing 环境变量 → 走云签名（私钥不出域）
    - 否则用本地证书库 / PFX（SignPath 导出的 PFX 或商业 CA 证书）
    """
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        import sign_windows
    except ImportError as exc:
        print(f"❌ 无法加载签名模块 tools/sign_windows.py: {exc}")
        return False

    if not sign_windows.find_signtool():
        print("❌ 未找到 signtool.exe，请安装 Windows SDK："
              " winget install Microsoft.WindowsSDK")
        return False

    pfx = os.environ.get("YC_SIGNING_PFX") or os.path.join(
        ROOT, "installer", "yc-signing.pfx")
    pwd = os.environ.get("YC_SIGNING_PASSWORD", "")

    class _Args:
        file = path
        pfx = pfx if os.path.isfile(pfx) else None
        password = pwd or None
        name = None
        timestamp = sign_windows.DEFAULT_TIMESTAMP_URL

    if _Args.pfx is None and not sign_windows.list_personal_certs():
        print("❌ 没有可用的签名凭据：")
        print("   · 本机测试：python tools/sign_windows.py selfsign")
        print("   · 正式发布：申请 SignPath Foundation 免费证书，或购买 OV/EV 证书")
        print("   · 云签名：配置 AZURE_SIGNING_ENDPOINT 等环境变量")
        return False

    return sign_windows.cmd_sign(_Args()) == 0


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


def build_nsis_installer(version):
    """用 NSIS 把便携目录打成安装包。"""
    makensis = find_makensis()
    if not makensis:
        print("❌ 未找到 NSIS（makensis.exe）。请安装 NSIS 3.x：")
        print("   winget install NSIS.NSIS")
        return None

    nsi = os.path.join(ROOT, "installer", "omnibrowser.nsi")
    if not os.path.isfile(nsi):
        print("❌ 未找到 NSIS 脚本：", nsi)
        return None

    # NSIS 的 Icon/OutFile 都是相对「脚本所在目录」解析的，
    # 因此必须在 installer/ 目录下编译，并把 ico 与 dist 复制到该目录的预期位置。
    ico_src = os.path.join(ASSETS, "omnibrowser.ico")
    ico_dst = os.path.join(ROOT, "installer", "omnibrowser.ico")
    if os.path.isfile(ico_src) and not os.path.isfile(ico_dst):
        shutil.copy2(ico_src, ico_dst)

    # NSIS 脚本里的 VERSION 是硬编码的，按当前版本号重写（保持与 src/version.py 一致）
    with open(nsi, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r'!define VERSION "[^"]*"', f'!define VERSION "{version}"', content)
    with open(nsi, "w", encoding="utf-8") as f:
        f.write(content)

    print("==> 编译 NSIS 安装包 ...")
    r = subprocess.run(
        [makensis, os.path.basename(nsi)],
        cwd=os.path.join(ROOT, "installer"),
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

    out = os.path.join(ROOT, "installer", f"YcBrowser-{version}-setup.exe")
    if not os.path.isfile(out):
        cands = [f for f in os.listdir(os.path.join(ROOT, "installer"))
                 if f.endswith("-setup.exe")]
        if cands:
            out = os.path.join(ROOT, "installer", cands[0])
    return out if os.path.isfile(out) else None


if __name__ == "__main__":
    sys.exit(main())
