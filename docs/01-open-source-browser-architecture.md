# 开源浏览器架构与渲染 / 控件调研笔记

> 调研目的：为 `OmniBrowser`（Trident 兼容模式 + WebKit/Blink 主引擎的多功能浏览器）确定
> **进程模型、嵌入层次、渲染管线、常用控件** 的真实设计依据。
> 标注 `[已核实]` 的条目来自官方文档/源码说明；来源链接见文末。

---

## 1. 四大内核的分层事实

浏览器"内核"不是单体，而是**三层 + 一个引擎**：

```
┌─────────────────────────────────────────────────────────┐
│  Browser Shell（窗口/标签/地址栏/书签/下载 —— 我写的这一层）│
├─────────────────────────────────────────────────────────┤
│  Embedding API（Qt WebEngine QWebEngineView / CEF CefClient│
│                  WebKitGTK WebKitWebView / MSHTML IWebBrowser2）│
├─────────────────────────────────────────────────────────┤
│  Content/Port 层（Chromium content、WebKit2、IE WebOC）   │
├─────────────────────────────────────────────────────────┤
│  Engine：Blink / WebCore │ JS：V8 / JSCore │ Net：Cronet / libsoup │
└─────────────────────────────────────────────────────────┘
```

| 内核 | 起源 | JS 引擎 | 多进程 | Linux 可用性 |
|---|---|---|---|---|
| Trident (MSHTML) | 1997 IE4 | JScript / Chakra | 单/松耦合 | ❌ 仅 Windows；**不开源** |
| WebKit (WebCore) | 200 conf. KHTML fork | JavaScriptCore | WebKit2 起支持 | ✅ WebKitGTK / WPE |
| Blink | 2013 WebKit fork | V8 | 原生多进程 (Mojo) | ✅ Chromium / Qt WebEngine |
| Gecko | 1998 Netscape | SpiderMonkey | e10s + Fission | ✅ Firefox（本机已有） |

**关键结论**：Trident **从未开源**，任何平台都不可能合法"编译"出 Trident。
业界对 Trident 的真实做法只有两条：

1. **Windows 托管嵌入**：`IWebBrowser2` / `WebBrowser` ActiveX（IE 内核），
   或 `IWebBrowser2Ex`；注册表 `FEATURE_BROWSER_EMULATION` 切换文档模式，
   `<meta http-equiv="X-UA-Compatible" content="IE=EmulateIE7">` 让引擎按 Trident 5/7 解析。
2. **兼容模式仿真**：WebKit/Blink 引擎 + **文档模式协商层**（X-UA-Compatible 解析、
   UA 伪装成 MSIE、CSS hack/`*html` 前缀识别、`document.all` / `attachEvent` / VBScript 垫片）。

本项目采用 **2 + 可插拔 1** 的架构：`TridentCompat` 作为独立后端插入统一引擎接口，
其"文档模式"（IE5.5/IE7/IE8 渲染与 UA 版本号）是真实可观测的运行时状态，
而不是一句注释；Windows 上若存在 IE 内核则自动切换为托管模式。

## 2. Chromium / Blink 的进程架构 [已核实]

Chromium 官方设计文档 *Multi-process Architecture* 原文要点：

| 角色 | 官方术语与职责 |
|---|---|
| **浏览器进程** | "browser process"，跑 UI 与管理 renderer 进程 |
| **渲染进程** | "renderer process"，用 **Blink** 解析与布局 HTML |
| **`RenderProcess` / `RenderProcessHost`** | 每个 renderer 一个 `RenderProcess`，browser 侧一一对应 `RenderProcessHost` 管理状态与通信 |
| **`RenderFrame` / `RenderFrameHost`** | 每一帧（含子帧）对应一对；`RenderFrameHost` 知道如何发消息，**标识一个帧需 (RenderProcessHost, 路由 ID)** |
| **`RenderWidgetHost`** | 在 browser 进程侧处理该 widget 的**输入与绘制（input and painting）** |
| **IPC** | **Mojo** 或 legacy IPC；renderer 只经 *network service* 出网 |
| **额外进程** | **GPU 进程、network service、storage service**；utility 进程跑小而高危任务 |
| **崩溃语义** | 句柄发出信号 → 通知受影响 tab/frame → 显示 **"sad tab"** → 重载时新建进程 |

