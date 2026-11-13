# Windows 独立安装包构建

> 目标：产出一个**不依赖目标机器任何预装软件或运行环境**的安装包。
> 干净 Windows 机器上双击安装即可用，无需 Python、无需 Qt、无需 VC++ 运行库。

---

## 一、曾经的问题

安装后点击桌面图标，弹出：

```
This application failed to start because no Qt platform plugin could be initialized.
Retraining the application may fix this problem.
```

### 根因链条

这不是单一问题，而是三层叠加：

**第一层：PyInstaller 的 Qt hook 被整个跳过**

`hook-PyQt6.py` 的工作方式是：在**隔离的子进程**里 `import PyQt6.QtCore`，
借此探测 Qt 的安装路径，再据此收集插件与资源。

在启用了 Windows 应用控制策略（WDAC / AppLocker）的构建机上，这个 import
会被系统策略拦截：

```
ImportError: DLL load failed while importing QtCore:
应用程序控制策略已阻止此文件。
```

导入失败 → `pyqt6_library_info.version` 为 `None` → hook 里的
`if pyqt6_library_info.version is not None:` 判断不成立 → **整段 hook 被跳过**。

**第二层：产物因此缺失全部 Qt 运行时**

| 缺失项 | 后果 |
|---|---|
| `plugins/platforms/qwindows.dll` | **启动即崩**（即用户看到的报错） |
| `plugins/imageformats/`、`styles/`、`iconengines/`、`tls/` | 图片格式、样式、SVG 图标、TLS 失效 |
| `resources/*.pak`、`icudtl.dat`、`v8_context_snapshot.bin` | 网页空白、乱码、启动变慢 |
| `translations/qtwebengine_locales/*.pak` | 页面显示豆腐块 |
| `QtWebEngineProcess.exe` | 渲染进程缺失，网页完全打不开 |

**第三层：原构建参数本身就选错了**

```python
"--collect-submodules", "PyQt6",   # 只收 Python 子模块，不收 C++ 插件与资源
```

`--collect-submodules` 只处理 Python 层面的子模块，不会带上 Qt 的插件目录与
资源文件；而且它还会把 `QtBluetooth`、`QtQuick3D`、`QtNfc` 等与浏览器无关的
模块一并拖进产物。

---

## 二、修复方案

### 1. 显式收集 Qt6 运行时（不依赖 hook）

`installer/build_windows.py` 的 `_qt_runtime_args()` 按 Qt6 的标准布局，
把以下目录**整体**纳入产物：

```
PyQt6/Qt6/
├── bin/           全部 Qt6 DLL + VC++ 运行时 + opengl32sw（软件渲染回退）
│                  + qt.conf（决定 Qt 到哪找插件，缺了插件必然找不到）
├── plugins/       平台插件、图像格式、样式、图标引擎、TLS
├── resources/     WebEngine 的 pak 资源包、ICU 数据、V8 快照
├── translations/  界面翻译 + qtwebengine_locales（页面 locale 数据）
└── qml/           QML 运行时
```

### 2. 运行时钩子显式指定路径

`installer/_qt_runtime_hook.py` 在程序启动时设置：

| 环境变量 | 指向 |
|---|---|
| `QT_PLUGIN_PATH` | `PyQt6/Qt6` |
| `QT_QPA_PLATFORM_PLUGIN_PATH` | `PyQt6/Qt6/plugins/platforms` |
| `QTWEBENGINEPROCESS_PATH` | `PyQt6/Qt6/bin/QtWebEngineProcess.exe` |
| `QTWEBENGINE_RESOURCES_PATH` | `PyQt6/Qt6/resources` |
| `QTWEBENGINE_LOCALES_PATH` | `PyQt6/Qt6/translations/qtwebengine_locales` |

这是社区公认的标准做法（StackOverflow / PyInstaller issue 均有记载）。
原本由 PyInstaller 自带 hook 负责，但该 hook 恰好被策略拦截了，所以自带一份。

### 3. 打包后对整个产物树签名

产物里的 Python 扩展模块（`PyQt6/*.pyd`）**不带 Authenticode 签名**，
在启用应用控制策略的机器上会被系统直接拒绝加载：

```
Code Integrity determined that a process (python.exe) attempted to load
...\PyQt6\QtCore.pyd that did not meet the Enterprise signing level
requirements ... (Policy ID:{0283ac0f-...})
```

因此 `sign_tree()` 会在打包后对产物树内所有 `.exe` / `.dll` / `.pyd`
批量签名；已带原厂签名（Qt 官方 DLL）的文件自动跳过，保留原签名。

---

## 三、构建

```bash
# 完整构建：PyInstaller → 签名产物树 → NSIS 安装包 → 签名安装包
python installer/build_windows.py --sign-password <PFX密码>

# 只出便携程序
python installer/build_windows.py --no-installer
```

产物：

| 路径 | 内容 |
|---|---|
| `dist/OmniBrowser/` | 便携目录（PyInstaller one-folder） |
| `installer/YcBrowser-<版本>-setup.exe` | NSIS 安装包 |

