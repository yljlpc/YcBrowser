# Yc浏览器（YcBrowser）

一款以 **Rust 原生核心 + PyQt6（Qt 6）** 构建的多功能桌面浏览器，
支持实时翻译与高速下载。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightblue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Rust](https://img.shields.io/badge/rust-1.70%2B-orange.svg)

---

## 功能特性

### 🌐 多引擎兼容

| 引擎 | 说明 |
|---|---|
| **Blink** | 基于 QtWebEngine 6.10（Chromium content + V8），默认引擎 |
| **WebKit** | 以 WebKit UA 伪装运行 |
| **Trident** | IE 兼容模式：按 `X-UA-Compatible` 协商文档模式（支持 `IE=EmulateIE7` 等真实页面写法），伪装 IE UA 并注入遗留 DOM 垫片（`document.all` / `attachEvent`） |

每个标签页使用独立的 `QWebEngineProfile`，因此可**按标签页隔离引擎与 UA**。

### 🌏 实时翻译（英译中）

- 提取页面可见正文（跳过脚本 / 代码 / 输入框）→ 逐句送译 → **术语统一 + 口语化改写** → 回填 DOM
- 一键「还原页面原文」
- 可切换后端：**MyMemory**（默认免费）/ **Google** / **LibreTranslate** / 自定义端点
  （自定义端点支持 `{text}` `{source}` `{target}` 占位符，或按 JSON POST 约定）
- 目标语言与自定义术语表可在「设置」中配置

> 语言学处理（语言检测、分句、术语统一、中文润色）在 Rust 核心内完成，**确定性且可单测**。

### ⬇️ 高速下载引擎

移植自 [SwiftDL](https://github.com/harshsinghsv/swiftdl)（MIT）的算法内核：

- **多连接分片**：单文件最多 32 个连接并行（设置中可调，默认 8）
- **动态再平衡**：某连接完成后立即接手剩余量最大的一段，避免末尾空转
- **无合并步骤**：文件预先按总长分配，各连接直接写入自己的偏移
- **自动降级**：服务器不支持 `Range` 时改用单线程
- **断点续传**：`.omnidl` 记录缺失字节区间，崩溃/断网最多损失最后一秒进度
- **分类归档**：按扩展名归入「视频 / 音乐 / 程序 / 压缩包 / 文档」子目录
- **媒体嗅探**：菜单「下载页面媒体…」列出页面中的视频与音频直链

### 🖥 界面与体验

- 多标签、独立地址栏、历史、书签、页面查找、下载管理、开发者工具
- **分辨率自适应**：按 `主屏分辨率/1920x1080` 与 `devicePixelRatio` 计算缩放系数
  （夹在 0.8–2.2），实时同步工具栏图标、字号、标签页网页缩放；可在设置中关闭或手动指定
- 无痕窗口、打印与导出 PDF、标签页右键菜单
- 随包分发中文字体，界面中文显示

---

## 架构

```
┌──────────────────────────────────────────────────────┐
│ PyQt6 / Qt 6 前端（src/）                             │
│  main.py      启动入口（注册字体/主题/核心子进程）      │
│  window.py    主窗口：工具栏·地址栏·引擎切换·多标签     │
│  tab.py       标签页：QWebEngineView + 独立 profile    │
│  translate.py 翻译客户端（MyMemory/Google/Libre）      │
│  downloader.py 多连接分片下载引擎                      │
│  core_client.py Rust 核心 IPC 客户端（行式 JSON-RPC）  │
└───────────────┬──────────────────────────────────────┘
                │ stdin/stdout（每行一个 JSON）
┌───────────────┴──────────────────────────────────────┐
│ Rust 原生核心（core/，零第三方依赖）                    │
│  engine.rs    引擎调度：Blink/WebKit/Trident 兼容档位   │
│  nav.rs       地址栏归一化（URL/搜索/内部页）           │
│  translate.rs 语言检测·分句·术语统一·中文润色           │
│  download.rs  分片规划·动态再平衡·限速·断点状态         │
│  ipc.rs       JSON-RPC 服务循环                        │
└──────────────────────────────────────────────────────┘
```

---

## 安装

### Linux

从 [Releases](https://github.com/your-org/yc-browser/releases) 下载 `.deb`：

```bash
sudo apt install ./omnibrowser_<版本>_amd64.deb
```

提供两个变体：

- **openKylin 变体** —— 自带 PyQt6 绑定，离线可用
- **deepin 变体** —— 依赖系统 `python3-pyqt6`，ABI 自适应

### Windows

下载 `YcBrowser-<版本>-setup.exe` 安装，或直接运行便携目录中的 `OmniBrowser.exe`。

> **签名状态**：当前发布包的 Windows 安装包使用**自签名证书**（仅用于开发与
> 内部验证），Windows 会提示「未知发布者」，请手动确认后再运行。
> 正式发布将接入 [SignPath Foundation](https://signpath.org) 的免费开源签名
> 服务 —— 该机构核验二进制确实构建自本仓库的公开源码，并向其用户背书。
> 详见 [docs/04-windows-code-signing.md](docs/04-windows-code-signing.md)。

---

## 从源码构建

### 前置

- Rust 1.70+（构建原生核心）
- Python 3.10+
- Linux 打包需 `fakeroot`、`dpkg-deb`；Windows 打包需 [NSIS](https://nsis.sourceforge.io/)

### 构建 Rust 核心

```bash
cd core
cargo build --release
# 产物：core/target/release/omnibrowser-core(.exe)
```

### 运行（开发模式）

```bash
./run.sh                 # Linux 前台启动
# Windows:
python -m src.main
```

### 打包

```bash
# Linux（openKylin + deepin 双包）
./build_one_click.sh --linux
# 或直接调用底层脚本（更可控）
bash package/build_debs.sh

# Windows（便携目录 + NSIS 安装包）
python installer/build_windows.py
# Win11 专用安装包（DPI 感知、任务栏固定等）
python build_windows_win11.py
```

详见 [docs/02-build-and-run.md](docs/02-build-and-run.md) 与
[docs/04-windows-code-signing.md](docs/04-windows-code-signing.md)。

---

## 测试

```bash
# Rust 核心单元测试
cd core && cargo test

# 纯逻辑验证（不启动 Chromium）
python tools/test_logic.py

# 下载引擎端到端（本地 HTTP 服务器 + 真实分片下载 + 字节级校验）
python tools/test_download.py

# 无头逐项功能测试（真实 Blink 渲染）
QT_QPA_PLATFORM=offscreen python tools/test_browser.py
```

---

## 已知边界

1. `setHtml` 的页面在地址栏显示的是 Qt 内部编码 URL（属 Qt 行为，不影响导航）
2. 无 GPU 环境下 Chromium 走软件渲染，复杂页面性能受限
3. Trident 兼容模式是 emulation：老站能按 IE 语义加载，但 ActiveX 等
   Windows 专属能力无法提供（会注入占位垫片避免脚本崩溃）
4. 流媒体（HLS `.m3u8` / DASH `.mpd`）需要分段合并，本软件不内置合并器，
   会提示用户改用外部工具
5. 翻译质量取决于所选后端；术语统一与口语化改写能明显减轻机翻腔，
   但无法完全替代人工润色

---

## 第三方组件

本项目移植了 [SwiftDL](https://github.com/harshsinghsv/swiftdl)（MIT）的下载引擎
算法内核。完整的第三方组件与许可证声明见 [LICENSE](LICENSE)。

---

## 许可证

[MIT](LICENSE)
