#!/bin/bash
# 构建完全独立的 Yc浏览器 安装包（包含所有 PyQt6/Qt6 依赖）
# 生成的安装包可以在任何Linux系统上直接运行，无需安装额外依赖

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 获取版本号
VERSION=$(grep 'VERSION' src/version.py | cut -d'"' -f2)

# 解析参数
AUTO_BUMP="0"
for arg in "$@"; do
    case $arg in
        --bump) AUTO_BUMP="1" ;;
        --help)
            cat << EOF
Yc浏览器 完全独立安装包构建脚本

用法: $0 [选项]

选项:
  --bump       构建前自动递增版本号
  --help       显示此帮助信息

产出:
  - package/omnibrowser_${VERSION}_linux_kits_ng_amd64.deb
    完全独立的安装包，包含所有 PyQt6/Qt6 依赖，可在任何 Linux 系统上运行

EOF
            exit 0
            ;;
    esac
done

# 如果需要自动递增版本号
if [ "$AUTO_BUMP" = "1" ]; then
    print_info "自动递增版本号..."
    python3 tools/bump_version.py || exit 1
    VERSION=$(grep 'VERSION' src/version.py | cut -d'"' -f2)
fi

# 构建版本
print_info "构建版本: $VERSION"

# 使用项目目录下的临时目录（避免tmpfs空间不足）
PROJECT_TMP="$ROOT/.workbuddy/tmp"
mkdir -p "$PROJECT_TMP"
TMP=$(mktemp -d "$PROJECT_TMP/buil_independent.XXXXXX")
print_info "临时目录: $TMP (使用项目目录临时空间)"

# 创建目录结构
print_info "创建目录结构..."
mkdir -p "$TMP/opt/omnibrowser/src"
mkdir -p "$TMP/opt/omnibrowser/lib/python3/dist-packages"
mkdir -p "$TMP/usr/bin"
mkdir -p "$TMP/usr/share/applications"
mkdir -p "$TMP/DEBIAN"
mkdir -p "$TMP/usr/share/icons/hicolor/24/apps"
mkdir -p "$TMP/usr/share/icons/hicolor/256/apps"

# 复制核心文件
print_info "复制核心文件..."
cp "$ROOT/core/target/release/omnibrowser-core" "$TMP/opt/omnibrowser/omnibrowser-core"
chmod +x "$TMP/opt/omnibrowser/omnibrowser-core"

# 复制 Python 源码
print_info "复制 Python 源码..."
cp "$ROOT/src"/*.py "$TMP/opt/omnibrowser/src/"

# 复制 PyQt6/Qt6 库 (关键步骤)
print_info "复制 PyQt6/Qt6 库..."
if [ -d "$ROOT/_stage/pyqt6root/usr/lib/python3/dist-packages/PyQt6" ]; then
    cp -r "$ROOT/_stage/pyqt6root/usr/lib/python3/dist-packages/PyQt6" \
          "$TMP/opt/omnibrowser/lib/python3/dist-packages/"
    print_info "PyQt6 核心库已复制"
else
    print_error "PyQt6 核心库不存在，请先构建 _stage/pyqt6root"
    exit 1
fi

# 复制所有需要的 dist-info
for di in pyqt6-6.10.2.dist-info pyqt6_sip-13.11.0.dist-info pyqt6_webengine-6.10.0.dist-info; do
    if [ -d "$ROOT/_stage/pyqt6root/usr/lib/python3/dist-packages/$di" ]; then
        cp -r "$ROOT/_stage/pyqt6root/usr/lib/python3/dist-packages/$di" \
              "$TMP/opt/omnibrowser/lib/python3/dist-packages/"
        print_info "复制了 $di"
    else
        print_warn "未找到 $di"
    fi
done

# 复制启动器
print_info "复制启动器..."
if [ -f "$ROOT/installer/omnibrowser-launch.sh" ]; then
    cp "$ROOT/installer/omnibrowser-launch.sh" "$TMP/usr/bin/omnibrowser"
    chmod +x "$TMP/usr/bin/omnibrowser"
else
    # 创建简化的启动脚本
    cat > "$TMP/usr/bin/omnibrowser" <<EOF
#!/bin/bash
export PYTHONPATH="\$0/../opt/omnibrowser/src:\$0/../opt/omnibrowser/lib/python3/dist-packages"
exec python3 "\$0/../opt/omnibrowser/src/main.py" "\$@"
EOF
    chmod +x "$TMP/usr/bin/omnibrowser"
fi

# 复制图标
print_info "复制图标..."
if [ -d "$ROOT/assets/hicolor/24x24/apps" ]; then
    mkdir -p "$TMP/usr/share/icons/hicolor/24/apps"
    cp "$ROOT/assets/hicolor/24x24/apps/omnibrowser.png" "$TMP/usr/share/icons/hicolor/24/apps/"
fi
if [ -d "$ROOT/assets/hicolor/256x256/apps" ]; then
    mkdir -p "$TMP/usr/share/icons/hicolor/256/apps"
    cp "$ROOT/assets/hicolor/256x256/apps/omnibrowser.png" "$TMP/usr/share/icons/hicolor/256/apps/"
fi

# 生成 .desktop 文件
print_info "生成 .desktop 文件..."
cat > "$TMP/usr/share/applications/omnibrowser.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Yc浏览器
Exec=omnibrowser %U
Icon=omnibrowser
Terminal=false
Categories=Network;WebBrowser;
EOF

# 生成控制文件（无依赖）
print_info "生成控制文件..."
cat > "$TMP/DEBIAN/control" <<EOF
Package: omnibrowser
Version: $VERSION
Section: web
Priority: optional
Architecture: amd64
Depends:
Maintainer: Yc <yc@omnibrowser.local>
Description: Yc浏览器 —— 完全独立版（包含所有 PyQt6/Qt6 依赖）
 一款以 Rust 原生核心 + PyQt6（Qt 6）构建的多功能桌面浏览器，支持实时翻译与高速下载。
 此版本包含所有必要的依赖，可在任何 Linux 系统上直接运行，无需安装额外的库。
 渲染核心为 Blink（QtWebEngine），并提供 WebKit 兼容 UA 与 Trident 兼容模式。
EOF

# 构建 deb 包
print_info "构建 deb 包..."
fakeroot dpkg-deb --build "$TMP" "$ROOT/package/omnibrowser_${VERSION}_linux_kits_ng_amd64.deb"

print_info "✅ 构建成功!"
echo "包路径: $ROOT/package/omnibrowser_${VERSION}_linux_kits_ng_amd64.deb"
ls -lh "$ROOT/package/omnibrowser_${VERSION}_linux_kits_ng_amd64.deb"

# 复制到桌面
cp "$ROOT/package/omnibrowser_${VERSION}_linux_kits_ng_amd64.deb" ~/桌面/
print_info "✅ 已复制到桌面: ~/桌面/omnibrowser_${VERSION}_linux_kits_ng_amd64.deb"

print_info "\n验证包信息..."
dpkg-deb -f "$ROOT/package/omnibrowser_${VERSION}_linux_kits_ng_amd64.deb" | head -10

# 清理临时目录
echo "\n清理临时目录..."
rm -rf "$TMP"

print_info "\n提供的演示脚本样例..."
echo "使用方式:"
echo "  ./package/omnibrowser_${VERSION}_linux_kits_ng_amd64.deb  # 通过文件管理器打开安装"
echo "  sudo apt install ./package/omnibrowser_${VERSION}_linux_kits_ng_amd64.deb  # 通过终端安装"
echo "  omnibrowser  # 不需要 sudo，只需在 PATH 中即可运行"
