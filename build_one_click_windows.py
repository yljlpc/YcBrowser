#!/usr/bin/env python3
"""Windows 构建脚本：一键构建 Yc浏览器 并保存到桌面

用法：
    build_one_click_windows.py [--bump] [--help]
"""
import os
import sys
import argparse
import shutil
from pathlib import Path

# 添加项目根目录到路径
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

def main():
    parser = argparse.ArgumentParser(description="Windows 一键构建脚本 (Yc浏览器)")
    parser.add_argument("--bump", action="store_true", help="构建前自动递增版本号")
    parser.add_argument("--no-desktop", action="store_true", help="不复制到桌面")
    args = parser.parse_args()

    print(f"=== Yc浏览器 一键构建 (v{args.bump}) ===")

    # 构建 Windows
    print("\n[1/2] 构建 Windows 安装包...")
    build_script = ROOT / "installer" / "build_windows.py"
    result = os.system(f"{sys.executable} {build_script} {'--auto-bump' if args.bump else ''}")

    if result != 0:
        print(f"❌ 构建失败")
        return 1

    print("\n[2/2] 复制安装包到桌面...")
    dist_dir = ROOT / "dist" / "OmniBrowser"
    nsis_installer = ROOT / "installer" / "omnibrowser.nsi"

    if args.no_desktop:
        print(f"已跳过复制桌面")
    else:
        # 获取版本号
        version_path = ROOT / "src" / "version.py"
        version = "1.1.2"
        with open(version_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('VERSION'):
                    version = line.split('"')[1]
                    break

        desktop_dir = Path.home() / "Desktop"
        desktop_dir.mkdir(exist_ok=True)

        # 复制文件夹
        if dist_dir.exists():
            dest = desktop_dir / f"Yc浏览器-{version}-Windows"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(dist_dir, dest)
            print(f"✅ 已保存 folder 到桌面: {dest}")
        else:
            print("⚠️ dist/ 目录不存在")

    print("\n✅ 构建完成！")
    return 0

if __name__ == "__main__":
    sys.exit(main())
