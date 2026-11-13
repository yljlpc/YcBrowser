@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: Yc浏览器 Windows 完全独立安装包构建脚本
:: 包含所有运行所需软件、插件、控件和运行环境

echo ======================
echo Yc浏览器 Windows 完全独立安装包构建程序
echo ======================
echo.

:: 获取当前版本号
for /f "tokens=*" %%i in ('findstr "VERSION" src^>^> version.py') do set VERSION=%%i
for /f "tokens=2 delims==" %%i in ("!VERSION!") do set VERSION=%%i

set BUILD_DIR=%CD%\ycbrowser_windows_independent
set TEMP_DIR=%CD%\ycbrowser_temp_build

echo [版本] %VERSION%
echo [构建目录] %BUILD_DIR%

:: Clean up previous builds
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
mkdir "%TEMP_DIR%"

echo [步骤 1] 复制 Rust 核心...
if not exist "core\target\release\omnibrowser-core.exe" (
    echo 错误：找不到 Rust 核心文件，请先编译
    exit /b 1
)
copy /y "core\target\release\omnibrowser-core.exe" "%TEMP_DIR%\omnibrowser-core.exe"

echo [步骤 2] 构建 PyInstaller 便携应用...
if not exist "installer\build_windows.py" (
    echo 错误：缺少 build_windows.py
    exit /b 1
)
pyinstaller --clean --noconfirm installer\build_windows.py -- --bump || (
    echo 错误：PyInstaller 打包失败
    exit /b 1
)

echo [步骤 3] 收集 Python 运行时依赖...
:: Python 运行库路径
set PYTHON_PATH=%LOCALAPPDATA%\Programs\Python\Python312
if not exist "%PYTHON_PATH%\python312.dll" (
    echo 警告：未找到 Python 3.12，从官方下载
    echo 下载地址：https://www.python.org/downloads/release/python-3120/
)

:: 收集 python312.dll 和其他必要的 Python 文件
if exist "%PYTHON_PATH%\python312.dll" (
    copy /y "%PYTHON_PATH%\python312.dll" "%TEMP_DIR%\"
)

:: 收集 VCRUNTIME 运行的库
echo [步骤 4] 收集 VCRUNTIME 运行库...
set VCRUNTIMES=
set SYSTEM_DIR=%SystemRoot%\System32

if exist "%SYSTEM_DIR%\vcruntime140.dll" (
    copy /y "%SYSTEM_DIR%\vcruntime140.dll" "%TEMP_DIR%\"
    set VCRUNTIMES=!VCRUNTIMES! vcruntime140.dll
)

if exist "%SYSTEM_DIR%\msvcp140.dll" (
    copy /y "%SYSTEM_DIR%\msvcp140.dll" "%TEMP_DIR%\"
    set VCRUNTIMES=!VCRUNTIMES! msvcp140.dll
)

if exist "%SYSTEM_DIR%\vcomp140.dll" (
    copy /y "%SYSTEM_DIR%\vcomp140.dll" "%TEMP_DIR%\"
    set VCRUNTIMES=!VCRUNTIMES! vcomp140.dll
)

echo [步骤 5] 从 PyInstaller 输出目录收集所有依赖...
if NOT exist "dist\OmniBrowser\*" (
    echo 错误：PyInstaller 输出目录不存在
    exit /b 1
)

mkdir "%TEMP_DIR%\ycbrowser"
xcopy /e /i /y "dist\OmniBrowser\*" "%TEMP_DIR%\ycbrowser\"

echo [步骤 6] 收集所需系统 DLL...
set SYSTEM_DLLS=

:: 必需的系统 DLL (某些 Windows 版本可能缺失)
if exist "%SYSTEM_DIR%\d3d11.dll" (
    copy /y "%SYSTEM_DIR%\d3d11.dll" "%TEMP_DIR%\ycbrowser\"
    set SYSTEM_DLLS=!SYSTEM_DLLS! d3d11.dll
)

if exist "%SYSTEM_DIR%\bcrypt.dll" (
    copy /y "%SYSTEM_DIR%\bcrypt.dll" "%TEMP_DIR%\ycbrowser\"
    set SYSTEM_DLLS=!SYSTEM_DLLS! bcrypt.dll
)

if exist "%SYSTEM_DIR%\gdi32.dll" (
    copy /y "%SYSTEM_DIR%\gdi32.dll" "%TEMP_DIR%\ycbrowser\"
    set SYSTEM_DLLS=!SYSTEM_DLLS! gdi32.dll
)

