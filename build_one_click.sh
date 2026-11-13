#!/bin/bash
# 一键构建脚本：构建 Yc浏览器 并生成桌面安装文件
# 用法：./build_one_click.sh --help

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 函数：打印信息
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 函数：获取当前版本号
get_version() {
    grep 'VERSION' src/version.py | cut -d'"' -f2
}

# 函数：保存文件到桌面
save_to_desktop() {
    local file="$1"
    if [ -f "$file" ]; then
        local desktop="~/桌面"
        mkdir -p "$desktop"
        cp "$file" "$desktop/"
        local filename=$(basename "$file")
        print_info "已保存安装文件到桌面: $desktop/$filename"
        return 0
    else
        print_error "文件不存在: $file"
        return 1
    fi
}

# 函数：构建 Linux deb 包
build_linux() {
    local auto_bump="$1"
    local bump_flag=""
    [ "$auto_bump" = "1" ] && bump_flag="--auto-bump"
    
    print_info "开始构建 Linux 安装包..."
    
    if python3 package/build_debs.sh $bump_flag; then
        print_info "Linux 构建成功！"
        
        # 保存到桌面
        local version=$(get_version)
        local openkylin_pkg="$ROOT/package/omnibrowser_${version}_amd64.deb"
        local deepin_pkg="$ROOT/package/omnibrowser-deepin_${version}_amd64.deb"
        
        if [ -f "$openkylin_pkg" ]; then
            save_to_desktop "$openkylin_pkg"
        fi
        if [ -f "$deepin_pkg" ]; then
            save_to_desktop "$deepin_pkg"
        fi
        return 0
    else
        print_error "Linux 构建失败！"
        return 1
    fi
}

# 函数：构建 Windows exe（仅支持 Windows 环境）
build_windows() {
    if [[ "$OSTYPE" != "msys" && "$OSTYPE" != "win32" ]]; then
        print_warn "此脚本仅可在 Windows 环境构建 Windows 安装包"
        return 0
    fi
    
    local auto_bump="$1"
    local bump_flag=""
    [ "$auto_bump" = "1" ] && bump_flag="--auto-bump"
    
    print_info "开始构建 Windows 安装包..."
    
    if python3 installer/build_windows.py $bump_flag; then
        print_info "Windows 构建成功（检查 dist/ 目录）"
        return 0
    else
        print_error "Windows 构建失败！"
        return 1
    fi
}

# 函数：显示帮助
show_help() {
    cat << EOF
Yc浏览器 一键构建脚本

用法: $0 [选项]

选项:
  --linux           仅构建 Linux deb 包 (默认)
  --windows         仅构建 Windows exe/package
  --all             构建所有平台
  --bump            构建前自动递增版本号
  --help            显示此帮助信息

示例:
  $0 --linux --bump        # 构建 Linux 并递增版本号
  $0 --all                 # 构建所有平台

输出:
  - Linux deb 包 -> ~桌面/
  - Windows exe  -> dist/

版本: $(get_version)
EOF
}

# 解析参数
AUTO_BUMP="0"
BUILD_LINUX="0"
BUILD_WINDOWS="0"

for arg in "$@"; do
    case $arg in
        --linux) BUILD_LINUX="1" ;;
        --windows) BUILD_WINDOWS="1" ;;
        --all) BUILD_LINUX="1"; BUILD_WINDOWS="1" ;;
        --bump) AUTO_BUMP="1" ;;
        --help) show_help; exit 0 ;;
    esac
done

# 默认构建 Linux
[ "$BUILD_LINUX" = "0" ] && [ "$BUILD_WINDOWS" = "0" ] && BUILD_LINUX="1"

print_info "当前版本号: $(get_version)"

# 执行构建
if [ "$BUILD_LINUX" = "1" ]; then
    build_linux $AUTO_BUMP
fi

if [ "$BUILD_WINDOWS" = "1" ]; then
    build_windows $AUTO_BUMP
fi

print_info "构建完成！"
