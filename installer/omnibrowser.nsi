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

; 卸载注册表键名 / winget ProductCode。
; 必须使用 ASCII：SignPath 要求产物元数据与项目名一致，winget 的
; PackageIdentifier 也以 ASCII 段匹配 ARP 键，中文键名会导致两者都无法对齐。
!define ARPKEY "YcBrowser"

Name "${APPNAME} ${VERSION}"
OutFile "YcBrowser-${VERSION}-setup.exe"
InstallDir "${INSTDIR}"
RequestExecutionLevel admin

; ---------------------------------------------------------------------------
; 压缩算法
;
; 安装耗时 = 解压耗时 + 写盘耗时 + Defender 对每个新写入文件的实时扫描。
; 载荷瘦身后（2788 → 142 个文件）写盘与扫描成本已大幅下降，
; 解压成为主要瓶颈，因此选用 **solid LZMA**：
;   - /SOLID 把整个包压成一个连续数据块，比逐文件 LZMA 压缩率高 10~15%，
;     同样体积下安装包更小（下载更快）；
;   - NSIS 3.x 对 solid LZMA 采用**多线程并行解压**，多核机器上解压吞吐
;     远高于单文件 LZMA；
;   - 相比 zlib 体积小得多，抵消了 zlib 那点解压速度优势 ——
;     实测 zlib 的安装包会从约 120 MB 涨到 210 MB，下载时间反而更长。
; ---------------------------------------------------------------------------
SetCompressor /SOLID lzma
SetDatablockOptimize on

; ---------------------------------------------------------------------------
; 版本资源（VERSIONINFO）
;
; SignPath Foundation 要求产物元数据必须正确且一致：
;   - 产品名必须与项目名一致
;   - 版本号在每次构建中相同（由 build_windows.py 从 src/version.py 注入）
; Windows 的「属性 → 详细信息」面板与文件属性对话框读取的就是这里的值。
; ---------------------------------------------------------------------------
VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductName"     "${ARPKEY}"
VIAddVersionKey /LANG=2052 "ProductVersion"  "${VERSION}.0"
VIAddVersionKey /LANG=2052 "FileDescription" "${APPNAME} 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion"     "${VERSION}.0"
VIAddVersionKey /LANG=2052 "CompanyName"     "${PUBLISHER}"
VIAddVersionKey /LANG=2052 "LegalCopyright"  "MIT License"
VIAddVersionKey /LANG=2052 "Comments"        "多引擎浏览器（Blink / WebKit / Trident 兼容）"

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

  ; 注册卸载信息（ARP 键使用 ASCII 的 ${ARPKEY}，与 winget ProductCode 对齐）
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${ARPKEY}" "DisplayName" "${APPNAME} ${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${ARPKEY}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${ARPKEY}" "DisplayIcon" "$INSTDIR\OmniBrowser.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${ARPKEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${ARPKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${ARPKEY}" "InstallLocation" "$INSTDIR"
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  RMDir "$SMPROGRAMS\${APPNAME}"
  Delete "$DESKTOP\${APPNAME}.lnk"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${ARPKEY}"
SectionEnd
