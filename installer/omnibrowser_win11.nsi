; Yc浏览器 Windows 11 安装包脚本（NSIS）
; 用法（在 Windows 上）：
;   1) 先运行 installer/build_windows.py 生成 dist/OmniBrowser/
;   2) 本脚本需在 installer/ 目录下用 makensis 编译（下方路径均相对本目录）
;   3) makensis omnibrowser_win11.nsi
; 产出：installer/Yc浏览器-Windows11-<版本>-setup.exe
;
; 注意：本目录下的 omnibrowser.ico 由 build_windows.py 自动从 assets/ 复制而来。

!define APPNAME "Yc浏览器"
!define VERSION "1.1.8"
!define PUBLISHER "Yc"
!define INSTDIR "$PROGRAMFILES64\Yc浏览器"
!define ICO "omnibrowser.ico"

; Windows 11 风格设置
!include "WordFunc.nsh"
!include "WinVer.nsh"

Name "${APPNAME} ${VERSION}"
OutFile "Yc浏览器-Windows11-${VERSION}-setup.exe"
InstallDir "${INSTDIR}"
RequestExecutionLevel admin
ManifestEnableDPIAwareness
ManifestSupportedOS XP WIN7 WIN8 WIN10 WIN11

; 安装器与卸载器均显示 Yc 图标（固化）
Icon "${ICO}"
UninstallIcon "${ICO}"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

; Windows 11 现代化界面
!macro ModernPageEX CUSTOMPAGEEXTRA
  !insertmacro ModernInitLanguageDialog
  !insertmacro ModernDirectory
  !insertmacro ModernInstFiles
  ${CUSTOMPAGEEXTRA}
  !insertmacro ModernConfirmUninstall
  !insertmacro ModernInstFiles
!macroend

Section "安装"
  SetOutPath "$INSTDIR"
  ; 复制 PyInstaller 生成的便携程序（单文件夹）
  File /r "..\dist\OmniBrowser\*.*"

  ; 设置 Windows 11 兼容性
  SetRegView 64
  
  ; 开始菜单快捷方式
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\OmniBrowser.exe" "" "$INSTDIR\OmniBrowser.exe" 0
  ; 桌面快捷方式
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\OmniBrowser.exe" "" "$INSTDIR\OmniBrowser.exe" 0
  
  ; 注册卸载信息（Windows 11/10/8/7通用）
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME} ${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon" "$INSTDIR\OmniBrowser.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Categories" "网络;Web浏览器"
  
  ; Windows 11 特定：开始在任务栏固定支持
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\AppModel\" "StartupAppsV2Mode" "1"
  
  ; 应用现代化 UI 要求
  WriteRegStr HKCU "Software\Microsoft\Windows\DWM" "ColorizationColor" "00000000"
  
  ; 设置默认浏览器
  WriteRegStr HKCU "Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice" "ProgId" "YcBrowser.86651F718"
  WriteRegStr HKCU "Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice" "ProgId" "YcBrowser.86651F718"
  
  ; 注册文件关联
  WriteRegStr HKCU "Software\Classes\http\shell\open\command" "(pad)" "" "YcBrowser.exe \"%1\""
  WriteRegStr HKCU "Software\Classes\https\shell\open\command" "(pad)" "" "YcBrowser.exe \"%1\""
  WriteRegStr HKCU "Software\Classes\YcBrowser.86651F718" "(pad)" "" "Yc浏览器"
  WriteRegStr HKCU "Software\Classes\YcBrowser.86651F718\shell" "" "" "open"
  WriteRegStr HKCU "Software\Classes\YcBrowser.86651F718\shell\open\command" "" "YcBrowser.exe \"%1\""
  
  ; Windows 11 启用颜色主题
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" "AppsUseLightTheme" "0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" "SystemUsesLightTheme" "1"
  
  ; 设置 Fluent Design 支持
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" "EnableTransparency" "1"
  
  ; Windows 11 通知支持
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\PushNotifications" "ToastActivity" "1"
  
  ; Windows 11 触控键盘优化
  WriteRegStr HKCU "Software\Microsoft\TabletTip\1.7" "EnableTouchKeyboard" "1"
  
  ; 检索系统 DPI 设置
  System::Call(&quot;user32.dll&quot;::GetDpiForWindow(i) &quot;r0&quot;)
  StrCmp $0 0 0 +2
  StrCmp $0 96 0 +2
  StrCmp $0 120 0 +2
  StrCmp $0 144 "dpi144" 0 +2
  StrCmp $0 192 "dpi192" 0 +2
  
  ; 注册 Xbox 相关功能（如果系统有）
  WriteRegStr HKCU "Software\Microsoft\GameBar" "AutoGameModeEnabled" "0"
  
  ; 启用 DirectX 12 Ultimate 支持（如果系统有）
  SetRegView Default
  WriteRegStr HKCU "Software\Microsoft\DirectX\DirectSetup" "SkipDirectXUpdate" "0"

SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  RMDir "$SMPROGRAMS\${APPNAME}"
  Delete "$DESKTOP\${APPNAME}.lnk"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\AppModel\"
  DeleteRegKey HKCU "Software\Microsoft\Windows\DWM"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\PushNotifications"
  DeleteRegKey HKCU "Software\Microsoft\TabletTip\1.7"
  DeleteRegKey "Software\Microsoft\GameBar"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Search"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\wt"
  DeleteRegKey HKLM "SOFTWARE\Classes\y"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\DPI"
  DeleteRegKey HKLM "SOFTWARE\Classes\YcBrowser.86651F718"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Mica"
SectionEnd
