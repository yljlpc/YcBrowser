"""测量 NSIS 安装包各阶段耗时，定位安装慢的真实原因。

要回答的问题
------------
1.1.14 只剩 134 个文件（1.1.13 是 2840 个），体积也小 38%，
但端到端安装耗时反而略长。本脚本把耗时拆成三段：

    [解压]   从安装包读出并解压全部文件到临时目录
    [写盘]   把临时文件复制到最终安装目录
    [签名]   每个可执行文件的 Authenticode 校验（Windows 加载时做）

如果 [解压] 占大头，说明瓶颈是压缩/IO 而不是文件数；
如果 [签名] 占大头，说明自签证书链的校验成本高 —— 这正好指向
SignPath（公共 CA 证书的链更短、校验更快）。
"""
import os
import shutil
import subprocess
import sys
import time

NSIS_EXTRACTORS = [
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
]


def find_extractor():
    for p in NSIS_EXTRACTORS:
        if os.path.isfile(p):
            return p
    return None


def time_copy(src, dst):
    """纯写盘耗时：复制已解压好的文件到目标目录。"""
    t0 = time.perf_counter()
    total = 0
    for root, _, files in os.walk(src):
        for f in files:
            s = os.path.join(root, f)
            rel = os.path.relpath(s, src)
            d = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
            total += os.path.getsize(s)
    return time.perf_counter() - t0, total


def time_sign_check(root):
    """让 Windows 对每个 PE 做一次 Authenticode 校验，模拟加载期成本。"""
    t0 = time.perf_counter()
    n = 0
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith((".exe", ".dll", ".pyd")):
                p = os.path.join(dirpath, f)
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command",
                     f"(Get-AuthenticodeSignature -LiteralPath '{p}').Status"],
                    capture_output=True, text=True,
                )
                n += 1
    return time.perf_counter() - t0, n


def main():
    pkg = sys.argv[1] if len(sys.argv) > 1 else \
        r"C:\Users\Administrator\Desktop\yc-browser-1.1.14-windows-x86_64-setup.exe"
    work = r"C:\ycbuild\phase_test"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)

    print(f"安装包: {pkg}")
    print(f"体积  : {os.path.getsize(pkg)/1048576:.1f} MB\n")

    # 阶段 1：解压
    ex = find_extractor()
    extract_s = None
    if ex:
        dest = os.path.join(work, "extracted")
        os.makedirs(dest, exist_ok=True)
        t0 = time.perf_counter()
        r = subprocess.run([ex, "x", "-y", f"-o{dest}", pkg],
                           capture_output=True, text=True)
        extract_s = time.perf_counter() - t0
        nfiles = sum(len(f) for _, _, f in os.walk(dest))
        print(f"[解压] {extract_s:.2f} s  -> {nfiles} 个文件")
        if r.returncode != 0:
            print("  7z 错误:", r.stdout[-400:], r.stderr[-400:])
    else:
        print("[解压] 未找到 7z，跳过")

    # 阶段 2：写盘
    if ex:
        t, total = time_copy(os.path.join(work, "extracted"),
                              os.path.join(work, "installed"))
        print(f"[写盘] {t:.2f} s  -> {total/1048576:.1f} MB")

        # 阶段 3：签名校验
        t, n = time_sign_check(os.path.join(work, "installed"))
        print(f"[签名] {t:.2f} s  -> 校验 {n} 个 PE")


if __name__ == "__main__":
    main()
