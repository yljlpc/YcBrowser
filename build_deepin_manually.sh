#!/bin/bash
set -e

ROOT="/home/YCSM/WorkBuddy/2026-11-10-21-14-21"
PKG="$ROOT/package"
TMP=$(mktemp -d)
VERSION=$(grep 'VERSION' "$ROOT/src/version.py" | cut -d'"' -f2)

echo "=== 构建 Yc浏览器 deepin deb (v$VERSION) ==="
echo "临时目录: $TMP"

# 创建目录结构
echo "创建目录结构..."
mkdir -p "$TMP/opt/omnibrowser/src"
mkdir -p "$TMP/opt/omnibrowser/fonts"
mkdir -p "$TMP/usr/bin"
mkdir -p "$TMP/usr/share/applications"
mkdir -p "$TMP/DEBIAN"
mkdir -p "$TMP/usr/share/icons/hicolor/24/apps"
mkdir -p "$TMP/usr/share/icons/hicolor/256/apps"

# 复制文件
echo "复制核心文件..."
cp "$ROOT/core/target/release/omnibrowser-core" "$TMP/opt/omnibrowser/omnibrowser-core"
chmod +x "$TMP/opt/omnibrowser/omnibrowser-core"

echo "复制 Python 源码..."
cp "$ROOT/src"/*.py "$TMP/opt/omnibrowser/src/"

echo "复制启动器..."
cp "$ROOT/installer/omnibrowser-launch.sh" "$TMP/usr/bin/omnibrowser-launch.sh"
chmod +x "$TMP/usr/bin/omnibrowser-launch.sh"
# 创建简化的启动脚本
echo "#!/bin/bash" > "$TMP/usr/bin/omnibrowser"
echo "exec \$ROOT/installer/omnibrowser-launch.sh" >> "$TMP/usr/bin/omnibrowser"
chmod +x "$TMP/usr/bin/omnibrowser"

# 复制图标
echo "复制图标..."
cp "$ROOT/assets/hicolor/24x24/apps/omnibrowser.png" "$TMP/usr/share/icons/hicolor/24/apps/"
cp "$ROOT/assets/hicolor/256x256/apps/omnibrowser.png" "$TMP/usr/share/icons/hicolor/256/apps/"

# 生成 .desktop 文件
echo "生成 .desktop 文件..."
cat > "$TMP/usr/share/applications/omnibrowser.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Yc浏览器
Exec=omnibrowser %U
Icon=omnibrowser
Terminal=false
Categories=Network;WebBrowser;
EOF

# 生成控制文件
echo "生成控制文件..."
cat > "$TMP/DEBIAN/control" <<EOF
Package: omnibrowser
Version: $VERSION
Section: web
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.10), python3-pyqt6 (>= 6.4), python3-pyqt6.webengine (>= 6.4), libqt6webengine6-data
Maintainer: Yc <yc@omnibrowser.local>
Description: Yc浏览器 —— 多引擎浏览器（Blink / WebKit / Trident 兼容）
 一款以 Rust 原生核心 + PyQt6 构建的多功能桌面浏览器，支持实时翻译与高速下载。
EOF

echo "构建 deb 包..."
fakeroot dpkg-deb --build "$TMP" "$PKG/omnibrowser-deepin_${VERSION}_amd64.deb"

echo "✅ 构建成功!"
echo "包路径: $PKG/omnibrowser-deepin_${VERSION}_amd64.deb"
ls -lh "$PKG/omnibrowser-deepin_${VERSION}_amd64.deb"

echo -e "\n复制到桌面..."
cp "$PKG/omnibrowser-deepin_${VERSION}_amd64.deb" ~/桌面/
echo "✅ 已保存到桌面: ~/桌面/omnibrowser-deepin_${VERSION}_amd64.deb"

echo -e "\n验证包信息..."
dpkg-deb -f "$PKG/omnibrowser-deepin_${VERSION}_amd64.deb" | head -10

# 清理临时目录
rm -rf "$TMP"
