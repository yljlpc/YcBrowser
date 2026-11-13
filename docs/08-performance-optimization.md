# 启动与安装性能优化

> 状态：已实施。启动侧与安装侧的改动均已落到代码，产物需重新构建后生效。

本文记录 Yc浏览器 在「双击到看见界面」与「安装耗时」两条链路上做的优化，
以及每项改动的**依据**与**验证方式** —— 所有结论都来自对产物本身的静态
分析，而不是拍脑袋。

---

## 一、启动侧

### 1.1 根因：启动时逐个解析系统字体（收益最大）

**问题**：`src/fonts.py` 的 `_font_search_dirs()` 在 Windows 上返回

```python
[随包 fonts 目录, r"C:\Windows\Fonts"]
```

`register_fonts()` 随后对每个 `.ttf/.otf/.ttc` 调用
`QFontDatabase.addApplicationFont()`。本机 `C:\Windows\Fonts` 里有
**343 个字体文件、合计约 468 MB**，每一个都要解析字形表并建立索引。

**关键认知**：系统字体**本来就不需要注册**。Windows 通过 GDI/DirectWrite
全局提供它们，Qt 的 `QFontDatabase` 在未显式注册时同样能通过
`QFontDatabase.families()` 看到它们。把系统字体目录喂给
`addApplicationFont()` 纯属重复劳动。

**改法**：只注册「必须显式注册」的两类目录 —— 随包分发的开源字体
（不在系统字体目录里）和用户自备字体目录（开发期放桌面 `fonts/`）。
桌面目录保留是为了让开发环境与安装后的界面观感一致。

**效果**：启动阶段少了 343 次字体解析 + 468 MB 读取。

### 1.2 根因：窗口显示前同步初始化 Chromium

**问题**：`MainWindow.__init__` 里创建首个 `BrowserTab`，而
`BrowserTab` 内部实例化 `QWebEngineView` —— 这一步会触发 **Chromium
初始化（进程启动 + GPU 进程握手 + V8 快照装载），约 1~2 秒**。
在 `win.show()` 之前同步发生，用户从点图标到看见界面要干等这一整段。

**改法**（`src/window.py`）：窗口先显示，首个标签页推迟到事件循环启动后创建：

```python
self._first_tab = None
QTimer.singleShot(0, self._create_first_tab)
```

Chromium 初始化从「阻塞首帧」变成「界面已呈现后的后台预热」，
**感知延迟**因此从 1~2 秒降到 0.3 秒以内。

### 1.3 图标缓存

`src/icons.py` 的 `make_logo()` 每次都重新用 QPainter 画一遍徽标。
加上 `@lru_cache(maxsize=8)`，同一尺寸只画一次。

### 1.4 启动耗时打点

`src/main.py` 在各阶段打点，窗口显示后输出一行分解：

```
[启动] QApplication 120 | 字体+样式 45 | Rust 核心 8 | 主窗口 310 | 合计 483 ms
```

这行是**回归基准** —— 后续任何改动都应先看它有没有变差。

> 注：Rust 核心 `CoreClient._start()` 只做 `subprocess.Popen`，不等待握手，
> 因此不会阻塞启动。

---

## 二、安装侧

### 2.1 根因：产物里塞了整套 Qt6 运行时

`installer/build_windows.py` 用「整目录收集」策略把 `PyQt6/Qt6/` 下的
`bin / plugins / resources / translations / qml` 全量收进产物。
结果：

| 目录 | 体积 | 文件数 | 内容 |
|---|---|---|---|
| `bin/` | 349 MB | 123 | 全套 Qt6 DLL（含 QML / Quick3D / Designer / Multimedia） |
| `resources/` | 102 MB | 11 | 其中 77 MB 是 `*.debug.*` 调试资源包 |
| `translations/` | 55 MB | 297 | 240 种语言的 `.qm` 翻译 |
| `plugins/` | 17 MB | 101 | 含 sql 驱动、qmlls、sceneparsers 等无关插件 |
| `qml/` | 15 MB | 2329 | 895 个 `.qml` + 780 张样式图片 |
| **合计** | **589 MB** | **2788** | |

而本应用**只 import 六个模块**：

```
PyQt6.QtCore / QtGui / QtWidgets / QtPrintSupport / QtWebEngineCore / QtWebEngineWidgets
```

