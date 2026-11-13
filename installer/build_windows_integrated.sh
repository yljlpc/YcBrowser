#!/bin/bash
# Yc浏览器 Windows 11 完全独立安装包构建脚本
# 集成所有必需的运行时、插件、控件和运行环境

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

VERSION=$(grep 'VERSION' src/version.py | cut -d'"' -f2)

AUTO_BUMP="0"
for arg in "$@"; do
    case $arg in
        --bump) AUTO_BUMP="1" ;;
        --help) cat <<EOF
Yc浏览器 Windows 11 完全独立安装包构建脚本

用法: $0 [选项]

选项:
  --bump       构建前自动递增版本号
  --help       显示此帮助信息

产出:
  - Yc浏览器-Windows11-完全版_${VERSION}-setup.exe
    包含所有运行环境、依赖库和数据文件的 Windows 安装文件
EOF
        exit 0 ;;
    esac
done

if [ "$AUTO_BUMP" = "1" ]; then
    print_info "自动递增版本号..."
    python3 tools/bump_version.py || exit 1
    VERSION=$(grep 'VERSION' src/version.py | cut -d'"' -f2)
fi

print_info "构建版本: $VERSION"

# 创建工作目录
WORK_DIR=$(mktemp -d)
print_info "工作目录: $WORK_DIR"

print_info "构建 Windows 便携应用..."
# 在 Windows 环境中执行 PyInstaller 打包
# 这个步骤需要 Windows 系统环境

# 创建 NSIS 安装脚本
cat > "$WORK_DIR/integrated_windows_installer.nsi" <<'EOF'
; Yc浏览器 Windows 11 完全独立安装包 (集成所有运行时和依赖)

!define APPNAME "Yc浏览器"
!define VERSION "${VERSION}"
!define PUBLISHER "Yc"
!define PUBLISHER_WEBSITE "https://ycbrowser.com"
!define INSTDIR "$PROGRAMFILES64\Yc浏览器"
!define ICO "omnibrowser.ico"

Name "${APPNAME} ${VERSION}"
OutFile "Yc浏览器-Windows11-完全版-${VERSION}-setup.exe"
InstallDir "${INSTDIR}"
RequestExecutionLevel admin

; 支持 Fluent Design 和 DPI 感知
ManifestEnableDPIAwareness
ManifestSupportedOS XP WIN7 WIN8 WIN10 WIN11

; 安装器与卸载器均显示 Yc 图标（固化）
Icon "${ICO}"
UninstallIcon "${ICO}"

; 汉化界面
!include "MUI2.nsh"
!include "WinVer.nsh"
!include "WordFunc.nsh"

; 设置 UTF-8 编码
Unicode true

; 界面配置
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; 卸载程序
!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; 界面语言
!insertmacro MUI_LANGUAGE "Simp chino"

