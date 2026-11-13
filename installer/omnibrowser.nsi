; OmniBrowser Windows 安装包脚本（NSIS）
; 用法（在 Windows 上）：
;   1) 先运行 installer/build_windows.py 生成 dist/OmniBrowser/
;   2) 本脚本需在 installer/ 目录下用 makensis 编译（下方路径均相对本目录）
;   3) makensis omnibrowser.nsi
; 产出：installer/YcBrowser-<版本>-setup.exe
;
; 注意：本目录下的 omnibrowser.ico 由 build_windows.py 自动从 assets/ 复制而来。

!define APPNAME "Yc浏览器"
!define VERSION "1.1.14"
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
; 载荷瘦身后（2788 → 134 个文件）写盘与扫描成本已大幅下降，
; **解压成为绝对瓶颈**，因此压缩算法必须以解压速度优先。
;
; 曾经这里用 /SOLID lzma，注释称"NSIS 3.x 对 solid LZMA 多线程并行解压"。
; 该假设经实测**证伪**（见 tools/cmp_compressor.py，四轮交叉对照，
; 同一份产物只改压缩算法）：
;
;   算法          体积        安装耗时(4 轮平均)
;   zlib          165.1 MB    4.38 s
;   lzma          125.9 MB   15.74 s
;   solid lzma   123.9 MB   17.40 s
;
; LZMA 解压比 zlib 慢 3~4 倍，且优势随载荷缩小而更加明显
; （文件少 → 解压占比高 → 差距放大）。bzip2 更慢（20.6 s），
; zlib + SetDatablockOptimize 与 zlib 无差异（体积完全相同）。
;
; 体积换时间的账：zlib 比 solid lzma 大 41 MB，但在 80 Mbps 有效带宽下
; 只多花约 4 s 下载；换来的安装加速是 12.7 s —— **净收益约 9 s**，
; 且用户等待的是"装完"的瞬间，而不是"下载完"的瞬间。
; 带宽越慢、越接近本地磁盘安装，zlib 的优势越大。
;
; 结论：坚持 zlib。体积不是安装体验的关键指标。
; ---------------------------------------------------------------------------
SetCompressor zlib
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
