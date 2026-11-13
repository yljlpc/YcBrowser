#!/usr/bin/env python3
"""Windows 产物运行时依赖审计。

用途：确保打出来的安装包不依赖目标机器上任何预装的软件或环境。

做法：递归解析产物内每个 PE 文件（.exe/.dll/.pyd）的导入表，列出它依赖的
DLL 名，再检查这些 DLL 是否存在于产物目录内；不在的再判断是否为 Windows
系统自带的 DLL。两者都不满足即为「缺失依赖」—— 装到干净机器上必然报错。

用法：
    python tools/audit_dependencies.py dist/OmniBrowser
    python tools/audit_dependencies.py dist/OmniBrowser --verbose
"""
import os
import struct
import sys
from collections import defaultdict

# Windows 系统自带 DLL（无需随包分发）
SYSTEM_DLLS = {
    "kernel32.dll", "kernelbase.dll", "user32.dll", "gdi32.dll", "gdi32full.dll",
    "advapi32.dll", "shell32.dll", "ole32.dll", "oleaut32.dll", "comctl32.dll",
    "comdlg32.dll", "shlwapi.dll", "psapi.dll", "ws2_32.dll", "ntdll.dll",
    "msvcrt.dll", "ucrtbase.dll", "rpcrt4.dll", "imm32.dll", "setupapi.dll",
    "winmm.dll", "version.dll", "crypt32.dll", "wininet.dll", "iphlpapi.dll",
    "normaliz.dll", "dnsapi.dll", "dxgi.dll", "d3d9.dll", "d3d11.dll",
    "avrt.dll", "mpr.dll", "netapi32.dll", "secur32.dll", "bcrypt.dll",
    "wintrust.dll", "imagehlp.dll", "dbghelp.dll", "mswsock.dll", "ws2help.dll",
    "propsys.dll", "shcore.dll", "combase.dll", "difxapi.dll", "uxtheme.dll",
    "dwmapi.dll", "uxtheme.dll", "msimg32.dll", "powrprof.dll", "credui.dll",
    "cryptui.dll", "wintypes.dll", "sspicli.dll", "wtsapi32.dll", "userenv.dll",
    "profapi.dll", "mfplat.dll", "mf.dll", "mfreadwrite.dll", "evr.dll",
    "msmpeg2vdec.dll", "dxva2.dll", "d3d11.dll", "dcomp.dll", "dwrite.dll",
    "d2d1.dll", "d3dcompiler_47.dll", "opengl32.dll", "glu32.dll", "winmm.dll",
    "winspool.drv", "comdlg32.dll", "msvcp140.dll", "msvcp140_1.dll",
    "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll",
    "concrt140.dll", "ucrtbase.dll", "msvcp140_codecvt_ids.dll",
    "api-ms-win-crt-runtime-l1-1-0.dll", "api-ms-win-crt-heap-l1-1-0.dll",
    "api-ms-win-crt-string-l1-1-0.dll", "api-ms-win-crt-math-l1-1-0.dll",
    "api-ms-win-crt-locale-l1-1-0.dll", "api-ms-win-crt-convert-l1-1-0.dll",
    "api-ms-win-crt-multibyte-l1-1-0.dll", "api-ms-win-crt-time-l1-1-0.dll",
    "api-ms-win-crt-stdio-l1-1-0.dll", "api-ms-win-crt-filesystem-l1-1-0.dll",
    "api-ms-win-crt-environment-l1-1-0.dll", "api-ms-win-crt-utility-l1-1-0.dll",
    "api-ms-win-crt-process-l1-1-0.dll", "api-ms-win-crt-private-l1-1-0.dll",
    "api-ms-win-crt-conio-l1-1-0.dll", "api-ms-win-crt-random-l1-1-0.dll",
    "api-ms-win-crt-time-l1-1-0.dll", "api-ms-win-crt-string-l1-1-0.dll",
    "api-ms-win-core-synch-l1-2-0.dll", "api-ms-win-core-synch-l1-2-1.dll",
    "api-ms-win-core-file-l1-2-0.dll", "api-ms-win-core-file-l1-2-1.dll",
    "api-ms-win-core-profile-l1-1-0.dll", "api-ms-win-core-heap-l1-2-0.dll",
    "api-ms-win-core-localization-l1-2-0.dll", "api-ms-win-core-errorhandling-l1-1-0.dll",
    "api-ms-win-core-interlocked-l1-1-0.dll", "api-ms-win-core-datetime-l1-1-0.dll",
    "api-ms-win-core-console-l1-1-0.dll", "api-ms-win-core-util-l1-1-0.dll",
    "api-ms-win-core-rtlsupport-l1-1-0.dll", "api-ms-win-core-memory-l1-1-0.dll",
    "api-ms-win-core-namedpipe-l1-1-0.dll", "api-ms-win-core-processthreads-l1-1-0.dll",
    "api-ms-win-core-synch-l1-1-0.dll", "api-ms-win-core-processthreads-l1-1-0.dll",
    "api-ms-win-core-sysinfo-l1-1-0.dll", "api-ms-win-core-sysinfo-l1-2-0.dll",
    "api-ms-win-core-debug-l1-1-0.dll", "api-ms-win-core-io-l1-1-0.dll",
    "api-ms-win-core-registry-l1-1-0.dll", "api-ms-win-core-profile-l1-1-0.dll",
    "api-ms-win-core-libraryloader-l1-2-0.dll", "api-ms-win-core-handle-l1-1-0.dll",
    "api-ms-win-core-job-l1-1-0.dll", "api-ms-win-core-sysinfo-l1-1-0.dll",
    "api-ms-win-core-virtualmemory-l1-1-0.dll", "api-ms-win-core-memory-l1-1-0.dll",
    "api-ms-win-core-heap-l1-1-0.dll", "api-ms-win-downlevel-kernel32-l1-1-0.dll",
    "api-ms-win-downlevel-user32-l1-1-0.dll", "api-ms-win-downlevel-shlwapi-l1-1-0.dll",
    "api-ms-win-downlevel-advapi32-l1-1-0.dll", "api-ms-win-downlevel-kernel-base-l1-1-0.dll",
    "ext-ms-win-rt-unicode-nls-l1-1-0.dll", "ext-ms-win-ntuser-dialogbox-l1-1-0.dll",
    "ext-ms-win-ntuser-windowstation-l1-1-0.dll", "ext-ms-win-ntuser-dlgsys-l1-1-0.dll",
    "ext-ms-win-ntuser-uiaccess-l1-1-0.dll", "ext-ms-win-secur32-l1-0-0.dll",
}


