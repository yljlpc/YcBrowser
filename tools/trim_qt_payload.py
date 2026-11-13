#!/usr/bin/env python3
"""分析并裁剪 PyInstaller 产物中的 Qt6 运行时载荷。

背景
----
本项目只用到了 Qt6 的 5 个模块（QtCore / QtGui / QtWidgets / QtPrintSupport /
QtWebEngineCore / QtWebEngineWidgets），但 PyInstaller 的 hook 与「整目录收集」
策略会把 **整个 Qt6 运行时** 塞进产物：

    bin/          349 MB  123 个 DLL —— 包含 QML / Quick3D / Designer / Multimedia
    resources/    102 MB  含 73 MB 的 debug 版 DevTools 资源包
    translations/  55 MB  242 个 .qm 翻译文件（240 种语言）
    plugins/       17 MB  含 sqldrivers / qmlls / sceneparsers 等无关插件
    qml/           15 MB  895 个 .qml + 780 张图标（本应用不用 QML）

结果是产物 2788 个文件 / 589 MB —— 安装时逐个文件写入 + 被 Defender 实时扫描，
是「安装很慢」的主因。

本脚本做两件事：
  1. **静态分析**：解析 PE 导入表，算出从入口模块出发的 DLL 依赖闭包，
     得到「真正必需」的 DLL 集合（而不是靠人工猜测）。
  2. **裁剪**：把用不到的 DLL / 插件 / 翻译 / 资源从产物目录删除。

安全约束
--------
- 只删除「可证明不被需要」的文件：不在依赖闭包内的 DLL、非白名单插件、
  非中英文翻译、`.debug.*` 调试资源。
- 依赖闭包以 **入口 .pyd + 可执行文件** 为根，沿 PE 导入表递归展开，
  任何被静态链接引用的 DLL 都会自动保留。
- `--dry-run` 只报告不删除，便于先审阅再执行。

用法：
    python tools/trim_qt_payload.py --dist dist/OmniBrowser --dry-run
    python tools/trim_qt_payload.py --dist dist/OmniBrowser
"""
import argparse
import json
import os
import shutil
import struct
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# ---------------------------------------------------------------------------
# PE 解析：读取导入表（Import Directory）与延迟导入表（Delay Import Directory）
# ---------------------------------------------------------------------------

def _read_rva_to_offset(sections, rva):
    """把 RVA 换算成文件偏移。sections 为 [(name, vaddr, vsize, praw, psize)]。"""
    for _name, vaddr, vsize, praw, psize in sections:
        if vaddr <= rva < vaddr + max(vsize, psize):
            return praw + (rva - vaddr)
    return None


def _read_cstring(data, offset):
    """从 offset 处读取**一个**以 \\0 结尾的 ASCII 字符串。

    必须只读一个：导入表的 Name 字段指向的 DLL 名后面，紧接着就是
    hint/name 表的 2 字节 hint —— 只隔一个 \\0 而非两个。
    连读会把 hint/name 条目（'SystemFunction036' 之类）误当成 DLL 名。
    """
    if offset is None or offset < 0 or offset >= len(data):
        return ""
    end = data.find(b"\0", offset, min(len(data), offset + 260))
    if end < 0:
        return ""
    try:
        return data[offset:end].decode("ascii")
    except UnicodeDecodeError:
        return data[offset:end].decode("latin-1")