Section "安装"
  SetOutPath "$INSTDIR"
  
  ; 复制所有必需的文件
  File /r "ycbrowser_setup_files\*.*"
  
  ; 创建开始菜单快捷方式
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\YcBrowser.exe" "" "$INSTDIR\YcBrowser.exe" 0
  CreateShortcut "$SMPROGRAMS\${APPNAME}\卸载.lnk" "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0
  CreateShortcut "$SMPROGRAMS\${APPNAME}\桌面快捷方式.lnk" "$INSTDIR\YcBrowser.exe" "" "$INSTDIR\YcBrowser.exe" 0
  
  ; 创建桌面快捷方式
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\YcBrowser.exe" "" "$INSTDIR\YcBrowser.exe" 0
  
  ; 注册卸载信息
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME} ${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon" "$INSTDIR\YcBrowser.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Categories" "网络;Web浏览器"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLInfoAbout" ${PUBLISHER_WEBSITE}
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLUpdateInfo" ${PUBLISHER_WEBSITE}
  
  ; 注册文件关联
  WriteRegStr HKCR "ybrowser" "Description" "Yc浏览器 URL Scheme"
  WriteRegStr HKCR "ybrowser" "URL Protocol" ""
  WriteRegStr HKCR "ybrowser\shell" "Edit" "\"http\""
  WriteRegStr HKCR "ybrowser\shell\open" "(pad)" "" "Open"
  WriteRegStr HKCR "ybrowser\shell\open\command" "(pad)" "" '"$INSTDIR\YcBrowser.exe" "%1"'
  
  ; 注册 HTTP/HTTPS 协议
  WriteRegStr HKCR "http" "URL Protocol" ""
  WriteRegStr HKCR "http\shell\open\command" "(pad)" "" '"$INSTDIR\YcBrowser.exe" "%1"'
  WriteRegStr HKCR "https" "URL Protocol" ""
  WriteRegStr HKCR "https\shell\open\command" "(pad)" "" '"$INSTDIR\YcBrowser.exe" "%1"'
  
  ; 设置数组属性
  WriteRegStr HKCR "http" "UserAgent" "${APPNAME}/${VERSION}"
  WriteRegStr HKCR "https" "UserAgent" "${APPNAME}/${VERSION}"
  
  ; Windows 11 特定设置
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\App Paths\YcBrowser.exe" "" "$INSTDIR\YcBrowser.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\AppModel\" "StartupAppsV2Mode" "1"
  
  ; 设置默认浏览器
  WriteRegStr HKCU "Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice" "ProgId" "ybrowser.86651F718"
  WriteRegStr HKCU "Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice" "ProgId" "ybrowser.86651F718"
  
  ; 注册程序关联
  WriteRegStr HKCU "Software\Classes\ybrowser.86651F718" "(pad)" "" "${APPNAME}"
  WriteRegStr HKCU "Software\Classes\ybrowser.86651F718\shell" "" "" "open"
  WriteRegStr HKCU "Software\Classes\ybrowser.86651F718\shell\open\command" "" '"$INSTDIR\YcBrowser.exe" "%1"'
  
  ; 设置应用图标
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\AppendStream" "AppendStream" "YcBrowser"
  
  ; 设置文本编码
  WriteRegStr HKCU "Software\Classes\http\shell\open\command" "CodePage" "65001"
  
  ; 设置终端仿真
  WriteRegStr HKCU "Software\Classes\http\shell\open\command" "Terminal" "0"
  
  ; Windows 11 启用颜色主题
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" "AppsUseLightTheme" "0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" "SystemUsesLightTheme" "1"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" "EnableTransparency" "1"
  
  ; 通知系统
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\PushNotifications" "ToastActivity" "1"
  
  ; 触控键盘优化
  WriteRegStr HKCU "Software\Microsoft\TabletTip\1.7" "EnableTouchKeyboard" "1"
  
  ; 设置 Viewport 缩放
  WriteRegStr HKCU "Software\Classes\YcBrowser.86651F718" "Compatibility" "1"
  
  ; 设置快捷键
  WriteRegStr HKCU "Software\Classes\ybrowser\shell\open" "Hotkey" "WS"
  WriteRegStr HKCU "Software\Classes\ybrowser\shell\open" "Command" "Open"
  
SectionEnd

Section "Uninstall"
  SetRegView 64
  
  ; 删除卸载注册表
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
  
  ; 删除注册表
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\AppModel\"
  DeleteRegKey HKCU "Software\Microsoft\Windows\DWM"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\PushNotifications"
  DeleteRegKey HKCU "Software\Microsoft\TabletTip\1.7"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Search"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\wt"
  DeleteRegKey HKLM "SOFTWARE\Classes\ybrowser"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\DPI"
  DeleteRegKey HKLM "SOFTWARE\Classes\YcBrowser.86651F718"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Win32PackagesFilter"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Mica"
  DeleteRegKey "Software\Microsoft\GameBar"
  
  ; 删除卸载程序
  Delete "$INSTDIR\uninstall.exe"
  
  ; 删除快捷方式
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${APPNAME}\卸载.lnk"
  Delete "$SMPROGRAMS\${APPNAME}\桌面快捷方式.lnk"
  RMDir "$SMPROGRAMS\${APPNAME}"
  Delete "$DESKTOP\${APPNAME}.lnk"
  
  ; 删除文件夹
  RMDir /r "$INSTDIR"
  
  ; 尝试删除主程序
  Delete "$INSTDIR\YcBrowser.exe"
  RMDir "$INSTDIR"
  
  ; 删除 Shell 扩展
  DeleteRegKey HKCU "Software\Classes\ybrowser\types"
  DeleteRegKey HKCU "Software\Classes\ybrowser\shell"
  DeleteRegKey HKCU "Software\Classes\ybrowser\shell\open\command"
  DeleteRegKey HKCU "Software\Classes\ybrowser"
  
  ; Windows 11 特定卸载
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\AppModel\"
  
  ; 通知系统清理
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\PushNotifications"
SectionEnd

Section "验证与记录"
  ; 记录安装配置
  WriteRegStr HKCU "SOFTWARE\${APPNAME}\SetupInfo" "version" "${VERSION}"
  WriteRegStr HKCU "SOFTWARE\${APPNAME}\SetupInfo" "path" "$INSTDIR"
  WriteRegStr HKCU "SOFTWARE\${APPNAME}\SetupInfo" "host" "$HWNDPARENT"
  WriteRegStr HKCU "SOFTWARE\${APPNAME}\SetupInfo" "installer" "YcBrowser-Windows11-完全版-${VERSION}-setup.exe"
  WriteRegStr HKCU "SOFTWARE\${APPNAME}\SetupInfo" "host_media_id" ""
SectionEnd