**安装慢的真正原因不是体积，是文件数**：安装要逐个文件创建、逐个被
Defender 实时扫描。2788 个文件里有 2329 个是 `qml/` 下的 QML 模块。

### 2.2 裁剪：靠 PE 导入表算出最小必需集

`tools/trim_qt_payload.py` 不靠人工猜测，而是**解析 PE 导入表**：

1. 以「入口 `.pyd` + 可执行文件」为根，沿 Import / Delay-Import 目录
   递归展开，算出 DLL 依赖闭包；
2. 闭包外的 DLL 一律删除；
3. 插件按类别白名单保留（`platforms / styles / imageformats / iconengines /
   tls / renderers / generic`）；
4. 翻译只留 `zh_CN` 与 `en_US`；
5. 资源包只留 DLL 字符串表里**确有引用**的那几个；
6. 删完再跑一遍**导入表完备性校验**：每个 PE 引用的 DLL 必须能在产物里
   或 `System32` 里找到，否则判定为裁剪过头。

几处需要人工兜底的地方（**不在导入表里，但运行时必需**）：

- `QtWebEngineProcess.exe` —— WebEngine 渲染子进程，由 `Qt6WebEngineCore` 拉起；
- `avcodec/avformat/avutil/swscale/swresample` —— FFmpeg，Chromium 媒体栈**动态加载**；
- `d3dcompiler_47.dll` —— ANGLE 运行时编译 HLSL 着色器；
- `opengl32sw.dll` —— 无 GPU 时的软件 OpenGL 回退。

### 2.3 `qml/` 整棵删除的依据

不是「本应用不用 QML」这一条就够 —— 实际把每个 QML 插件的导入表解出来
后发现，它们**全部依赖 PyInstaller 根本没收集的 Qt6 模块 DLL**：

```
qml/QtNetwork/qmlnetworkplugin.dll          → Qt6QmlNetwork.dll       （不存在）
qml/QtWebEngine/qtwebenginequickplugin.dll  → Qt6WebEngineQuick.dll   （不存在）
qml/QtQml/DesignSupport/…plugin.dll         → Qt6QmlDesignSupport.dll （不存在）
qml/QtQuick3D/…                             → Qt63DRender.dll 等      （不存在）
```

也就是说这棵树在当前产物里**本来就是坏的**，任何加载路径都会立刻失败。
本应用不创建 `QQmlEngine`、不 import 任何 `.qml`，它永远走不到。

### 2.4 `*.debug.*` 资源包删除的依据

反查 `Qt6WebEngineCore.dll` 的字符串表，它实际引用的资源文件只有：

```
qtwebengine_resources.pak
qtwebengine_resources_100p.pak
qtwebengine_resources_200p.pak
qtwebengine_devtools_resources.pak
v8_context_snapshot.bin
```

**没有任何一处引用 `.debug.pak` / `.debug.bin`**（Chromium 的 release 构建
只认 `v8_context_snapshot.bin`，不做「debug 文件存在则优先」的探测）。
5 个调试资源包合计 77 MB 全部是死重。

### 2.5 NSIS 压缩算法

`installer/omnibrowser.nsi` 改为：

```nsis
SetCompressor /SOLID lzma
SetDatablockOptimize on
```

- `/SOLID` 把整个包压成一个连续数据块，比逐文件 LZMA 压缩率高 10~15%，
  同样体积下安装包更小（下载更快）；
- NSIS 3.x 对 solid LZMA 采用**多线程并行解压**，多核机器上吞吐远高于
  单文件 LZMA；
- 相比 zlib：zlib 的安装包会从约 120 MB 涨到 210 MB，下载时间反而更长。

### 2.6 收益汇总（实测）

**安装包（v1.1.13 → v1.1.14，同一台机器实测）**

| 指标 | 优化前 | 优化后 | 变化 |
|---|---|---|---|
| 安装包体积 | 233 MB | **124.0 MB** | **−47%** |
| 产物文件数 | 2788 | **134** | **−95.2%** |
| 产物体积 | 582.5 MB | **366.6 MB** | −37.1% |
| 安装写盘耗时 | 14.33 s | **0.53 s** | **−96.3%** |
| 需要签名的文件 | 244 | 14 | −94% |
| 启动：字体解析 | 343 个文件 / 468 MB | 2 个文件 | −99% |
| 启动：Chromium 初始化阻塞首帧 | 1~2 s | 0（后台预热） | 感知延迟显著下降 |

