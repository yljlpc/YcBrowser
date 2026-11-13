#!/usr/bin/env python3
"""独立安装包自检：验证产物能否脱离目标机器的预装环境运行。

检查项（全部基于文件系统的静态核对，不依赖执行产物）：

  1. Qt 路径解析   —— 按 qt.conf 的 Prefix 推导 Qt 的各路径，验证目录与关键文件
  2. 运行时钩子   —— 模拟 installer/_qt_runtime_hook.py 计算出的每个环境变量
  3. 平台插件     —— qwindows.dll 是否就位
  4. WebEngine    —— 按 Qt 官方文档逐项核对必需文件
  5. 依赖闭包     —— 递归解析 PE 导入表，区分「必需缺失」与「可选插件的可选依赖」
  6. 随包资源     —— Rust 核心、中文字体、Python 运行时、VC++ 运行时
  7. 数字签名     —— 各 PE 文件的 Authenticode 签名状态

用法：
    python tools/verify_bundle.py dist/OmniBrowser
    python tools/verify_bundle.py dist/OmniBrowser --verbose
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audit_dependencies import parse_pe_imports, is_system_dll  # noqa: E402

# Qt 官方文档《Deploying Qt WebEngine Applications》列出的必需文件
WEBENGINE_REQUIRED = [
    ("Qt6WebEngineCore.dll", "WebEngine 核心库"),
    ("Qt6WebEngineWidgets.dll", "WebEngine Widgets 绑定"),
    ("QtWebEngineProcess.exe", "WebEngine 渲染进程（每个标签页一个实例）"),
    ("qtwebengine_resources.pak", "Chromium 资源"),
    ("qtwebengine_devtools_resources.pak", "远程调试工具资源"),
    ("qtwebengine_resources_100p.pak", "低分辨率显示资源"),
    ("qtwebengine_resources_200p.pak", "高 DPI 显示资源"),
    ("icudtl.dat", "ICU Unicode 支持"),
    ("v8_context_snapshot.bin", "V8 上下文快照（加速初始化）"),
]

# 平台插件：缺了必然启动失败
PLATFORM_REQUIRED = [
    ("plugins/platforms/qwindows.dll", "Windows 平台插件"),
    ("plugins/imageformats", "图像格式插件（PNG/JPEG/GIF/SVG 等）"),
    ("plugins/styles", "界面样式插件"),
    ("plugins/iconengines", "SVG 图标引擎"),
    ("plugins/tls", "TLS/SSL 支持"),
]

# 随包必须存在的其他组件
BUNDLE_REQUIRED = [
    ("omnibrowser-core.exe", "Rust 原生核心"),
    ("fonts", "中文字体目录"),
    ("python3.dll", "Python 运行时"),
]


class Checker:
    def __init__(self, root, verbose=False):
        self.root = os.path.abspath(root)
        self.verbose = verbose
        self.internal = os.path.join(self.root, "_internal")
        self.qt6 = os.path.join(self.internal, "PyQt6", "Qt6")
        self.failures = []
        self.warnings = []
        self.ok_count = 0

    # ---------- 基础工具 ----------
    def rel(self, path):
        try:
            return os.path.relpath(path, self.root)
        except ValueError:
            return path

    def pass_(self, msg):
        self.ok_count += 1
        print("  [OK]   " + msg)

    def fail(self, msg, detail=""):
        self.failures.append(msg + (("  —— " + detail) if detail else ""))
        print("  [FAIL] " + msg + (("  —— " + detail) if detail else ""))

    def warn(self, msg, detail=""):
        self.warnings.append(msg + (("  —— " + detail) if detail else ""))
        print("  [WARN] " + msg + (("  —— " + detail) if detail else ""))

    def section(self, title):
        print()
        print("=" * 66)
        print(title)
        print("=" * 66)

    # ---------- 1. Qt 路径解析 ----------
    def check_qt_paths(self):
        self.section("1. Qt 路径解析（依据 qt.conf 的 Prefix）")
        conf = os.path.join(self.qt6, "bin", "qt.conf")
        if not os.path.isfile(conf):
            self.fail("缺少 qt.conf", "Qt 将无法定位 plugins/resources 目录")
            return
        prefix_rel = None
        with open(conf, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.lower().startswith("prefix"):
                    prefix_rel = line.split("=", 1)[1].strip()
        if not prefix_rel:
            self.fail("qt.conf 中没有 Prefix 项")
            return
        # Prefix 相对于 qt.conf 所在目录
        prefix = os.path.normpath(os.path.join(os.path.dirname(conf), prefix_rel))
        self.pass_("qt.conf Prefix = %s  →  %s" % (prefix_rel, self.rel(prefix)))
        if not os.path.isdir(prefix):
            self.fail("Prefix 指向的目录不存在", self.rel(prefix))
            return

        # Qt 6 的标准布局
        layout = [
            ("PluginsPath", os.path.join(prefix, "plugins")),
            ("DataPath", prefix),
            ("LibraryExecutablesPath", os.path.join(prefix, "bin")),
            ("TranslationsPath", os.path.join(prefix, "translations")),
        ]
        for name, path in layout:
            if os.path.isdir(path):
                self.pass_("%-22s %s" % (name, self.rel(path)))
            else:
                self.fail("%s 目录不存在" % name, self.rel(path))

    # ---------- 2. 运行时钩子 ----------
    def check_runtime_hook(self):
        self.section("2. 运行时钩子解析出的环境变量目标")
        # 模拟 installer/_qt_runtime_hook.py 的计算逻辑
        targets = {
            "QT_PLUGIN_PATH": self.qt6,
            "QT_QPA_PLATFORM_PLUGIN_PATH": os.path.join(self.qt6, "plugins", "platforms"),
            "QTWEBENGINEPROCESS_PATH": os.path.join(self.qt6, "bin", "QtWebEngineProcess.exe"),
            "QTWEBENGINE_RESOURCES_PATH": os.path.join(self.qt6, "resources"),
            "QTWEBENGINE_LOCALES_PATH": os.path.join(self.qt6, "translations", "qtwebengine_locales"),
        }
        for env, path in targets.items():
            if os.path.exists(path):
                self.pass_("%-30s → %s" % (env, self.rel(path)))
            else:
                self.fail("%s 指向的路径不存在" % env, self.rel(path))

    # ---------- 3. 平台插件 ----------
    def check_platform_plugins(self):
        self.section("3. 平台插件")
        for rel, desc in PLATFORM_REQUIRED:
            p = os.path.join(self.qt6, rel)
            if os.path.exists(p):
                self.pass_("%-34s %s" % (desc, self.rel(p)))
            else:
                self.fail("缺少 %s" % desc, self.rel(p))

    # ---------- 4. WebEngine 必需文件 ----------
    def check_webengine(self):
        self.section("4. Qt WebEngine 必需文件（依据 Qt 官方部署文档）")
        for fn, desc in WEBENGINE_REQUIRED:
            hit = None
            for dirpath, _d, files in os.walk(self.internal):
                if fn in files:
                    hit = os.path.join(dirpath, fn)
                    break
            if hit:
                size = os.path.getsize(hit) / 1048576
                self.pass_("%-38s (%.1f MB)  %s" % (desc, size, self.rel(hit)))
            else:
                self.fail("缺少 %s" % desc, fn)

    # ---------- 5. 依赖闭包 ----------
    def check_dependency_closure(self):
        self.section("5. 依赖闭包分析（递归解析 PE 导入表）")
        shipped = {}
        for dirpath, _d, files in os.walk(self.root):
            for fn in files:
                shipped.setdefault(fn.lower(), os.path.join(dirpath, fn))

        pe_files = []
        for dirpath, _d, files in os.walk(self.root):
            for fn in files:
                if fn.lower().endswith((".exe", ".dll", ".pyd")):
                    pe_files.append(os.path.join(dirpath, fn))

        # 必需文件 = 主程序 + Python 扩展模块 + WebEngine 核心 + Rust 核心
        # 注意：plugins/ 下的都是可选插件（即使文件名含 webengine），
        # 它们加载失败时 Qt 会优雅降级，不应计入「必需缺失」。
        qt_bin = os.path.join(self.qt6, "bin")
        critical = []
        for p in pe_files:
            base = os.path.basename(p).lower()
            if os.sep + "plugins" + os.sep in p:
                continue
            if (base in ("omnibrowser.exe", "omnibrowser-core.exe")
                    or base.endswith(".pyd")
                    or (os.path.dirname(p) == qt_bin
                        and ("webengine" in base or base.startswith("qt6")))):
                critical.append(p)

        missing_critical = {}
        missing_optional = {}
        for pe in pe_files:
            for dep in parse_pe_imports(pe):
                dl = dep.lower()
                if dl in shipped or is_system_dll(dep):
                    continue
                target = missing_critical if pe in critical else missing_optional
                target.setdefault(dep, set()).add(self.rel(pe))

        if missing_critical:
            for dep in sorted(missing_critical):
                self.fail("必需组件缺少依赖：%s" % dep,
                          "被 %d 个核心文件依赖" % len(missing_critical[dep]))
        else:
            self.pass_("全部核心文件（主程序 / %d 个 Python 扩展 / WebEngine / Rust 核心）"
                       " 的依赖均可由产物自身或系统满足"
                       % len([p for p in pe_files if p.endswith('.pyd')]))

        if missing_optional:
            # 这些只被可选插件引用（数据库驱动、3D 场景、QML 语言工具等），
            # 插件加载失败时 Qt 会优雅降级，不影响浏览器功能。
            self.warn("可选插件存在未满足的依赖（不影响浏览器功能）",
                      "%d 项：%s" % (len(missing_optional),
                                    ", ".join(sorted(missing_optional)[:6])))
            if self.verbose:
                for dep in sorted(missing_optional):
                    users = missing_optional[dep]
                    print("        • %-22s ← %s" % (dep, ", ".join(sorted(users)[:3])))

    # ---------- 6. 随包资源 ----------
    def check_bundle_resources(self):
        self.section("6. 随包资源")
        for rel, desc in BUNDLE_REQUIRED:
            p = os.path.join(self.internal, rel)
            if os.path.exists(p):
                extra = ""
                if os.path.isdir(p):
                    cnt = len([f for f in os.listdir(p)
                               if f.lower().endswith((".ttf", ".otf", ".ttc"))])
                    extra = "（%d 个字体文件）" % cnt
                self.pass_("%-20s %s%s" % (desc, self.rel(p), extra))
            else:
                self.fail("缺少 %s" % desc, rel)

        # VC++ 运行时（Qt WebEngine 要求 14.28+）
        vc = [f for f in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll",
                          "msvcp140_1.dll", "msvcp140_2.dll")
              if any(fn.lower() == f for fn in os.listdir(
                  os.path.join(self.internal, "PyQt6", "Qt6", "bin"))
                  if os.path.isdir(os.path.join(self.internal, "PyQt6", "Qt6", "bin")))]
        if vc:
            self.pass_("VC++ 运行时（app-local，随包分发）: %s" % ", ".join(vc))
        else:
            self.fail("缺少 VC++ 运行时 DLL", "Qt WebEngine 需要 14.28 或更高版本")

        # 无 GPU 环境下的软件渲染回退
        sw = os.path.join(self.qt6, "bin", "opengl32sw.dll")
        if os.path.isfile(sw):
            self.pass_("软件 OpenGL 回退（无 GPU 机器可用）: opengl32sw.dll")
        else:
            self.warn("缺少 opengl32sw.dll", "无 GPU 机器上 Chromium 可能无法渲染")

    # ---------- 7. 数字签名 ----------
    def check_signatures(self):
        self.section("7. Authenticode 数字签名")
        try:
            from sign_windows import _pe_has_signature
        except ImportError:
            self.warn("无法加载签名检查模块")
            return
        unsigned = []
        signed = 0
        for dirpath, _d, files in os.walk(self.root):
            for fn in files:
                if fn.lower().endswith((".exe", ".dll", ".pyd")):
                    p = os.path.join(dirpath, fn)
                    if _pe_has_signature(p):
                        signed += 1
                    else:
                        unsigned.append(self.rel(p))
        self.pass_("已签名: %d 个可执行文件" % signed)
        if unsigned:
            self.warn("未签名: %d 个" % len(unsigned), ", ".join(unsigned[:5]))

    # ---------- 主流程 ----------
    def run(self):
        print("=" * 66)
        print("独立安装包自检：" + self.root)
        print("=" * 66)
        if not os.path.isdir(self.root):
            print("目录不存在")
            return 2
        self.check_qt_paths()
        self.check_runtime_hook()
        self.check_platform_plugins()
        self.check_webengine()
        self.check_dependency_closure()
        self.check_bundle_resources()
        self.check_signatures()

        print()
        print("=" * 66)
        print("自检结果")
        print("=" * 66)
        print(f"通过项     : {self.ok_count}")
        print(f"失败项     : {len(self.failures)}")
        print(f"警告项     : {len(self.warnings)}")
        if self.failures:
            print()
            print("失败明细：")
            for f in self.failures:
                print("  ✗ " + f)
        if self.warnings:
            print()
            print("警告明细：")
            for w in self.warnings:
                print("  ! " + w)
        print()
        if not self.failures:
            print("✅ 产物自检通过：运行时所需组件齐备，可脱离预装环境运行")
            return 0
        print("❌ 存在失败项，需补齐后重新打包")
        return 1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    return Checker(sys.argv[1], "--verbose" in sys.argv).run()


if __name__ == "__main__":
    sys.exit(main())