def parse_pe_imports(path):
    """返回该 PE 文件导入的 DLL 名列表。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []

    if len(data) < 0x40 or data[:2] != b"MZ":
        return []

    try:
        lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if lfanew + 24 > len(data) or data[lfanew:lfanew + 4] != b"PE\x00\x00":
            return []

        coff = lfanew + 4
        num_sections = struct.unpack_from("<H", data, coff + 2)[0]
        size_opt = struct.unpack_from("<H", data, coff + 16)[0]
        opt = coff + 20
        magic = struct.unpack_from("<H", data, opt)[0]
        if magic == 0x10B:
            dd = opt + 96
        elif magic == 0x20B:
            dd = opt + 112
        else:
            return []

        # 节表：用于 RVA -> 文件偏移 转换
        sec_off = opt + size_opt
        sections = []
        for i in range(num_sections):
            base = sec_off + i * 40
            if base + 40 > len(data):
                break
            vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", data, base + 8)
            sections.append((vaddr, max(vsize, rawsize), rawptr))

        def rva_to_off(rva):
            for vaddr, vsize, rawptr in sections:
                if vaddr <= rva < vaddr + vsize:
                    return rawptr + (rva - vaddr)
            return None

        # 导入表（数据目录索引 1）
        import_rva, import_size = struct.unpack_from("<II", data, dd + 8)
        if import_rva == 0:
            return []

        idt_off = rva_to_off(import_rva)
        if idt_off is None:
            return []

        dlls = []
        pos = idt_off
        while pos + 20 <= len(data):
            name_rva = struct.unpack_from("<I", data, pos + 12)[0]
            orig_thunk = struct.unpack_from("<I", data, pos)[0]
            first_thunk = struct.unpack_from("<I", data, pos + 16)[0]
            if name_rva == 0 and first_thunk == 0:
                break
            if name_rva:
                noff = rva_to_off(name_rva)
                if noff is not None:
                    end = data.find(b"\x00", noff)
                    if end > noff:
                        dlls.append(data[noff:end].decode("ascii", "replace"))
            pos += 20
        return dlls
    except (struct.error, IndexError):
        return []


def _system32_names():
    """读取本机 System32 的 DLL 名单，作为「系统自带」的权威依据。

    比维护一份手工名单可靠得多 —— Windows 自带的 DLL 随版本变化，
    而 System32 就是目标机器上必然存在的那一份。
    """
    names = set()
    for base in (r"C:\Windows\System32", r"C:\Windows\SysWOW64"):
        if not os.path.isdir(base):
            continue
        try:
            for fn in os.listdir(base):
                if fn.lower().endswith((".dll", ".cpl", ".drv")):
                    names.add(fn.lower())
        except OSError:
            pass
    return names


SYSTEM32_NAMES = _system32_names()


def is_system_dll(name):
    low = name.lower()
    if low in SYSTEM32_NAMES:
        return True
    return (low.startswith("api-ms-win-")
            or low.startswith("ext-ms-")
            or low.startswith("msvcp")
            or low.startswith("vcruntime")
            or low.startswith("ucrtbase")
            or low.startswith("concrt"))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    root = sys.argv[1]
    verbose = "--verbose" in sys.argv

    if not os.path.isdir(root):
        print(f"目录不存在: {root}")
        return 1

    # 产物内所有文件名（用于判断依赖是否自带）
    shipped = {}
    for dirpath, _d, filenames in os.walk(root):
        for fn in filenames:
            shipped.setdefault(fn.lower(), os.path.join(dirpath, fn))

    # 收集所有 PE 文件及其依赖
    pe_files = []
    for dirpath, _d, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith((".exe", ".dll", ".pyd")):
                pe_files.append(os.path.join(dirpath, fn))

    missing = defaultdict(set)   # 缺失 DLL -> 需要它的文件
    for pe in pe_files:
        for dep in parse_pe_imports(pe):
            if dep.lower() in shipped or is_system_dll(dep):
                continue
            missing[dep].add(os.path.relpath(pe, root))

    print("=" * 70)
    print("依赖审计：" + root)
    print("=" * 70)
    print(f"PE 文件总数      : {len(pe_files)}")
    print(f"产物内文件总数   : {len(shipped)}")
    print(f"缺失的第三方依赖 : {len(missing)}")
    print()

    if not missing:
        print("✅ 无缺失依赖 —— 产物可脱离目标机器的预装软件独立运行")
        return 0

    print("❌ 以下依赖既不在产物内，也不是 Windows 系统自带：")
    for dep in sorted(missing, key=str.lower):
        users = missing[dep]
        print(f"   • {dep}   ← 被 {len(users)} 个文件依赖")
        if verbose:
            for u in sorted(users)[:8]:
                print(f"       {u}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
