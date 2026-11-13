#!/bin/bash
# 构建两个 Linux 安装包：
#   package/omnibrowser_<版本>_amd64.deb      —— openKylin 3.0（自带 PyQt6 绑定，离线可用）
#   package/omnibrowser-deepin_<版本>_amd64.deb —— deepin v25（依赖系统 python3-pyqt6，ABI 自适应）
#
# 支持 --auto-bump 参数，在构建前自动递增版本号（默认修订号 +1）
# 版本号从 src/version.py 自动读取，避免与「关于页 / 帮助页」不一致。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/package"
ASSETS="$ROOT/assets"
FONT_SRC="$HOME/桌面/fonts"

# 解析参数
AUTO_BUMP="0"
for arg in "$@"; do
  case $arg in
    --auto-bump) AUTO_BUMP="1" ;;
  esac
done

# 如果需要自动递增版本号
if [ "$AUTO_BUMP" = "1" ]; then
  echo "==> 自动递增版本号..."
  python3 "$ROOT/tools/bump_version.py" || exit 1
fi

# 从 src/version.py 提取 VERSION（唯一版本来源）
VERSION="$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$ROOT/src/version.py" | head -1)"
if [ -z "$VERSION" ]; then
  echo "错误：无法从 src/version.py 读取版本号" >&2
  exit 1
fi
echo "构建版本：$VERSION"

# dpkg-deb 会在 TMPDIR 下写中间 data.tar；若 /tmp 为小容量 tmpfs（10MB）会 ENOSPC，
# 故统一把临时目录指向大分区。
export TMPDIR="${TMPDIR:-$PKG/.tmp}"
mkdir -p "$TMPDIR"