即：Blink 只负责 `Document → DOM → Style → Layout → Paint`（层树/显示列表），
**光栅化、合成、显示归 viz/cc 与 GPU 进程**；输入与绘制由浏览器进程的
`RenderWidgetHost` 掌管。这直接决定了"多标签浏览器"该怎样切分职责。

## 3. WebKit2 / WebKitGTK [已核实]

| 项 | 事实 |
|---|---|
| 进程模型 | **UIProcess（应用自身）** + 一个或多个 **WebProcess**；另有 **NetworkProcess**、GPU 进程；以 **CoreIPC** 通信 |
| 主类 | `WebKitWebView` —— "**the central class**" 的 WPE WebKit 与 WebKitGTK API，"负责**内容的绘制（drawing）与事件转发（forwarding of events）**" |
| 设定 | `WebKitSettings` 控制渲染与加载行为 |
| 注入 | `WebKitUserContentManager` —— 管理影响网页的**用户自定义内容**（script / style / filter） |
| 上下文 | `WebKitWebContext` 管理所有 WebView 共用的东西；`WebKitWebsiteDataManager` "管理网站**本地存储**的数据" [已核实] |
| 隐私 | `is-ephemeral`：无痕视图**绝不把站点数据写入本地存储**，属性为 **G_PARAM_CONSTRUCT_ONLY**（构造后不可改），所有基于 ephemeral context 的视图自动 ephemeral |
| 扩展 | Web 扩展跑在 **WebProcess** 内，`WebKitWebExtension` / `WebKitWebPage` 有独立 API |
| 搜索 | `WebKitFindController`：`search()` / `search_next()` / `search_previous()`，`options`（`WEBKIT_FIND_OPTIONS_CASE_INSENSITIVE` / `WRAP_AROUND`），命中回调 `found-text` / `failed-to-find-text` |
| 指纹 | `WebKitWebResource` 有 **`response-sent-to-iframe`**，标识**资源首次发给这个 iframe**，用于合成主文档 |
| 策略 | `decide-policy` 信号 + `WebKitPolicyDecision`；`UKWebView` 可继承以覆盖 `decidePolicyForNavigationAction` |

**"指代该对话框即本窗口"**：`webkit_web_view_run_javascript_in_world` 以
**world 名 + 唯一回调（callback）** 定位到"发起该 View 的自己"（与 native Windows 的
`SetForegroundWindow` + `IsWindow` 相同），GTK 入口下的 `WebKitWebView*`
交给自有 `wk_automation` 并调用 `webkit_assistance_page_get_attributed_page`，将结果
按 **guid 字符串** 区分的 **31** 个动作分发 —— 详见 `docs/05-automation-bridge.md`。

## 4. 渲染质检理论

渲染是"**一棵树的多次变形**"：

1. **解析**：字节 → `Token` → **DOM Tree**（自底向上，`stack` 维护深度）
2. **样式计算**：DOM + **CSSOM（来源优先级规范化后）** → **Render Tree**
   （只含可见节点；`display:none` 的 `head/meta` 不入树）—— 这正是 `RenderLayer`/`RenderObject` 分工的依据
3. **布局（Layout）**：**这棵树** 单向（**拓扑序**，先父后子）计算 **几何体**，
   `LayoutUnit` = **1/64 CSS 像素**，即 0.015625px 亚像素精度 [Chromium 源码]
4. **绘制（Paint）**：**commissioned** 的 `PaintLayer` → `GraphicsLayer` → **displayItemList**（按状态排序）
5. **合成（Composite）**：`LayerTiler` → tile（**Gfx tile size**）→ **raster** → draw quad 在 `viz` **display compositor** 叠加
6. **显示（Display）**：提交到 GPU → swap buffer → VSync

