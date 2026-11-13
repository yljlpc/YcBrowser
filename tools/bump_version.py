#!/usr/bin/env python3
"""版本号自动递增工具。

用法：
    python tools/bump_version.py [--major|--minor]   # 指定版本号级别
    python tools/bump_version.py                     # 默认修订号 +1

功能：
- 自动读取 src/version.py 中的当前版本号
- 递增版本号（默认修订号 +1）
- 更新 version.py 文件
- 显示版本号变更历史
"""
import re
import sys
import argparse
from pathlib import Path

def read_version(filepath: Path) -> tuple[int, int, int]:
    """读取版本号生成三整数元组 (major, minor, patch)"""
    pattern = r'^VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)"'
    content = filepath.read_text(encoding="utf-8")
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        raise ValueError(f"未找到 VERSION 定义: {filepath}")
    major, minor, patch = map(int, match.groups())
    return major, minor, patch

def increase_version(major: int, minor: int, patch: int, level: str = "patch") -> tuple[int, int, int]:
    """根据级别递增版本号"""
    if level == "major":
        major += 1
        minor = 0
        patch = 0
    elif level == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    return major, minor, patch

def write_version(filepath: Path, version: tuple[int, int, int]) -> None:
    """将版本号写入 version.py"""
    original = filepath.read_text(encoding="utf-8")
    version_str = f"{version[0]}.{version[1]}.{version[2]}"
    # 匹配 VERSION = "1.1.0"
    new = re.sub(
        r'^VERSION\s*=\s*"\d+\.\d+\.\d+"',
        f'VERSION = "{version_str}"',
        original,
        count=1,
        flags=re.MULTILINE
    )
    if new == original:
        print("错误：未能更新 version.py", file=sys.stderr)
        sys.exit(1)
    filepath.write_text(new, encoding="utf-8")
    print(f"版本号更新为: {version_str}")

def main():
    parser = argparse.ArgumentParser(description="版本号自动递增工具")
    parser.add_argument(
        "--major",
        action="store_true",
        help="主版本号递增 (如 1.1.0 -> 2.0.0)"
    )
    parser.add_argument(
        "--minor",
        action="store_true",
        help="次版本号递增 (如 1.1.0 -> 1.2.0)"
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="仅显示当前版本号，不更新"
    )
    args = parser.parse_args()

    # 获取版本文件路径
    root = Path(__file__).parent.parent
    version_file = root / "src" / "version.py"

    if not version_file.exists():
        print(f"错误：未找到 {version_file}", file=sys.stderr)
        sys.exit(1)

    major, minor, patch = read_version(version_file)

    if args.no_update:
        print(f"当前版本号: {major}.{minor}.{patch}")
        return

    # 根据级别递增
    level = "major" if args.major else ("minor" if args.minor else "patch")
    new_version = increase_version(major, minor, patch, level)

    write_version(version_file, new_version)

    print(f"\n✅ 版本变更完成")
    print(f"旧版本: {major}.{minor}.{patch}")
    print(f"新版本: {'.'.join(map(str, new_version))}")
    print(f"\n提示：运行 'python package/build_debs.sh' 或 'python installer/build_windows.py' 构建新包")

if __name__ == "__main__":
    main()
