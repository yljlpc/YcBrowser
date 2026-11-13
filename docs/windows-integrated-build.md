# Yc浏览器 Windows 11 完全独立安装包构建指南

## 📋 概述

本文档介绍如何构建 Yc浏览器 的 Windows 11 完全独立安装包，包含所有必需的运行时、依赖库和资源文件。

## 🎯 打包目标

- **完全独立**: 安装包包含所有运行所需的文件
- **零依赖**: 安装后无需安装额外软件或依赖
- **Windows 11 优化**: 支持 Fluent Design、DPI 感知、透明度等特性
- **统一界面**: 所有用户可见元素全部中文化为 "Yc浏览器"

## 🔧 前置要求

### 1. 开发环境
- Windows 10/11 64 位
- Visual Studio 2019 或更高版本（编译 Rust 需要）
- Git for Windows

### 2. Python 环境
- Python 3.12+ (64 位)
- 依赖包: `pyinstaller`, `PyQt6`, `PyQt6-WebEngine`

### 3. 构建工具
- Rust (通过 `cargo` 编译核心)
- NSIS (Notepad++ Integration Script) 3.0+

### 4. 依赖库（手动收集）

#### 必需运行时库
- **PyQt6 核心库**: 已包含
- **PyQt6-WebEngine**: 已包含
- **PyQt6-sip**: 已包含
- **Python 运行库**: 需从 Python.org 下载

#### 系统依赖（部分需要复制）
- `vcruntime140.dll`
- `msvcp140.dll`
- `vcomp140.dll`
- `libpng16.dll`
- `libjpeg8.dll`
- `libgif7.dll`
- 运行库：`msi15.dll`, `msi15_msvc.dll`

### 构建依赖（可选）
- `nsis` (NSIS 构建工具)
- `7zip` (用于压缩)

## 🚀 构建步骤

### 1. 编译 Rust 核心 (Windows 目标)

```powershell
# 在 Windows 终端执行
cd core
cargo build --release --target x86_64-pc-windows-msvc
# 生成的可执行文件位于: target/release/omnibrowser-core.exe
```

### 2. 构建便携应用 (使用 PyInstaller)

```powershell
# 在 Windows 上执行
cd installer
python build_windows_win11.py --bump
```

### 3. 手动收集运行时依赖

```powershell
# 创建依赖文件夹
mkdir ycbrowser_runtime_libs

# 复制 Python 运行库
copy "C:\Program Files\Python312\python312.dll" ycbrowser_runtime_libs\
copy "C:\Program Files\Python312\lib\gc_1.pyd" ycbrowser_runtime_libs\
# 其他必要的 .pyd 和 .dll 文件

# 从指定路径复制 VCRUNTIME 等
copy "C:\Windows\System32\vcruntime140.dll" ycbrowser_runtime_libs\
copy "C:\Windows\System32\msvcp140.dll" ycbrowser_runtime_libs\
```

### 4. 生成最终安装包

```powershell
# 使用 NSIS 编译
makensis omnibrowser_win11.nsi
```

## 📦 安装包结构

```
Yc浏览器-Windows11-完全版_1.1.11-setup.exe
├── YcBrowser.exe              # 主程序 (PyInstaller 打包)
├── omnibrowser-core.exe       # Rust 核心
├── unic    # Unicode 字体支持
├── fonts/                      # 中文字体
├── ycbrowser_runtime_libs/     # 外部运行时库
│   ├── vcruntime140.dll
│   ├── msvcp140.dll
│   ├── python312.dll
│   └── ... (其他必要 DLL)
├── uninstall.exe               # 卸载程序
└── uninstall.log               # 卸载日志
```

## 🔍 运行环境要求

### 最低要求
- Windows 10 64 位
- 2GB RAM
- 3GB 磁盘空间

### 推荐要求
- Windows 11 64 位
- 4GB RAM
- 5GB 磁盘空间 (SSD 推荐)
- DirectX 10+ 支持

## 🆚 版本对比

| 版本 | 大小 | 依赖 | 安装后 |
|------|------|------|--------|
| **便携版** | 约 80MB | 无 (整个便携) | 直接运行 |
| **安装版** | 约 100MB | 无 | 系统整合 |
| **完全独立版** | 约 150MB | 所有运行时 | 完全独立 |

## 🛠️ 使用脚本

### `build_windows_integrated.sh` (用于 Linux 内容检查，构建在 Windows 上)

```bash
# 检查脚本
./build_windows_integrated.sh --help
```

### `build_windows_win11.py` (Windows 构建工具)

```powershell
# Windows 构建
python installer/build_windows_win11.py --bump
```

## 🎨 Windows 11 优化

- ✅ Fluent Design 支持
- ✅ DPI 感知 (自动缩放)
- ✅ 透明度/毛玻璃效果
- ✅ 任务栏固定
- ✅ 通知中心集成
- ✅ 触控键盘优化
- ✅ 文件关联 (HTTP/HTTPS)
- ✅ 通用新建选项

## 🏗️ 单文件包 (便携式)

```
Yc_browser_existing.zip            # 单文件便携包
├── YcBrowser.exe
├── omnibrowser-core.exe
├── libs/                           # 所有依赖库
│   ├── Qt*6.dll
│   ├── *dtl
│   └── ...
└── fonts/                          # 中文字体
```

## ⚙️ 配置文件

### 注册表位置
```
HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\Uninstall\Yc浏览器
HKEY_CURRENT_USER\Software\Yc浏览器
HKEY_CLASSES_ROOT\ybrowser
```

### 数据目录
```
C:\Users\<用户>\AppData\Local\Yc浏览器\
C:\Users\<用户>\AppData\Roaming\Yc浏览器\
```

## 🔧 部署脚本

### 使用 MSI 包装 (可选)

```xml
<!-- 代码形式或工具 -->
自定义 .msi 封装器 - 企业部署
```

### 官方方式 - 一键安装

```powershell
# 管理员权限运行
.\YcBrowser-Windows11-完全版_1.1.11-setup.exe /S
```

## 📡 常见问题

### Q1: 为什么需要手动复制运行时库？
PyInstaller 打包过程中不会自动包含系统 DLL，这些需要手动收集以确保在某些系统中也能正常运行。

### Q2: 是否可以自动收集 VCRUNTIME？
可以通过 `vcredist.exe` 部署工具，但我们的独立包不需要额外安装。

### Q3: NSIS 不支持 >4GB 怎么办？
Rust 核心 + PyInstaller 打包后的体积通常在 100MB 左右，不会超过限制。

## 📞 支持

- 开发日志: `docs/` 目录
- 构建错误: 检查 `logs/` 目录
- 集成问题: 联系开发者