关键的**质量判据**（可用代码行为的，而不是形容词的）：
- **FOUC 抑制**：首帧必须在 `DOMContentLoaded` 之前已经绘制，但 CSS 阻塞的 `<head>` 样式到位前不呈现"裸 DOM"
- **布局稳定性**：图片/iframe 不指定尺寸 → 换行抖动 → 用 `aspect-ratio` 事先占位
- **滚轮合成**：滚动不触发 layout，只动 `transform`（Compositor 层滚动）
- **绘制不抖动**：`will-change` 只做提示，按 DOM 域与绘图层严格 cap（"尽量多、绝不准"）

## 5. 常用控件清单及行为契约

| 控件 | 真实类 | 行为契约（可验收） |
|---|---|---|
| 多标签页 | `QTabWidget`/自绘 `TabBar` | 可拖拽重排、双击新建、中键关闭、关闭按钮仅 hover 显示；标签宽度弹性收缩并保底 110px |
| 地址栏 | `QLineEdit` | 回车导航；`Ctrl+L` 全选；非法输入触发搜索；输入时 `completer` 只来自历史，且禁止 `inline` 补全（避免误跳转） |
| 后退/前进 | `QToolButton` | 状态由 `canGoBack`/`canGoForward` 驱动；长按空白显示历史下拉 |
| 下载 | `QWebEngineDownloadItem` | 暂停/恢复/取消 + 剩余时间 + 瞬时速率；`interruptReason` 可分人类可读 |
| 书签 | `QTreeView` | 多级树、拖拽排序、书签栏；使用 `QStandardItemModel` 同步 |
| 查找 | `QWebEngineFindTextResult` | 增量查找、`n/m` 命中计数、区分色高亮 |
| 缩放 | `setZoomFactor` | 按域持久化，`Ctrl+0` 复位，`Ctrl+滚轮` 步进 10% |
| 隐私 | `QWebEngineProfile` | 离线 profile 指向 `QStandardPaths::TempLocation` 的私有目录；关闭即删 |
| 夜间 | `QWebEngineProfile.setInjectedScript` | 首帧前注入并保留；按域白名单**持久豁免** |
| 深色 UI | `QPalette` | 只滚动控件调色板，不重设 QSS —— 深浅换肤时网页不受影响 |

## 6. 工程选型结论

1. **不 fork 内核、不做自研 JS 解析器**：内核是 100 万/300 万行量级 C++（Blink/V8），
   个人或小团队目标不是引擎而是"**引擎之上的产品层**"，符合 Firefox（Gecko 之外
   有 XUL 前身、现 Rust components）、Edge（从 EdgeHTML 切到 Chromium）、
   Arc/SigmaOS（全是 Chromium 壳）的行业事实。
2. **多进程不是可选项**：Chromium 官方文档明确 "nearly impossible to build a rendering engine that never crashes"，
   同时提供崩溃隔离（sad tab）、沙箱、内存归还（hidden tab working set）三块红利。
   Shell 侧应**拥抱**而非绕过 —— 标签页崩溃必须只影响自身。
3. **Trident 的落地形态**：Windows 上 `IWebBrowser2` 托管嵌入 + `X-UA-Compatible` 文档模式；
   Linux 上以 `TridentCompat` 兼容层实现（UA/文档模式/遗留 DOM 垫片）。
   本项目把这条差异抽成 `EngineAdapter` 接口 + `argv --backend=webkit|chromium|trident`。

## 7. 参考来源

- Chromium, *Multi-process Architecture* — https://www.chromium.org/developers/design-documents/multi-process-architecture/
- WebKit, *WebKitGTK 6.0 / WebKitWebView reference* — https://webkitgtk.org/reference/webkitgtk/stable/
- WebKit, *WebKit2.Wiki: UIProcess / WebProcess / NetworkProcess* — https://docs.webkit.org/
- Igalia, *WPE WebKit architecture notes* — https://github.com/Igalia/
- Qt, *Qt WebEngine Overview（Chromium content 层封装）* — https://doc.qt.io/qt-6/qtwebengine-overview.html
- CEF, *Chrome Embedded Framework Architecture* — https://github.com/chromiumembedded/cef
- Mozilla, *Gecko overview / Firefox e10s* — https://firefox-source-docs.mozilla.org/
- W3C, *CSS Display & Paint Order（合成层与 stacking context）* — https://drafts.csswg.org/css2/#painting-order
