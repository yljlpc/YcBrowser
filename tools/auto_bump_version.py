#!/usr/bin/env python3
"""版本号随修改次数自动递增（供 git pre-commit hook 调用）。

机制：
    在 pre-commit 阶段检查**暂存区**是否包含需要计入版本号的源码变更；
    若有，则把 src/version.py 的修订号（patch）+1，并把结果一并加入暂存区，
    于是「版本号随修改次数自动增加」这一约定由 git 机制强制保证，
    而不是靠人工记得手动改。

判定为「有效修改」的文件（目录级）：
    src/            核心源码
    core/           Rust 核心
    package/        打包脚本
    installer/      安装器
    tools/          构建与发布工具
    build_*.sh      构建入口脚本

不计入：文档（docs/）、README、.gitignore、CI 配置、纯二进制资源等。

用法：
    python tools/auto_bump_version.py            # hook 模式（暂存区已 add 完毕）
    python tools/auto_bump_version.py --check    # 只报告，不修改
    python tools/auto_bump_version.py --force    # 无条件递增
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "src" / "version.py"

# 计入版本号的路径前缀
COUNTED_PREFIXES = (
    "src/",
    "core/",
    "package/",
    "installer/",
    "tools/",
)
# 顶层构建脚本
COUNTED_FILES = re.compile(r"^build_.*\.sh$")

VERSION_RE = re.compile(r'^VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)"', re.MULTILINE)


def run(*args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True)


def staged_files():
    """返回暂存区文件列表。"""
    r = run("git", "diff", "--cached", "--name-only", "--diff-filter=ACMR")
    if r.returncode != 0:
        return []
    return [f for f in r.stdout.splitlines() if f.strip()]


def counted(files):
    out = []
    for f in files:
        if any(f.startswith(p) for p in COUNTED_PREFIXES):
            out.append(f)
        elif COUNTED_FILES.match(f):
            out.append(f)
    return out


def read_version():
    content = VERSION_FILE.read_text(encoding="utf-8")
    m = VERSION_RE.search(content)
    if not m:
        raise SystemExit(f"未在 {VERSION_FILE} 中找到 VERSION 定义")
    return tuple(int(x) for x in m.groups())


def write_version(v):
    content = VERSION_FILE.read_text(encoding="utf-8")
    new = re.sub(
        r'^VERSION\s*=\s*"\d+\.\d+\.\d+"',
        f'VERSION = "{v[0]}.{v[1]}.{v[2]}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    VERSION_FILE.write_text(new, encoding="utf-8")


def main():
    args = sys.argv[1:]
    force = "--force" in args
    check = "--check" in args

    old = read_version()
    if check:
        print(f"当前版本: {old[0]}.{old[1]}.{old[2]}")
        return 0

    if not force:
        files = counted(staged_files())
        if not files:
            print("[auto-bump] 暂存区无源码变更，版本号保持不变。")
            return 0
        print(f"[auto-bump] 检测到 {len(files)} 个源码文件变更，版本号自动递增。")
    else:
        print("[auto-bump] --force：强制递增版本号。")

    new = (old[0], old[1], old[2] + 1)
    write_version(new)
    run("git", "add", str(VERSION_FILE.relative_to(ROOT)))
    print(f"[auto-bump] 版本号 {old[0]}.{old[1]}.{old[2]} → {new[0]}.{new[1]}.{new[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