build_one() {
  local name="$1"; local bundled="$2"; local depends="$3"
  # 每次构建使用全新暂存目录，避免删除旧目录（大批量删除易被安全钩子拦截）
  local DEST
  DEST="$(mktemp -d "$PKG/.stage.XXXXXX")"
  echo "==> 构建 $name (bundled=$bundled)"
  echo "    暂存目录: $DEST"
  mkdir -p "$DEST/opt/omnibrowser/src" \
           "$DEST/opt/omnibrowser/fonts" \
           "$DEST/usr/bin" \
           "$DEST/usr/share/applications" \
           "$DEST/usr/share/deb-systemd-helper" \
           "$DEST/DEBIAN"

  # 核心 + 前端源码 + 字体
  cp "$ROOT/core/target/release/omnibrowser-core" "$DEST/opt/omnibrowser/omnibrowser-core"
  chmod 755 "$DEST/opt/omnibrowser/omnibrowser-core"
  cp "$ROOT"/src/*.py "$DEST/opt/omnibrowser/src/"
  if [ -d "$FONT_SRC" ]; then
    cp "$FONT_SRC"/* "$DEST/opt/omnibrowser/fonts/" 2>/dev/null || true
  fi
  # 若桌面字体目录为空（如 CI/其他环境），退而使用仓库内已随附的 fonts（若有）
  if [ -z "$(ls -A "$DEST/opt/omnibrowser/fonts/" 2>/dev/null)" ]; then
    echo "  警告：未找到 $FONT_SRC，fonts 目录为空（请放入随附中文字体）"
  fi

  # PyQt6 绑定：openKylin 自带，deepin 交给系统
  if [ "$bundled" = "1" ]; then
    mkdir -p "$DEST/opt/omnibrowser/lib/python3/dist-packages"
    cp -r "$ROOT/_stage/pyqt6root/usr/lib/python3/dist-packages/PyQt6" \
          "$DEST/opt/omnibrowser/lib/python3/dist-packages/"
    for di in pyqt6-6.10.2.dist-info pyqt6_sip-13.11.0.dist-info pyqt6_webengine-6.10.0.dist-info; do
      if [ -d "$ROOT/_stage/pyqt6root/usr/lib/python3/dist-packages/$di" ]; then
        cp -r "$ROOT/_stage/pyqt6root/usr/lib/python3/dist-packages/$di" \
              "$DEST/opt/omnibrowser/lib/python3/dist-packages/"
      fi
    done
  fi

  # 启动器（openKylin / deepin 通用）
  cp "$ROOT/installer/omnibrowser-launch.sh" "$DEST/usr/bin/omnibrowser"
  chmod 755 "$DEST/usr/bin/omnibrowser"

  # post-install 脚本 - 刷新图标缓存
  cp "$ROOT/installer/omnibrowser-postinst" "$DEST/DEBIAN/postinst"
  chmod 755 "$DEST/DEBIAN/postinst"

  # .desktop
  # 注意：StartupNotify 会让"启动失败但没弹窗"的情况完全静默（用户只看到图标点了没反应），
  # 故这里关闭它 —— 启动异常时终端/启动器能把原因打出来。
  # Name 是用户看到的显示名（应用列表 / 任务栏 / 桌面图标文字）；
  # Exec 与包名是技术标识符，保持英文不变（改了会无法启动）。
  cat > "$DEST/usr/share/applications/omnibrowser.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Yc浏览器
Name[en]=Yc Browser
GenericName=浏览器
GenericName[zh_CN]=多引擎浏览器
Comment=Yc浏览器 —— 多引擎浏览器（Blink / WebKit / Trident 兼容），支持实时翻译与高速下载
Comment[zh_CN]=Yc浏览器 —— 多引擎浏览器（Blink / WebKit / Trident 兼容），支持实时翻译与高速下载
Exec=omnibrowser %U
TryExec=omnibrowser
Icon=omnibrowser
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;x-scheme-handler/omni;
StartupNotify=false
EOF

  # 图标：完整 hicolor 尺寸集（任务栏 / 菜单 / 文件管理器 / 安装器均显示 Yc 图标）
  for d in "$ASSETS"/hicolor/*x*/apps; do
    sz="$(basename "$(dirname "$d")")"
    mkdir -p "$DEST/usr/share/icons/hicolor/$sz/apps"
    cp "$d/omnibrowser.png" "$DEST/usr/share/icons/hicolor/$sz/apps/omnibrowser.png"
  done

  # control
  cat > "$DEST/DEBIAN/control" <<EOF
Package: omnibrowser
Version: $VERSION
Section: web
Priority: optional
Architecture: amd64
Depends: $depends
Maintainer: Yc <yc@omnibrowser.local>
Description: Yc浏览器 —— 多引擎浏览器（Blink / WebKit / Trident 兼容）
 一款以 Rust 原生核心 + PyQt6（Qt 6）构建的多功能桌面浏览器，支持实时翻译与高速下载。
 渲染核心为 Blink（QtWebEngine），并提供 WebKit 兼容 UA 与 Trident 兼容模式。
 内置多标签、独立地址栏、历史/书签、页面查找、下载管理、开发者工具、
 页面缩放与清除浏览数据等完整功能，并随系统分辨率与 DPI 自适应。
 关于页提供软件详细说明与版本号。
EOF

  fakeroot dpkg-deb --build "$DEST" "$PKG/$name.deb"
  echo "    产物: $PKG/$name.deb ($(du -h "$PKG/$name.deb" | cut -f1))"
}

# openKylin 3.0：自带 PyQt6 绑定（离线），Qt6 运行时依赖用 "|" 兼容 t64 / 非 t64 命名
OPENKYLIN_DEP='python3 (>= 3.12), libqt6core6t64 | libqt6core6, libqt6gui6, libqt6widgets6, libqt6network6, libqt6opengl6, libqt6printsupport6, libqt6dbus6, libqt6svg6, libqt6positioning6, libqt6qml6, libqt6quick6, libqt6quickwidgets6, libqt6webchannel6, libqt6webenginecore6 | libqt6webenginecore6t64, libqt6webenginewidgets6 | libqt6webenginewidgets6t64, libqt6webengine6-data'
build_one "omnibrowser_${VERSION}_amd64" 1 "$OPENKYLIN_DEP"

# deepin v25：依赖系统 python3-pyqt6（由发行版提供 ABI 匹配的 PyQt6 + Qt6 运行时）
# WebEngine 绑定包名 Debian 系为 python3-pyqt6.qtwebengine，deepin/UOS 部分仓库沿用
# python3-pyqt6.webengine —— 用 "|" 兼容两种命名，任一存在即可满足依赖。
DEEPIN_DEP='python3 (>= 3.10), python3-pyqt6 (>= 6.4), python3-pyqt6.qtwebengine (>= 6.4) | python3-pyqt6.webengine, libqt6webengine6-data'
build_one "omnibrowser-deepin_${VERSION}_amd64" 0 "$DEEPIN_DEP"

echo "全部完成。"
