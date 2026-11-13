# OmniBrowser 构建与运行

## 架构总览

```
┌──────────────────────────────────────────────────────┐
│ PyQt6 / Qt 6 前端（src/）                             │
│  main.py      启动入口（注册字体/主题/核心子进程）      │
│  window.py    主窗口：工具栏·地址栏·引擎切换·多标签·自适应│
│               翻译 / 下载 / 媒体 / 无痕 / 打印           │
│  tab.py       标签页：QWebEngineView + 独立 profile    │
│               （UA 注入 / Trident 垫片 / 内部页拦截）   │
│  translate.py 翻译客户端（MyMemory/Google/LibreTranslate）│
│  downloader.py 多连接分片下载引擎（多线程 + Range）    │
│  download_ui.py 下载管理器界面                        │
│  media.py    页面媒体嗅探（视频/音频直链）             │
│  core_client.py  Rust 核心 IPC 客户端（行式 JSON-RPC） │
│  fonts.py / theme.py / internal.py / layout.py        │
└───────────────┬──────────────────────────────────────┘
                │ stdin/stdout（每行一个 JSON）
┌───────────────┴──────────────────────────────────────┐
│ Rust 原生核心（core/，零第三方依赖）                    │
│  engine.rs  引擎调度：Blink/WebKit/Trident 兼容档位     │
│  nav.rs     地址栏归一化（URL/搜索/内部页）             │
│  translate.rs 语言检测·分句·术语统一·中文润色           │
│  download.rs 分片规划·动态再平衡·限速·断点状态·文件探测 │
│  ipc.rs     JSON-RPC 服务循环                          │
│  json.rs    手写 JSON 解析/序列化                      │
└──────────────────────────────────────────────────────┘
```

- **渲染核心**：Blink（QtWebEngine 6.10.2，Chromium content + V8）。
- **Trident**：Linux 无原生 MSHTML，以「兼容模式」落地 —— 按
  `X-UA-Compatible`（含 `EmulateIE7` 等真实页面写法）协商文档模式，
  并按档位伪装 IE UA + 注入遗留 DOM 垫片（document.all / attachEvent）。
- **WebKit**：以 WebKit UA 伪装运行（真实 WebKitGTK 渲染需另接 gi 绑定，见 docs/01）。
- **翻译**：网络请求在前端（标准库 urllib），语言学处理在核心
  （确定性、可单测）；两者经 JSON-RPC 协作。
- **下载**：移植自 SwiftDL（MIT）的算法内核 —— 核心零依赖无法引入
  reqwest/tokio，故保留分片与再平衡算法，网络层换标准库 urllib + 线程池。

## 环境要求

- openKylin / Debian 系，Qt 6.10+ 运行库
- PyQt6 + QtWebEngine（已解包到 `_stage/pyqt6root/`，见下）
- Rust 1.7x+（构建核心）

## 构建 Rust 核心

```bash
cd core
CARGO_HOME=../_stage/cargohome CARGO_TARGET_DIR=$PWD/target cargo build --release
# 产物：core/target/release/omnibrowser-core
```

## 运行

```bash
./run.sh                 # 前台启动
# 或手动：
PYTHONPATH=_stage/pyqt6root/usr/lib/python3/dist-packages:. python3 -m src.main
```

`run.sh` 会自动拼好 `PYTHONPATH`（指向私有 PyQt6 前缀）与
`QTWEBENGINE_CHROMIUM_FLAGS`（`--no-sandbox --disable-gpu` 等，
沙箱/无 GPU 环境必需；`src/main.py` 内置了相同默认值）。

## 测试

```bash
# 1) Rust 核心单元测试（46 项）
cd core && cargo test --offline

# 2) 纯逻辑验证（78 项，不启动 Chromium；导入 internal/layout/translate 等纯模块）
python3 tools/test_logic.py

# 3) 下载引擎端到端（22 项，本地 HTTP 服务器 + 真实分片下载 + 字节级校验）
python3 tools/test_download.py

# 4) 无头逐项功能测试（66 项，真实 Blink 渲染）
PYTHONPATH=_stage/pyqt6root/usr/lib/python3/dist-packages:. \
QT_QPA_PLATFORM=offscreen \
QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu --disable-dev-shm-usage" \
python3 tools/test_browser.py

# 5) 整页翻译端到端（10 项，真实网络 + 真实渲染 + 真实 DOM 回填）
QT_QPA_PLATFORM=offscreen python3 tools/test_translate_e2e.py
```

> 注：PyQt6 6.12 的 wheel 已不含 WebEngine，需另外安装 `PyQt6-WebEngine`；
> 系统 PyQt6 6.10.2（`_stage/pyqt6root/`）则自带。

## 实时翻译

1. 点击工具栏「翻译」或菜单「翻译此页为中文…」。
2. 提取页面可见正文（跳过脚本/代码/输入框）→ 逐句送译 → 术语统一 + 口语化改写 → 回填 DOM。
3. 菜单「还原页面原文」一键还原。

后端可在「设置」中切换：MyMemory（默认免费）/ Google / LibreTranslate / 自定义端点
（自定义端点地址支持 `{text}` `{source}` `{target}` 占位符，或按 JSON POST 约定）。
目标语言与自定义术语表同样在「设置」中配置。

## 分辨率自适应

`window.compute_ui_scale()` 按 `主屏分辨率/1920x1080` 与 `devicePixelRatio`
计算缩放系数（夹在 0.8–2.2），并监听屏幕几何/DPI 变化实时重应用：

- 工具栏图标尺寸、地址栏/下拉框字号与高度
- 每个标签的网页缩放（`QWebEngineView.setZoomFactor`）
- 状态栏显示当前缩放百分比；设置里可关闭自适应或手动指定缩放百分比

## 高速下载

下载请求由浏览器的多连接分片引擎接管（移植自 SwiftDL 的算法内核）：

- **多连接**：单文件最多 32 个连接并行（设置中可调，默认 8）。
- **动态再平衡**：某连接完成后立即接手剩余量最大的一段，避免末尾空转。
- **无合并步骤**：文件预先按总长分配，各连接直接写入自己的偏移。
- **降级**：服务器不支持 `Range` 时自动改用单线程下载。
- **断点续传**：`.omnidl` 记录仍缺失的字节区间，崩溃/断网最多损失最后一秒进度；
  可在下载管理器中暂停 / 继续 / 取消。
- **分类归档**：按扩展名归入「视频 / 音乐 / 程序 / 压缩包 / 文档」子目录。
- **媒体嗅探**：菜单「下载页面媒体…」可列出页面中的视频与音频直链并直接下载
  （HLS/DASH 流媒体需外部合并工具，会明确提示）。

## 已知边界

1. `setHtml` 的页面在地址栏显示的是 Qt 内部编码 URL（属 Qt 行为，不影响导航）。
2. offscreen / 无 GPU 环境下 Chromium 走软件渲染，复杂页面性能受限。
3. Trident 兼容模式是 emulation：老站能按 IE 语义加载，但 ActiveX 等
   Windows 专属能力无法提供（会注入占位垫片避免脚本崩溃）。
4. 流媒体（HLS `.m3u8` / DASH `.mpd`）需要分段合并，本软件不内置合并器，
   会提示用户改用外部工具。
5. 翻译质量取决于所选后端；术语统一与口语化改写能明显减轻机翻腔，
   但无法完全替代人工润色。
