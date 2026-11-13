@echo off
REM OmniBrowser 便携启动器（开发 / 免安装模式）
REM 前置：已编译 core/target/release/omnibrowser-core.exe，且已 pip install PyQt6 PyQt6-WebEngine
setlocal
set OMNIBROWSER_CORE=%~dp0core\target\release\omnibrowser-core.exe
cd /d %~dp0
python -m src.main
endlocal
