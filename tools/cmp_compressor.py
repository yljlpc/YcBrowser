"""对照实验：同一份产物，只改压缩算法，测各自的安装耗时。

要回答的问题
------------
1.1.14 只剩 135 个文件（1.1.13 是 2840 个）、体积小 38%，
但端到端安装反而慢 30~50%。原假设"文件数是瓶颈"已被实测推翻。

本脚本用**完全相同的产物目录**，只切换 NSIS 的压缩设置，重新打包三个版本：

    A  zlib           （NSIS 默认，1.1.13 用的就是这个）
    B  solid lzma     （当前 1.1.14 的设置）
    C  lzma（非solid） 每文件独立压缩

然后各自静默安装到全新目录，记录端到端耗时。
"""
import os
import shutil
import subprocess
import sys
import time

REPO = r"F:\2026-11-10-21-14-21"
NSIS = r"C:\Program Files (x86)\NSIS\makensis.exe"
WORK = r"C:\ycbuild\cmp_installer"

VARIANTS = {
    "zlib":        "SetCompressor zlib",
    "solid_lzma":  "SetCompressor /SOLID lzma\nSetDatablockOptimize on",
    "lzma":        "SetCompressor lzma",
}


def read_base_nsi():
    with open(os.path.join(REPO, "installer", "omnibrowser.nsi"),
              encoding="utf-8", errors="replace") as f:
        return f.read()


def make_variant(name, compressor_line, out_dir):
    """基于主 nsi 生成变体脚本，只替换压缩设置。

    脚本必须放在 installer/ 目录下 —— nsi 里所有路径（图标、
    File /r "..\\dist\\OmniBrowser\\*.*"）都是相对于脚本位置的。
    """
    src = read_base_nsi()
    # 去掉原有的压缩设置块
    out_lines = []
    for line in src.splitlines():
        if line.startswith("SetCompressor"):
            continue
        if line.startswith("SetDatablockOptimize"):
            continue
        out_lines.append(line)
    text = "\n".join(out_lines)

    # 插到 Name 之后
    marker = "!define /redef MUI_ABORTWARNING"
    if marker not in text:
        marker = "Name"
    idx = text.index(marker)
    end = text.index("\n", idx)
    text = text[:end + 1] + "\n" + compressor_line + "\n" + text[end + 1:]

    os.makedirs(out_dir, exist_ok=True)
    nsi_path = os.path.join(out_dir, "variant.nsi")
    with open(nsi_path, "w", encoding="utf-8") as f:
        f.write(text)
    return nsi_path


def build(name, compressor_line):
    out_dir = os.path.join(WORK, name)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    # nsi 必须落在 installer/ 内，否则图标与载荷的相对路径解析不到
    nsi = make_variant(name, compressor_line, os.path.join(REPO, "installer"))

    exe = os.path.join(out_dir, f"{name}.exe")
    # 脚本用 OutFile 决定输出名，直接改写它
    with open(nsi, encoding="utf-8") as f:
        body = f.read()
    import re as _re
    body = _re.sub(r'^\s*OutFile\s+"[^"]*"',
                   lambda _m: 'OutFile "' + exe + '"',
                   body, count=1, flags=_re.M)
    with open(nsi, "w", encoding="utf-8") as f:
        f.write(body)

    t0 = time.perf_counter()
    r = subprocess.run(
        [NSIS, nsi],
        cwd=os.path.join(REPO, "installer"),
        capture_output=True, text=True,
    )
    build_s = time.perf_counter() - t0
    try:
        os.remove(nsi)
    except OSError:
        pass
    if not os.path.isfile(exe):
        print(f"  [{name}] 打包失败:\n{r.stdout[-800:]}\n{r.stderr[-800:]}")
        return None
    size = os.path.getsize(exe) / 1048576
    print(f"  [{name}] 打包 {build_s:.1f} s, 体积 {size:.1f} MB")
    return exe


def install_timed(exe, tag):
    dest = os.path.join(WORK, "inst_" + tag)
    shutil.rmtree(dest, ignore_errors=True)
    t0 = time.perf_counter()
    p = subprocess.run([exe, "/S", f"/D={dest}"], capture_output=True)
    dt = time.perf_counter() - t0
    n = sum(len(f) for _, _, f in os.walk(dest))
    return dt, n


def main():
    os.makedirs(WORK, exist_ok=True)
    print("=== 打包三个变体（产物完全相同，仅压缩算法不同）===")
    built = []
    for name, line in VARIANTS.items():
        e = build(name, line)
        if e:
            built.append((name, e))

    print("\n=== 安装耗时对照（每种跑 4 轮，交叉顺序）===")
    results = {n: [] for n, _ in built}
    for rnd in range(4):
        order = built if rnd % 2 == 0 else list(reversed(built))
        for name, exe in order:
            dt, n = install_timed(exe, f"{name}_{rnd}")
            results[name].append(dt)
            print(f"  轮{rnd+1} [{name:11s}]: {dt:6.2f} s  ({n} 个文件)")

    print("\n=== 汇总 ===")
    for name, _ in built:
        ts = results[name]
        print(f"  {name:11s}: 最快 {min(ts):6.2f} s  最慢 {max(ts):6.2f} s  平均 {sum(ts)/len(ts):6.2f} s")


if __name__ == "__main__":
    main()
