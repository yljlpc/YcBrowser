"""最终对照：确定 NSIS 压缩算法的最优选择。

已确立的事实（tools/cmp_compressor.py 四轮实测）：
    zlib       165.1 MB   安装 4.38 s
    lzma       125.9 MB   安装 15.74 s
    solid lzma 123.9 MB   安装 17.40 s

本脚本进一步测：
    zlib + DatablockOptimize   —— zlib 体积能否压小一点而保持速度
    bzip2                      —— NSIS 的另一个选项（通常比 zlib 慢）

以及关键的联合指标：
    下载耗时（按 10 MB/s 有效带宽估算）+ 安装耗时 = 用户总等待时间
"""
import os
import shutil
import subprocess
import sys
import time

REPO = r"F:\2026-11-10-21-14-21"
NSIS = r"C:\Program Files (x86)\NSIS\makensis.exe"
WORK = r"C:\ycbuild\cmp2"

VARIANTS = {
    "zlib_plain": "SetCompressor zlib",
    "zlib_dbo":   "SetCompressor zlib\nSetDatablockOptimize on",
    "bzip2":      "SetCompressor bzip2",
}

# 有效下载带宽（Mbps）——含 TLS 开销与服务器限速的保守估计
DOWNLOAD_MBPS = 80.0


def make_variant(compressor_line, out_dir):
    with open(os.path.join(REPO, "installer", "omnibrowser.nsi"),
              encoding="utf-8", errors="replace") as f:
        src = f.read()
    lines = [l for l in src.splitlines()
             if not l.startswith("SetCompressor")
             and not l.startswith("SetDatablockOptimize")]
    text = "\n".join(lines)
    idx = text.index("Name ")
    end = text.index("\n", idx)
    text = text[:end + 1] + "\n" + compressor_line + "\n" + text[end + 1:]

    os.makedirs(out_dir, exist_ok=True)
    nsi = os.path.join(REPO, "installer", "variant.nsi")
    with open(nsi, "w", encoding="utf-8") as f:
        f.write(text)
    return nsi


def build(name, compressor_line):
    out_dir = os.path.join(WORK, name)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    nsi = make_variant(compressor_line, out_dir)
    exe = os.path.join(out_dir, f"{name}.exe")

    import re as _re
    with open(nsi, encoding="utf-8") as f:
        body = f.read()
    body = _re.sub(r'^\s*OutFile\s+"[^"]*"',
                   lambda _m: 'OutFile "' + exe + '"',
                   body, count=1, flags=_re.M)
    with open(nsi, "w", encoding="utf-8") as f:
        f.write(body)

    t0 = time.perf_counter()
    r = subprocess.run([NSIS, nsi], cwd=os.path.join(REPO, "installer"),
                       capture_output=True, text=True)
    build_s = time.perf_counter() - t0
    try:
        os.remove(nsi)
    except OSError:
        pass
    if not os.path.isfile(exe):
        print(f"  [{name}] 打包失败:\n{r.stdout[-500:]}")
        return None
    size = os.path.getsize(exe) / 1048576
    print(f"  [{name}] 打包 {build_s:.1f} s, 体积 {size:.1f} MB")
    return exe, size


def install_timed(exe, tag):
    dest = os.path.join(WORK, "inst_" + tag)
    shutil.rmtree(dest, ignore_errors=True)
    t0 = time.perf_counter()
    subprocess.run([exe, "/S", f"/D={dest}"], capture_output=True)
    return time.perf_counter() - t0


def main():
    os.makedirs(WORK, exist_ok=True)
    print("=== 打包 ===")
    built = []
    for name, line in VARIANTS.items():
        res = build(name, line)
        if res:
            built.append((name, res[0], res[1]))

    print("\n=== 安装耗时（3 轮交叉）===")
    results = {n: [] for n, _, _ in built}
    for rnd in range(3):
        order = built if rnd % 2 == 0 else list(reversed(built))
        for name, exe, _ in order:
            dt = install_timed(exe, f"{name}_{rnd}")
            results[name].append(dt)
            print(f"  轮{rnd+1} [{name:11s}]: {dt:6.2f} s")

    print("\n=== 汇总：安装耗时 + 估算下载耗时 ===")
    print(f"  {'算法':<12} {'体积MB':>8} {'安装s':>8} {'下载s@80Mbps':>13} {'合计s':>8}")
    for name, _, size in built:
        ts = results[name]
        inst = sum(ts) / len(ts)
        dl = size * 8 / DOWNLOAD_MBPS
        print(f"  {name:<12} {size:>8.1f} {inst:>8.2f} {dl:>13.1f} {inst+dl:>8.1f}")


if __name__ == "__main__":
    main()
