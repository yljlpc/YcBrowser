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

# Windows 控制台默认代码页无法输出中文，强制 UTF-8，避免构建日志抛
# UnicodeEncodeError（CI 与本地 cmd/powershell 均会受影响）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

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


def _write_version_file(version):
    """生成 PyInstaller 用的 VERSIONINFO 文件。

    SignPath 要求产物元数据必须正确且一致 —— 产品名与项目名一致、
    版本号在每次构建中相同。安装包由 NSIS 的 VIAddVersionKey 提供，
    便携版主程序则需要这个文件，两边保持一致。
    """
    parts = [int(p) for p in version.split(".")]
    while len(parts) < 4:
        parts.append(0)
    tuple4 = ", ".join(str(p) for p in parts[:4])
    ver4 = ".".join(str(p) for p in parts[:4])

    content = f'''# -*- coding: utf-8 -*-
# 由 installer/build_windows.py 自动生成，请勿手工修改。
# 每次构建会按 src/version.py 的版本号重新生成。
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({tuple4},),
    prodvers=({tuple4},),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '080404B0',
          [StringStruct('CompanyName', 'Yc Browser'),
           StringStruct('FileDescription', 'Yc浏览器 —— 多引擎浏览器'),
           StringStruct('FileVersion', '{ver4}'),
           StringStruct('InternalName', 'OmniBrowser'),
           StringStruct('OriginalFilename', 'OmniBrowser.exe'),
           StringStruct('ProductName', 'Yc浏览器'),
           StringStruct('ProductVersion', '{ver4}'),
           StringStruct('LegalCopyright', 'MIT License')])
      ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
'''
    path = os.path.join(ROOT, "installer", "_version_info.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _qt_runtime_args():
    """构造显式收集 Qt6 运行时资源的 PyInstaller 参数。

    目标：产物必须能在**没有任何预装软件**的干净 Windows 上运行。

    PyInstaller 自带的 hook-PyQt6.py 靠在隔离子进程中 import
    PyQt6.QtCore 来探测 Qt 路径。在启用了 Windows 应用控制策略的机器上
    该 import 会被拦截，hook 整段跳过 —— 结果是产物缺少平台插件、
    WebEngine 子进程与资源包，双击即报
    "no Qt platform plugin could be initialized"。

    因此这里不依赖 hook，直接把 Qt6 的运行时目录整体纳入：

      bin/         全部 Qt6 DLL + VC++ 运行时 + opengl32sw（软件渲染回退）
                   + qt.conf（决定 Qt 到哪里找插件，缺了插件必然找不到）
      plugins/     平台插件（qwindows.dll）、图像格式、样式、图标引擎、TLS
      resources/   WebEngine 的 pak 资源包与 ICU 数据
      translations/界面翻译
      qml/         QML 运行时（WebEngine 间接依赖）
    """
    import sysconfig

    try:
        sp = sysconfig.get_paths()["purelib"]
    except Exception:
        sp = os.path.join(sys.path[0], "site-packages")
    qt6 = os.path.join(sp, "PyQt6", "Qt6")

    args = []
    if not os.path.isdir(qt6):
        print("⚠️ 未找到 PyQt6/Qt6 运行时目录：", qt6)
        return args

    # 整目录收集：bin / plugins / resources / translations / qml
    for sub in ("bin", "plugins", "resources", "translations", "qml"):
        src = os.path.join(qt6, sub)
        if os.path.isdir(src):
            args += ["--add-data", f"{src};PyQt6/Qt6/{sub}"]
            print(f"✓ 收集 Qt6/{sub}")
        else:
            print(f"⚠️ Qt6/{sub} 不存在，跳过")

    # WebEngine 子进程程序：渲染进程，缺失则网页无法加载。
    # bin 目录已整体收集，这里再以 binary 形式补一次，确保被标记为可执行。
    for exe_name in ("QtWebEngineProcess.exe", "Qt6WebEngineProcess.exe"):
        exe = os.path.join(qt6, "bin", exe_name)
        if os.path.isfile(exe):
            args += ["--add-binary", f"{exe};PyQt6/Qt6/bin"]
            print("✓ 收集 WebEngine 进程：", exe)
            break
    else:
        print("⚠️ 未找到 WebEngine 进程程序，网页渲染可能不可用")

    return args


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
    parser.add_argument(
        "--sign-password",
        default=os.environ.get("YC_SIGNING_PASSWORD", ""),
        help="PFX 密码（默认取环境变量 YC_SIGNING_PASSWORD）"
    )
    args = parser.parse_args()
    # 统一走环境变量，sign_tree / sign_artifact 都从这里取 PFX 密码
    if args.sign_password:
        os.environ["YC_SIGNING_PASSWORD"] = args.sign_password

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
    #
    # 不用 shutil.rmtree 删旧产物：那会触发「批量删除」安全钩子。
    # PyInstaller 的 --noconfirm 会自行覆盖/重建 COLLECT 目录，
    # 这里只把确实过期的旧目录改名归档（.old-<时间戳>），避免硬删除。
    dist = os.path.join(ROOT, "dist", "OmniBrowser")
    if os.path.isdir(dist):
        import time
        stale = os.path.join(ROOT, "dist", "OmniBrowser.old-%d" % int(time.time()))
        try:
            os.rename(dist, stale)
            print("旧产物已重命名归档：", stale)
        except OSError as exc:
            print(f"⚠️ 无法归档旧产物目录（{exc}），将直接覆盖构建")

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
        "--hidden-import", "PyQt6.QtCore",
        "--hidden-import", "PyQt6.QtGui",
        "--hidden-import", "PyQt6.QtWidgets",
        "--hidden-import", "PyQt6.QtPrintSupport",
        "--hidden-import", "PyQt6.QtWebEngineCore",
        "--hidden-import", "PyQt6.QtWebEngineWidgets",
        "--hidden-import", "PyQt6.sip",
        "--noconfirm",
        entry,
    ]

    # 运行时钩子：显式设置 QT_PLUGIN_PATH 等环境变量，
    # 让 Qt 能找到平台插件、webengine 进程与资源包。
    # PyInstaller 自带 hook 会做这件事，但它在启用应用控制策略的机器上
    # 会被整体跳过，因此这里自带一份。
    hook = os.path.join(ROOT, "installer", "_qt_runtime_hook.py")
    if os.path.isfile(hook):
        cmd += ["--runtime-hook", hook]
        print("✓ 使用运行时钩子：", hook)

    # 版本资源：保证便携版主程序与安装包的元数据一致
    try:
        ver_file = _write_version_file(VERSION)
        cmd += ["--version-file", ver_file]
        print("✓ 版本资源：", ver_file)
    except Exception as exc:
        print("⚠️ 生成版本资源失败（不影响打包）：", exc)
    if font_dir:
        cmd += ["--add-data", f"{font_dir};fonts"]

    # ---- Qt6 运行时资源（显式收集，不依赖 PyInstaller 的 hook）----
    #
    # 为什么必须显式收集：PyInstaller 的 hook-PyQt6.py 靠在隔离的子进程里
    # import PyQt6.QtCore 来探测 Qt 安装路径。在启用了 Windows 应用控制
    # 策略（WDAC/AppLocker）的机器上，这个 import 会被系统策略拦截
    # （ImportError: DLL load failed ... 应用程序控制策略已阻止此文件），
    # 导致 pyqt6_library_info.version 为 None，hook 整段被跳过。
    # 后果是产物里没有 plugins/platforms/qwindows.dll，
    # 双击即报 "no Qt platform plugin could be initialized"。
    #
    # 平台插件、WebEngine 子进程、资源包都是运行必需，因此在此逐项显式收集。
    cmd += _qt_runtime_args()

    run(cmd)

    print("\n完成：", dist)
    print("版本：", VERSION)

    # 4) 签名产物树（.pyd / .dll / .exe）
    #
    # 这一步不是可有可无的装饰：PyInstaller 产物里的 Python 扩展模块
    # （PyQt6 的 *.pyd）不带 Authenticode 签名，在启用了 Windows 应用
    # 控制策略的机器上会被系统直接拦截，表现为
    # "DLL load failed while importing QtCore: 应用程序控制策略已阻止此文件"。
    # 因此先把整个产物树签好，再打安装包。
    sign_tree(dist)

    # 5) 打成 NSIS 安装包
    if args.no_installer:
        print("已跳过安装包构建（--no-installer）")
        return 0

    exe_path = build_nsis_installer(VERSION)
    if not exe_path:
        print("⚠️ NSIS 安装包未生成，便携程序仍可用：", dist)
        return 0

    print("✅ 安装包：", exe_path)
    print("   大小：%.1f MB" % (os.path.getsize(exe_path) / 1024 / 1024))

    # 6) 签名安装包本身
    if args.sign:
        sign_artifact(exe_path)
    else:
        print("提示：未启用签名（--sign）。未签名的安装包在用户机器上会显示")
        print("      「未知发布者」并可能触发 SmartScreen 提示。")
        print("      签名方式见 docs/04-windows-code-signing.md")
    return 0