### 前置依赖

```bash
pip install pyinstaller PyQt6 PyQt6-WebEngine
winget install NSIS.NSIS
winget install Microsoft.WindowsSDK.10.0.18362     # 提供 signtool
```

---

## 四、自检：证明它真的能脱离环境运行

```bash
python tools/verify_bundle.py dist/OmniBrowser --verbose
```

该工具做**纯静态核对**（不执行产物，因此不受本机策略影响），检查七组内容：

1. **Qt 路径解析** —— 按 `qt.conf` 的 `Prefix` 推导 PluginsPath / DataPath /
   LibraryExecutablesPath / TranslationsPath，验证目录存在
2. **运行时钩子** —— 模拟钩子算出的每个环境变量，验证目标路径存在
3. **平台插件** —— `qwindows.dll` 及图像格式、样式、图标、TLS 插件
4. **WebEngine 必需清单** —— 逐项对照
   [Qt 官方部署文档](https://doc.qt.io/qt-6/qtwebengine-deploying.html)：
   `Qt6WebEngineCore.dll`、`Qt6WebEngineWidgets.dll`、`QtWebEngineProcess.exe`、
   `qtwebengine_resources.pak`、`qtwebengine_devtools_resources.pak`、
   `qtwebengine_resources_100p.pak`、`qtwebengine_resources_200p.pak`、
   `icudtl.dat`、`v8_context_snapshot.bin`
5. **依赖闭包** —— 递归解析每个 PE 的导入表，区分「必需缺失」与
   「可选插件的可选依赖」
6. **随包资源** —— Rust 核心、中文字体、Python 运行时、VC++ 运行时、
   `opengl32sw.dll`（无 GPU 机器的软件渲染回退）
7. **签名状态** —— 各 PE 文件的 Authenticode 签名情况

配套的 `tools/audit_dependencies.py` 可单独做依赖审计：

```bash
python tools/audit_dependencies.py dist/OmniBrowser --verbose
```

它以**本机 `System32` 的实际 DLL 清单**作为「系统自带」的判据，
比手工维护白名单可靠得多。

### 判定「可脱离环境运行」的依据

Qt 官方文档给出的标准做法是：
> 把可执行文件复制到一台没有安装 Qt 或任何 Qt 应用的机器上运行。

本项目的等价判据是：产物内每个 PE 的全部导入，要么能在产物自身找到，
要么是 Windows 系统自带（已与 `System32` 实际清单比对），没有第三种情况。

---

## 五、体积构成与精简空间

当前便携目录约 **761 MB**，构成：

| 部分 | 体积 | 可否精简 |
|---|---|---|
| `Qt6/bin` | 349 MB | 可 — 去掉 Quick3D/Bluetooth/Designer 等无关 DLL |
| `Qt6/resources` | 102 MB | 不可 — WebEngine 必需 |
| `Qt6/translations` | 55 MB | 可 — 242 个 `.qm`，只留中英文可省 ~50 MB |
| `Qt6/plugins` | 17 MB | 可 — 去掉 sqldrivers / sceneparsers / qmllint 等可选插件 |
| `Qt6/qml` | 15 MB | 可 — 仅 Qt Quick 集成才需要 |
| 中文字体 | 195 MB | 可 — 只保留界面实际用到的字族 |

现版本按「完整优先」策略全量收集。若需要更小的安装包，
`tools/audit_dependencies.py` 的输出可直接作为精简依据。

---

## 六、已知限制

1. **H.264 / AAC 视频** —— Chromium 140 已把 FFmpeg **静态链接**进
   `Qt6WebEngineCore.dll`（导入表中无外部 ffmpeg 依赖），开源构建不含
   专有编解码器，因此部分 H.264 视频可能无法播放。VP8/VP9/Opus/Vorbis 正常。
   历史上可从 Chrome 提取 `ffmpegsumo.dll` 补齐，但该机制在新版 Chromium
   中已不存在。
2. **SmartScreen 提示** —— 正式发布需接入 SignPath Foundation 或商业 CA 证书。
   当前自签证书只在本机验证流程，公众会看到「未知发布者」。
3. **构建机的应用控制策略** —— 若构建机启用了 WDAC 企业签名级别策略，
   自签证书同样不被信任，本机无法完成 GUI 启动验证；此时应以
   `verify_bundle.py` 的静态自检结论为准。

---

## 七、相关文件

| 文件 | 作用 |
|---|---|
| `installer/build_windows.py` | 构建主脚本（打包 → 签名 → NSIS → 签名） |
| `installer/_qt_runtime_hook.py` | 运行时钩子，指定 Qt 插件与资源路径 |
| `installer/omnibrowser.nsi` | NSIS 安装脚本 |
| `tools/sign_windows.py` | Authenticode 签名工具（含 `sign-tree` 批量签名） |
| `tools/audit_dependencies.py` | PE 依赖审计 |
| `tools/verify_bundle.py` | 独立安装包自检 |
| `docs/04-windows-code-signing.md` | 签名方案与证书获取 |