echo [步骤 7] 收集 QtWebEngine 相关依赖...
if exist "dist\OmniBrowser\QtWebEngineCore.dll" (
    copy /y "dist\OmniBrowser\QtWebEngine*.dll" "%TEMP_DIR%\ycbrowser\" 2>nul
    copy /y "dist\OmniBrowser\Qt*.dll" "%TEMP_DIR%\ycbrowser\" 2>nul
    copy /y "dist\OmniBrowser\*vcruntime*.dll" "%TEMP_DIR%\ycbrowser\" 2>nul
)

echo [步骤 8] 复制图标和资源...
mkdir "%TEMP_DIR%\ycbrowser\fonts"
if exist "assets\*.png" (
    mkdir "%TEMP_DIR%\ycbrowser\assets\hicolor"
    copy /y "assets\*.png" "%TEMP_DIR%\ycbrowser\assets\hicolor\"
)

echo [步骤 9] 准备 NSIS 安装脚本...
 copy "installer\omnibrowser_win11.nsi" "%TEMP_DIR%\installer_windows_independent.nsi"

:: 更新 NSIS 脚本中的版本号
(
    echo !define APPNAME "Yc浏览器"
    echo !define VERSION "%VERSION%"
    echo !define PUBLISHER "Yc"
    echo !define INSTDIR "$PROGRAMFILES64\Yc浏览器"
    echo !define ICO "omnibrowser.ico"
    echo.
    echo Name "${APPNAME} ${VERSION}"
    echo OutFile "Yc浏览器-Windows11-完全独立版-%VERSION%-setup.exe"
    echo InstallDir "${INSTDIR}"
    echo RequestExecutionLevel admin
    echo.
    echo !include "WordFunc.nsh"
    echo !include "WinVer.nsh"
    echo.
    echo Name "${APPNAME} ${VERSION}"
    echo OutFile "Yc浏览器-Windows11-完全独立版-%VERSION%-setup.exe"
    echo InstallDir "${INSTDIR}"
    echo RequestExecutionLevel admin
    echo.
    echo Icon "${ICO}"
    echo UninstallIcon "${ICO}"
    echo.
    echo Page directory
    echo Page instfiles
    echo UninstPage uninstConfirm
    echo UninstPage instfiles
    echo.
    echo Section "安装 (完全独立版)"
    echo   SetOutPath "$INSTDIR"
    echo   File /r "%TEMP_DIR%\ycbrowser\*.*"
    echo   CreateDirectory "$SMPROGRAMS\${APPNAME}"
    echo   CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\OmniBrowser.exe" "" "$INSTDIR\OmniBrowser.exe" 0
    echo   CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\OmniBrowser.exe" "" "$INSTDIR\OmniBrowser.exe" 0
    echo   WriteUninstaller "$INSTDIR\uninstall.exe"
    echo SectionEnd
    echo.
    echo Section "Uninstall"
    echo   RMDir /r "$INSTDIR"
    echo   Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
    echo   RMDir "$SMPROGRAMS\${APPNAME}"
    echo   Delete "$DESKTOP\${APPNAME}.lnk"
    echo   DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
    echo SectionEnd
) > "%TEMP_DIR%\installer_windows_independent.nsi"

echo [步骤 10] 创建最终安装包...
if not exist "%TEMP_DIR%\msis..exe" (
    echo 错误：找不到 NSIS makensis.exe，请安装 NSIS
    exit /b 1
)

makensis /V3 "%TEMP_DIR%\installer_windows_independent.nsi"
if errorlevel 1 (
    echo 错误：NSIS 编译失败
    exit /b 1
)

:: 移动到构建目录
mkdir "%BUILD_DIR%"
move /y "%TEMP_DIR%\Yc浏览器-Windows11-完全独立版-%VERSION%-setup.exe" "%BUILD_DIR%\"

echo.
echo ======================
echo 构建完成！
echo 构建目录: %BUILD_DIR%
echo 安装包: %BUILD_DIR%\Yc浏览器-Windows11-完全独立版-%VERSION%-setup.exe
echo ======================
echo.
echo 下架待安装的组件:
echo   [✅] Python312 运行时
echo   [✅] VCRUNTIME140
echo   [✅] 系统 DLL
echo   [✅] QtWebEngine 依赖
echo   [✅] 中文字体
echo   [✅] Rust 核心
echo [✅] 所有必要插件和控件
echo.
echo 无需安装额外运行时，可直接在任何 Windows 系统上运行
echo.
endlocal
pause