def parse_imports(path):
    """返回 (普通导入, 延迟导入) 两个 DLL 名列表。缺失或格式异常时返回空列表。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return [], []

    if len(data) < 0x40 or data[:2] != b"MZ":
        return [], []
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if e_lfanew + 24 > len(data) or data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        return [], []

    coff = e_lfanew + 4
    n_sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x20B:      # PE32+
        dd_off = opt + 112
    elif magic == 0x10B:    # PE32
        dd_off = opt + 96
    else:
        return [], []

    # 节表
    sec_off = opt + opt_size
    sections = []
    for i in range(n_sections):
        base = sec_off + i * 40
        if base + 40 > len(data):
            break
        name = data[base:base + 8].rstrip(b"\0").decode("latin-1")
        vsize, vaddr, psize, praw = struct.unpack_from("<IIII", data, base + 8)
        sections.append((name, vaddr, vsize, praw, psize))

    def _dir_entries(index):
        pos = dd_off + index * 8
        if pos + 8 > len(data):
            return 0, 0
        rva, size = struct.unpack_from("<II", data, pos)
        return rva, size

    def _collect(index, use_rva_field):
        rva, size = _dir_entries(index)
        if not rva or not size:
            return []
        off = _read_rva_to_offset(sections, rva)
        if off is None:
            return []
        names = []
        stride = 32 if use_rva_field else 20
        pos = off
        while pos + stride <= len(data):
            if use_rva_field:
                # IMAGE_DELAYLOAD_DESCRIPTOR: Attributes, Name, ModuleHandle, IAT, INT, BoundIAT, UnloadIAT, TimeDateStamp
                attrs, name_rva = struct.unpack_from("<II", data, pos)
                if name_rva == 0:
                    break
            else:
                # IMAGE_IMPORT_DESCRIPTOR: OriginalFirstThunk, TimeDateStamp, ForwarderChain, Name, FirstThunk
                name_rva = struct.unpack_from("<I", data, pos + 12)[0]
                if name_rva == 0:
                    break
            noff = _read_rva_to_offset(sections, name_rva)
            if noff is None:
                break
            nm = _read_cstring(data, noff)
            if nm:
                names.append(nm)
            pos += stride
        return names

    normal = _collect(1, False)
    delay = _collect(13, True)
    return normal, delay


# ---------------------------------------------------------------------------
# 保留策略
# ---------------------------------------------------------------------------

# 保留的 Qt 插件类别 —— 其余类别（sqldrivers / qmlls / sceneparsers /
# assetimporters / geometryloaders / designer / multimedia / position /
# sensors / texttospeech / scxmldatamodel / networkinformation / help …）
# 在 QWidget + WebEngine 应用中永远不会被加载。
KEEP_PLUGIN_DIRS = {
    "platforms",        # qwindows.dll —— 没有它程序根本无法启动
    "styles",           # Windows 11 原生观感
    "imageformats",     # gif / ico / jpeg / svg / webp 等图片解码
    "iconengines",      # SVG 图标引擎
    "tls",              # Qt 的 OpenSSL 后端（QNetworkAccessManager 走 HTTPS 时用）
    "renderers",        # QtWebEngine 的 ANGLE/OpenGL 渲染后端
    "generic",          # 通用插件容器
}

# 保留的 QML 模块目录（空 = 整棵 qml/ 全部删除）。
#
# 依据：把 qml/ 下每个插件的导入表解出来后发现，它们全部依赖
# **PyInstaller 根本没收集**的 Qt6 模块 DLL —— Qt6QmlNetwork.dll、
# Qt6WebEngineQuick.dll、Qt6QmlDesignSupport.dll、Qt6Quick3D*、
# Qt6QmlXmlListModel.dll …也就是说这棵树在当前产物里本来就是坏的，
# 任何一条加载路径都会立刻失败。而本应用只用 QWidget + WebEngine，
# 不创建 QQmlEngine、不 import 任何 .qml，qml/ 永远不会走到。
#
# 代价：qml/ 独占 2329 个文件（占全产物的 84%），是安装慢（Defender
# 逐文件扫描 + 逐文件创建）的主要来源。删除它对功能零影响。
KEEP_QML_DIRS: set[str] = set()

# 保留的翻译：应用与 Qt 界面为中文，保留简体 + 英文即可。
KEEP_TRANSLATION_PREFIX = ("qtbase_zh_CN", "qtbase_en_US", "qt_zh_CN", "qt_en_US",
                            "qtwebengine_zh_CN", "qtwebengine_en_US")

# 保留的 WebEngine locale（Chromium 本地化资源）。
#
# QTWEBENGINE_LOCALES_PATH 指向 translations/qtwebengine_locales，
# 里面每个语言一个约 1 MB 的 .pak，负责网页里的系统对话框、错误页、
# 右键菜单等 Chromium 内置界面的文案 —— 少了 zh-CN.pak，
# 中文用户看到的浏览器内置提示就会变成英文。
# 53 个语言共 44 MB，只留简体中文、繁体中文、英文三种。
KEEP_WEBENGINE_LOCALES = {"zh-CN.pak", "zh-TW.pak", "en-US.pak"}

# 保留的 WebEngine 资源包。
#
# 这份清单来自对 Qt6WebEngineCore.dll 的字符串表反查 —— DLL 里实际引用的
# 只有下面这几个名字，其余 5 个 *.debug.* 文件（合计 77 MB）在任何代码路径下
# 都不会被打开（Chromium 的 release 构建只认 v8_context_snapshot.bin，
# 不做「debug 文件存在则优先」的探测）。
KEEP_RESOURCES = {
    "qtwebengine_resources.pak",            # WebEngine 基础资源
    "qtwebengine_resources_200p.pak",       # 高 DPI 资源
    "qtwebengine_resources_100p.pak",       # 高 DPI 资源
    "qtwebengine_devtools_resources.pak",   # F12 开发者工具界面（应用提供该功能）
    "icudtl.dat",                           # ICU 字符库（中日韩必需）
    "v8_context_snapshot.bin",              # V8 快照（启动快）
}

# 不随包分发、但可能被系统/应用间接依赖的外部 DLL（不删，只是别动）。
EXTERNAL_DLL_HINTS = {
    "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll",
    "msvcp140_2.dll", "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll",
    "concrt140.dll", "ucrtbase.dll", "api-ms-win-crt-*.dll",
    "d3dcompiler_47.dll",      # ANGLE 运行时编译 HLSL 着色器
    "opengl32sw.dll",          # 无 GPU 时的软件 OpenGL 回退
    "avcodec-*.dll", "avformat-*.dll", "avutil-*.dll", "swscale-*.dll",
    "swresample-*.dll", "opus-*.dll", "libcrypto-*.dll", "libssl-*.dll",
}

# 运行期动态加载、不出现在 PE 导入表里的可执行文件。
DYNAMIC_EXE_KEEP = {
    "QtWebEngineProcess.exe",  # WebEngine 渲染子进程，由 Qt6WebEngineCore 拉起
}


def _match_hint(name, hints):
    import fnmatch
    for h in hints:
        if fnmatch.fnmatch(name.lower(), h.lower()):
            return True
    return False


# ---------------------------------------------------------------------------
# 完备性校验
# ---------------------------------------------------------------------------

def verify_tree(dist):
    """校验裁剪后的产物：每个 PE 的导入表里引用的 DLL 都必须能找到。

    找不到分两类：
      - 系统 DLL（System32 / SysWOW64 里存在）—— 正常，不算问题；
      - 本应随包携带却缺失 —— 说明裁剪过头，必须报出来。

    这是裁剪的**安全网**：本机被 WDAC 策略拦着跑不起来 Qt 时，
    静态导入表校验是唯一能证明「没删错」的可靠手段。
    """
    files = collect_files(dist)
    by_name = {}
    for rel in files:
        by_name.setdefault(os.path.basename(rel).lower(), rel)

    sysdirs = [
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"),
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "SysWOW64"),
    ]
    sysnames = set()
    for d in sysdirs:
        if os.path.isdir(d):
            for fn in os.listdir(d):
                sysnames.add(fn.lower())

    problems = []
    checked = 0
    for rel, full in files.items():
        if not full.lower().endswith((".dll", ".pyd", ".exe")):
            continue
        checked += 1
        normal, delay = parse_imports(full)
        for dep in set(normal + delay):
            low = dep.lower()
            if low in by_name or low in sysnames:
                continue
            # apisetapi 等转发器名在 System32 里没有实体文件，属正常
            if low.startswith("api-ms-win-") or low.startswith("ext-ms-"):
                continue
            problems.append((rel, dep))

    print(f"已校验 {checked} 个 PE 文件的导入表")
    if problems:
        print(f"❌ 发现 {len(problems)} 处未解析的依赖：")
        for rel, dep in problems[:60]:
            print(f"   {rel}  →  {dep}")
        if len(problems) > 60:
            print(f"   ... 其余 {len(problems)-60} 处省略")
    else:
        print("✅ 全部导入依赖均可解析，裁剪未造成缺失")
    return problems


# ---------------------------------------------------------------------------

def collect_files(dist):
    """收集产物目录下所有文件（相对路径 -> 绝对路径）。"""
    out = {}
    for root, _dirs, files in os.walk(dist):
        for fn in files:
            full = os.path.join(root, fn)
            out[os.path.relpath(full, dist).replace("\\", "/")] = full
    return out


def _category(rel, marker):
    """取 rel 中 marker 段（plugins/qml）之后的那一段，即子类名。

    marker 段的位置随 PyInstaller 的 _internal 前缀变化，
    因此按标记段动态定位，不写死下标。
    """
    parts = rel.split("/")
    if marker not in parts:
        return ""
    i = parts.index(marker)
    return parts[i + 1] if i + 1 < len(parts) else ""


def _is_pe(rel):
    return rel.lower().endswith((".dll", ".exe", ".pyd"))


def _system_dll_names():
    """系统目录里存在的 DLL 名集合（用于判定「依赖可由系统满足」）。"""
    sysdirs = [
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"),
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "SysWOW64"),
    ]
    names = set()
    for d in sysdirs:
        if os.path.isdir(d):
            for fn in os.listdir(d):
                names.add(fn.lower())
    return names


def _expand_closure(files, by_name, seeds):
    """沿 PE 导入表递归展开，返回依赖闭包（文件相对路径集合）。"""
    needed = set()
    queue = list(seeds)
    while queue:
        rel = queue.pop()
        if rel in needed:
            continue
        needed.add(rel)
        full = files.get(rel)
        if not full or not _is_pe(rel):
            continue
        normal, delay = parse_imports(full)
        for dep in normal + delay:
            dep_rel = by_name.get(dep.lower())
            if dep_rel and dep_rel not in needed:
                queue.append(dep_rel)
    return needed


def analyze(dist):
    """分析产物，返回裁剪方案。"""
    files = collect_files(dist)

    # PyInstaller one-folder 模式下二进制资源放在 _internal/ 下，
    # 目录前缀要动态识别（直接跑源码树时可能没有 _internal）。
    prefix = ""
    for cand in ("_internal/", ""):
        if any(r.startswith(cand + "PyQt6/Qt6/") for r in files):
            prefix = cand
            break
    qt_root = prefix + "PyQt6/Qt6"
    pyqt_root = prefix + "PyQt6"

    # 1) 建立「basename -> 相对路径」索引，用于依赖解析时的名字匹配
    by_name = {}
    for rel in files:
        by_name.setdefault(os.path.basename(rel).lower(), rel)

    # 2) 闭包种子
    #
    # 除了入口模块（应用 import 的 .pyd + 可执行文件），**保留的 Qt 插件
    # 也必须是种子**。插件由 Qt 在运行时用 LoadLibrary 加载，它们的依赖
    # 不出现在任何入口模块的导入表里：
    #     plugins/iconengines/qsvgicon.dll → Qt6Svg.dll
    #     plugins/imageformats/qsvg.dll     → Qt6Svg.dll
    # 只用入口模块做种子的话，Qt6Svg.dll 会被误删，SVG 图标与 SVG 图片
    # 随即失效 —— 这正是第一版裁剪逻辑漏掉的地方。
    seeds = []
    for rel in files:
        base = os.path.basename(rel)
        if rel.startswith(pyqt_root + "/") and base.endswith(".pyd"):
            seeds.append(rel)
        elif base in ("OmniBrowser.exe", "omnibrowser-core.exe",
                      "QtWebEngineProcess.exe"):
            seeds.append(rel)
        elif (rel.startswith(f"{qt_root}/plugins/")
              and _category(rel, "plugins") in KEEP_PLUGIN_DIRS
              and base.endswith(".dll")):
            seeds.append(rel)

    # 3) 依赖闭包
    needed = _expand_closure(files, by_name, seeds)

    # 4) 判定保留 / 删除
    keep, drop = [], []

    # Qt 目录下的非 PE 文件（配置文件）一律保留。
    #
    # 最关键的是 bin/qt.conf：
    #   [Paths]
    #   Prefix = ..
    # 它是 Qt 定位 plugins / resources / translations 的依据 —— 少了它，
    # QT_PLUGIN_PATH 又指错了层级（钩子里指向 Qt 根而不是 plugins 目录），
    # Qt 就会报 "no Qt platform plugin could be initialized"。
    # 它不是 PE，自然进不了依赖闭包，必须单独白名单。
    for rel in files:
        if rel.startswith(f"{qt_root}/bin/"):
            base = os.path.basename(rel)
            if not _is_pe(rel):
                keep.append(rel)          # qt.conf 等配置文件
                continue
            in_closure = rel in needed
            # 运行期动态加载、不在导入表里的 DLL 必须显式保留
            hinted = _match_hint(base, EXTERNAL_DLL_HINTS)
            dynamic = base in DYNAMIC_EXE_KEEP
            (keep if (in_closure or hinted or dynamic) else drop).append(rel)
            continue
        if rel.startswith(f"{qt_root}/plugins/"):
            if not _is_pe(rel):
                keep.append(rel)
                continue
            (keep if _category(rel, "plugins") in KEEP_PLUGIN_DIRS
             else drop).append(rel)
            continue
        if rel.startswith(f"{qt_root}/translations/"):
            base = os.path.basename(rel)
            if base.endswith(".pak"):
                # Chromium locale 资源
                (keep if base in KEEP_WEBENGINE_LOCALES else drop).append(rel)
            else:
                (keep if base.startswith(KEEP_TRANSLATION_PREFIX)
                 else drop).append(rel)
            continue
        if rel.startswith(f"{qt_root}/resources/"):
            base = os.path.basename(rel)
            (keep if base in KEEP_RESOURCES else drop).append(rel)
            continue
        if rel.startswith(f"{qt_root}/qml/"):
            (keep if _category(rel, "qml") in KEEP_QML_DIRS
             else drop).append(rel)
            continue
        keep.append(rel)

    # 5) 依赖自修复：迭代到「每个保留的 PE 的依赖都能满足」为止
    #
    # 这一步取代了「先裁后验」的做法。剪完再验有个致命问题：
    # 校验失败时文件已经被移走，安装包就缺件了。这里改成**先算后动**：
    # 在不动任何文件的前提下，把保留集合修到自洽为止。
    #
    #   - 依赖的 DLL 在产物里存在 → 把它加回保留集合（自修复）
    #   - 依赖的 DLL 根本不在产物里 → 这个 PE 注定加载不了，剔除它
    #     （例如 qpdf.dll 缺 Qt6Pdf.dll、renderers/* 缺 Qt63DRender.dll，
    #      这些 DLL 从来没进过产物，PyInstaller 早就警告过）
    sysnames = _system_dll_names()
    keep_set = set(keep)
    for _round in range(12):
        shipped = {os.path.basename(r).lower() for r in keep_set}
        changed = False
        unusable = []
        for rel in sorted(keep_set):
            if not _is_pe(rel):
                continue
            normal, delay = parse_imports(files[rel])
            missing_present = []
            missing_absent = []
            for d in set(normal + delay):
                low = d.lower()
                if low in shipped or low in sysnames:
                    continue
                if low.startswith(("api-ms-win-", "ext-ms-")):
                    continue
                dep_rel = by_name.get(low)
                if dep_rel and not rel.startswith(f"{qt_root}/qml/"):
                    # 只从 bin / plugins 里补，避免把 qml/ 整棵又拉回来
                    if dep_rel.startswith((f"{qt_root}/bin/", f"{qt_root}/plugins/")):
                        missing_present.append(dep_rel)
                    else:
                        missing_absent.append(d)
                else:
                    missing_absent.append(d)
            if missing_present:
                for m in missing_present:
                    if m not in keep_set:
                        keep_set.add(m)
                        changed = True
            elif missing_absent:
                unusable.append((rel, missing_absent))
        for rel, missing in unusable:
            if rel in keep_set:
                keep_set.discard(rel)
                changed = True
                print(f"⚠️ 剔除无法加载的插件：{os.path.basename(rel)} "
                      f"（缺 {', '.join(missing)}）")
        if not changed:
            break

    final_keep = []
    final_drop = []
    for rel in files:
        (final_keep if rel in keep_set else final_drop).append(rel)
    keep, drop = final_keep, final_drop

    # 6) 剔除「只为死插件而拉进来」的 DLL
    #
    # 上一步把坏插件删掉后，它独占的依赖（典型如 Qt6ShaderTools.dll
    # 只有 rhirenderer.dll 需要）就成了纯冗余。按存活插件重算一次闭包，
    # 把这类 DLL 一并去掉。
    alive_seeds = [rel for rel in seeds if rel in keep_set]
    alive_closure = _expand_closure(files, by_name, alive_seeds)
    for rel in list(keep):
        if not rel.startswith(f"{qt_root}/bin/") or not _is_pe(rel):
            continue
        base = os.path.basename(rel)
        if rel in alive_closure or _match_hint(base, EXTERNAL_DLL_HINTS) \
                or base in DYNAMIC_EXE_KEEP:
            continue
        keep.remove(rel)
        drop.append(rel)

    return keep, drop, needed, files, qt_root


def summarize(keep, drop, files):
    keep_bytes = sum(os.path.getsize(files[r]) for r in keep if r in files)
    drop_bytes = sum(os.path.getsize(files[r]) for r in drop if r in files)
    return keep_bytes, drop_bytes


def _plan_moves(dist, drop, files):
    """把待删项分组，优先整目录搬迁。

    返回 [(源路径, 相对 dist 的路径), ...]。整目录搬迁的好处：
      - 一次 rename 干掉几千个文件，而不是几千次 unlink；
      - 被移走的内容仍在隔离区里，可回溯、可恢复。
    """
    drop_set = set(drop)

    all_dirs = []
    files_under = {}
    for dirpath, dirnames, filenames in os.walk(dist):
        all_dirs.append(dirpath)
    for d in all_dirs:
        s = set()
        for dp, _dn, fns in os.walk(d):
            for fn in fns:
                s.add(os.path.relpath(os.path.join(dp, fn), dist).replace("\\", "/"))
        files_under[d] = s

    # 纯删除目录：底下所有文件都在待删集合里
    pure = [d for d in all_dirs
            if files_under[d] and files_under[d].issubset(drop_set)]
    # 只保留最顶层（避免既搬父目录又搬子目录）
    top_pure = []
    for d in sorted(pure, key=lambda p: p.count(os.sep)):
        if not any(d.startswith(p + os.sep) for p in top_pure):
            top_pure.append(d)

    moves = []
    covered = set()
    for d in top_pure:
        rel = os.path.relpath(d, dist).replace("\\", "/")
        moves.append((d, rel))
        covered |= files_under[d]

    for rel in drop:
        if rel in covered:
            continue
        moves.append((files[rel], rel))
    return moves


def restore_trim(dist, staging):
    """把隔离区里的内容搬回产物目录 —— 裁剪后校验失败时的回滚。

    因为裁剪用的是「搬迁」而不是「删除」，回滚是可行的：
    把隔离区里的文件按相对路径原样搬回即可。
    """
    if not staging or not os.path.isdir(staging):
        return 0
    n = 0
    for dp, _dn, fns in os.walk(staging):
        for fn in fns:
            s = os.path.join(dp, fn)
            d = os.path.join(dist, os.path.relpath(s, staging))
            if os.path.exists(d):
                continue
            os.makedirs(os.path.dirname(d), exist_ok=True)
            try:
                shutil.move(s, d)
                n += 1
            except (OSError, shutil.Error):
                pass
    return n


def apply_trim(dist, dry_run=False, staging=None, purge=False):
    """执行裁剪，返回 (保留文件数, 移除文件数, 释放字节数, 隔离区路径)。

    供 installer/build_windows.py 在「PyInstaller 打包完成 → 签名 → 打安装包」
    这条链路中间调用。顺序很关键：必须先裁再签，否则被裁的文件会白跑一遍
    签名流程（签名 200+ 个 DLL 本身就要好几分钟）。

    默认用**隔离搬迁**（把不要的文件 rename 到 staging 目录）而不是 unlink：
    既快（几千个文件一次 rename），又可回溯、可回滚，
    同时避免触发批量删除保护。purge=True 时改为直接删除。
    """
    keep, drop, needed, files, qt_root = analyze(dist)
    keep_bytes, drop_bytes = summarize(keep, drop, files)

    if dry_run:
        return len(keep), len(drop), drop_bytes, None

    moves = _plan_moves(dist, drop, files)
    removed = 0
    freed = 0
    used_staging = None

    if purge:
        for src, rel in moves:
            if os.path.isdir(src):
                for dp, _dn, fns in os.walk(src):
                    for fn in fns:
                        try:
                            freed += os.path.getsize(os.path.join(dp, fn))
                        except OSError:
                            pass
                try:
                    shutil.rmtree(src)
                except OSError as exc:
                    print(f"⚠️ 删除失败 {rel}: {exc}")
                    continue
            else:
                try:
                    freed += os.path.getsize(src)
                    os.remove(src)
                except OSError as exc:
                    print(f"⚠️ 删除失败 {rel}: {exc}")
                    continue
            removed += 1
    else:
        import time as _time
        used_staging = staging or os.path.join(
            os.path.dirname(os.path.abspath(dist)),
            "_trimmed_out-%d" % int(_time.time()))
        for src, rel in moves:
            dest = os.path.join(used_staging, rel)
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if os.path.isdir(src):
                    freed += sum(
                        os.path.getsize(os.path.join(dp, fn))
                        for dp, _dn, fns in os.walk(src) for fn in fns)
                else:
                    freed += os.path.getsize(src)
                shutil.move(src, dest)
                removed += 1
            except (OSError, shutil.Error) as exc:
                print(f"⚠️ 搬迁失败 {rel}: {exc}")
        print(f"   被裁剪的内容已隔离到：{used_staging}")

    # 清理产物内变空的目录
    for root_dir, dirs, sub_files in os.walk(dist, topdown=False):
        if not dirs and not sub_files:
            try:
                os.rmdir(root_dir)
            except OSError:
                pass

    print(f"✅ 已移除 {removed} 项，释放 {freed/1048576:.1f} MB")
    return len(keep), removed, freed, used_staging


def main():
    ap = argparse.ArgumentParser(description="裁剪产物中的无用 Qt6 运行时载荷")
    ap.add_argument("--dist", default="dist/OmniBrowser", help="产物目录")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不删除")
    ap.add_argument("--purge", action="store_true",
                    help="直接删除而不是隔离搬迁（会触发批量删除保护）")
    ap.add_argument("--verify", action="store_true",
                    help="只做导入表完备性校验，不做裁剪")
    ap.add_argument("--report", default="", help="把裁剪报告写成 JSON 文件")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist = args.dist if os.path.isabs(args.dist) else os.path.join(root, args.dist)
    if not os.path.isdir(dist):
        print(f"❌ 找不到产物目录：{dist}")
        return 1

    if args.verify:
        problems = verify_tree(dist)
        return 1 if problems else 0

    keep, drop, needed, files, qt_root = analyze(dist)
    keep_bytes, drop_bytes = summarize(keep, drop, files)
    total = keep_bytes + drop_bytes

    print("=" * 68)
    print("Qt6 载荷裁剪分析")
    print("=" * 68)
    print(f"产物总文件数：{len(files)}")
    print(f"保留：{len(keep)} 个 / {keep_bytes/1048576:.1f} MB")
    print(f"删除：{len(drop)} 个 / {drop_bytes/1048576:.1f} MB "
          f"({drop_bytes*100.0/max(total,1):.1f}%)")
    print()

    # 按目录汇总删除量，便于核对
    buckets = {}
    for rel in drop:
        parts = rel.split("/")
        key = "/".join(parts[:4]) if len(parts) >= 4 else "/".join(parts)
        buckets.setdefault(key, [0, 0])
        buckets[key][0] += 1
        buckets[key][1] += os.path.getsize(files[rel])
    print("按目录的删除量：")
    for key, (cnt, size) in sorted(buckets.items(), key=lambda kv: -kv[1][1]):
        print(f"  {size/1048576:8.1f} MB  {cnt:5d} 个  {key}")
    print()

    # 依赖闭包里「来自 bin 的 DLL」，逐个列出，确认没误删必需项
    bin_dlls = sorted(
        os.path.basename(r) for r in needed if r.startswith(f"{qt_root}/bin/")
    )
    print(f"依赖闭包内的 Qt DLL（{len(bin_dlls)} 个，必需）：")
    for i in range(0, len(bin_dlls), 4):
        print("  " + "  ".join(f"{n:<32}" for n in bin_dlls[i:i + 4]))
    print()

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"keep": keep, "drop": drop,
                       "keep_bytes": keep_bytes, "drop_bytes": drop_bytes},
                      f, ensure_ascii=False, indent=2)
        print("报告已写入：", args.report)

    if args.dry_run:
        print("--dry-run：未删除任何文件。")
        return 0

    # 实际执行
    _, removed, freed, _staging = apply_trim(dist, purge=args.purge)
    print(f"✅ 已移除 {removed} 项，释放 {freed/1048576:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
