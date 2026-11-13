; OmniBrowser Windows 安装包脚本（NSIS）
; 用法（在 Windows 上）：
;   1) 先运行 installer/build_windows.py 生成 dist/OmniBrowser/
;   2) 本脚本需在 installer/ 目录下用 makensis 编译（下方路径均相对本目录）
;   3) makensis omnibrowser.nsi
; 产出：installer/YcBrowser-<版本>-setup.exe
;
; 注意：本目录下的 omnibrowser.ico 由 build_windows.py 自动从 assets/ 复制而来。

!define APPNAME "Yc浏览器"
!define VERSION "1.1.13"
!define PUBLISHER "Yc"
!define INSTDIR "$PROGRAMFILES64\OmniBrowser"
!define ICO "omnibrowser.ico"

Name "${APPNAME} ${VERSION}"
OutFile "YcBrowser-${VERSION}-setup.exe"
InstallDir "${INSTDIR}"
RequestExecutionLevel admin

; 安装器与卸载器均显示 Yc 图标（固化）
Icon "${ICO}"
UninstallIcon "${ICO}"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "安装"
  SetOutPath "$INSTDIR"
  ; 复制 PyInstaller 生成的便携程序（单文件夹）
  File /r "..\dist\OmniBrowser\*.*"

  ; 开始菜单快捷方式
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\OmniBrowser.exe" "" "$INSTDIR\OmniBrowser.exe" 0
  ; 桌面快捷方式
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\OmniBrowser.exe" "" "$INSTDIR\OmniBrowser.exe" 0

  ; 注册卸载信息
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME} ${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon" "$INSTDIR\OmniBrowser.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSION}"
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  RMDir "$SMPROGRAMS\${APPNAME}"
  Delete "$DESKTOP\${APPNAME}.lnk"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
SectionEnd