def sign_tree(directory):
    """对整个产物目录下的 .exe / .dll / .pyd 执行 Authenticode 签名。

    已带原厂签名（Qt 官方 DLL 等）的文件会被自动跳过，保留其原签名。
    """
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        import sign_windows
    except ImportError as exc:
        print(f"⚠️ 无法加载签名模块 tools/sign_windows.py: {exc}")
        return False

    if not sign_windows.find_signtool():
        print("⚠️ 未找到 signtool.exe，跳过产物树签名")
        print("   安装 Windows SDK：winget install Microsoft.WindowsSDK")
        return False

    pfx = os.environ.get("YC_SIGNING_PFX") or os.path.join(
        ROOT, "installer", "yc-signing.pfx")
    pwd = os.environ.get("YC_SIGNING_PASSWORD", "")
    _target_dir = directory

    class _Args:
        pass

    _Args.directory = _target_dir
    _Args.pfx = pfx if os.path.isfile(pfx) else None
    _Args.password = pwd or None
    _Args.timestamp = sign_windows.DEFAULT_TIMESTAMP_URL

    if _Args.pfx is None and not sign_windows.list_personal_certs():
        print("⚠️ 没有可用的签名凭据，产物树保持未签名")
        print("   · 本机测试：python tools/sign_windows.py selfsign --password ycbuild")
        print("   · 正式发布：申请 SignPath Foundation 免费证书")
        return False

    print("\n=== 签名产物树 ===")
    return sign_windows.cmd_sign_tree(_Args()) == 0


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
    _target = path

    # 注意：类体作用域看不到函数局部变量，因此先取出再赋值，
    # 否则 `file = path` 会抛 NameError。
    class _Args:
        pass

    _Args.file = _target
    _Args.pfx = pfx if os.path.isfile(pfx) else None
    _Args.password = pwd or None
    _Args.name = None
    _Args.timestamp = sign_windows.DEFAULT_TIMESTAMP_URL

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
    #
    # 编码要点：NSIS 3.x 要求 .nsi 必须是 UTF-8 **带 BOM** 或系统 ANSI 编码。
    # 无 BOM 的 UTF-8 会报 "Bad text encoding: omnibrowser.nsi:1"。
    # 脚本含中文（应用名 / 快捷方式名），必须用 utf-8-sig 读写。
    with open(nsi, "r", encoding="utf-8-sig") as f:
        content = f.read()
    content = re.sub(r'!define VERSION "[^"]*"', f'!define VERSION "{version}"', content)
    with open(nsi, "w", encoding="utf-8-sig") as f:
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