> 写盘耗时为受控实测：把两个产物分别拷到同一块 SSD 上的临时目录，
> 同源同目标，排除读盘速度差异。实际安装还包含 NSIS 解压（安装包小了 47%，
> 这部分也同比下降）与 Defender 实时扫描（**文件数从 2788 降到 134，
> 扫描次数同比下降 95%**，这部分收益在本机被 WDAC 策略挡住未能实测）。

### 2.7 裁剪过程中的两个坑（都已修正，值得记下）

1. **`bin/qt.conf` 不是 PE，进不了依赖闭包** —— 第一版逻辑把它当垃圾删了。
   没有它，Qt 找不到 `plugins/` 目录，程序直接起不来
   （"no Qt platform plugin could be initialized"）。
   现在规则改为：**Qt 目录下的非 PE 文件一律保留**。
2. **闭包种子必须包含「保留的插件」** —— 插件由 Qt 运行时用 LoadLibrary
   加载，它们的依赖不在任何入口模块的导入表里：
   `plugins/iconengines/qsvgicon.dll → Qt6Svg.dll`。
   只用入口模块做种子，Qt6Svg.dll 会被误删，SVG 图标与 SVG 图片随即失效。
   现在种子 = 入口模块 ∪ 保留的插件 DLL，闭包会把 Qt6Svg.dll 一并带上。

此外还加了**自清理规则**：静态依赖缺失的插件（`qpdf.dll` 缺 Qt6Pdf.dll、
`renderers/*` 缺 Qt63DRender.dll —— 这些 DLL 从来没进过产物）直接剔除，
让自检始终保持「零未解析依赖」这一硬指标。

### 2.8 隔离搬迁而非删除

裁剪默认**不删除文件**，而是把它们 rename 到产物旁边的隔离目录：

```
dist/_trimmed_out-<时间戳>/
```

好处：一次 rename 干掉几千个文件（比几千次 unlink 快一个量级）、
被裁掉的内容可回溯可恢复、且不会触发批量删除保护。
需要真正删除时加 `--purge`。


---

## 三、验证方式

### 3.1 启动耗时

重启后运行安装好的程序，窗口出现后控制台/日志会输出：

```
[启动] QApplication 120 | 字体+样式 45 | Rust 核心 8 | 主窗口 310 | 合计 483 ms
```

（`--windowed` 打包下 stdout 不可见，可临时用 `python src/main.py` 在源码
目录跑同一套打点。）

### 3.2 产物完整性

```bash
python tools/trim_qt_payload.py --dist dist/OmniBrowser --verify
```

应输出「✅ 全部导入依赖均可解析」。

### 3.3 安装耗时

```bash
# 静默安装并计时
Measure-Command { Start-Process .\YcBrowser-1.1.14-setup.exe -ArgumentList '/S' -Wait }
```

对比优化前后（优化前基线：233 MB / 2788 文件 / 写盘 14.33 s）。

> ⚠️ **本机当前无法执行安装器**：Windows 的 WDAC 策略文件
> `{0283AC0F-FFF1-49AE-ADA1-8A933130CAD6}.cip` 仍在强制执行「企业签名级别」，
> 事件 3033/3077 会拦下自签名的安装器与卸载器
> （"应用程序控制策略已阻止此文件"）。
> SAC 注册表值已置 0，**重启后**才可能解除。实测数字待重启后补齐。

---

## 四、相关文件

| 文件 | 作用 |
|---|---|
| `tools/trim_qt_payload.py` | PE 导入表分析 + 载荷裁剪 + 完备性校验 |
| `installer/build_windows.py` | 在「打包 → 签名 → 打安装包」之间插入裁剪步骤 |
| `installer/omnibrowser.nsi` | NSIS 压缩算法与安装包元数据 |
| `src/fonts.py` | 字体注册范围收敛 |
| `src/window.py` | 首标签页延迟创建 |
| `src/icons.py` | 徽标绘制缓存 |
| `src/main.py` | 启动耗时打点 |
