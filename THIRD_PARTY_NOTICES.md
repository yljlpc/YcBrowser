# 第三方组件声明

本项目包含或移植了以下第三方开源组件，它们各自遵循独立的许可证。
本项目自身的许可证见 [LICENSE](LICENSE)。


本项目包含或移植了以下第三方开源组件，它们各自遵循独立的许可证：

### SwiftDL（下载引擎算法内核）

- 来源：https://github.com/harshsinghsv/swiftdl
- 许可证：MIT License
- 使用范围：
  - `core/src/download.rs` —— 分片规划、动态再平衡、限速、断点状态、文件探测等算法内核
  - `src/downloader.py` —— 网络层改用 Python 标准库 urllib + 线程池实现
  - `src/media.py` —— 页面媒体嗅探的扩展 content.js 思路

SwiftDL 的作者与版权声明保留在对应源文件的注释中。

### Qt / PyQt6

- Qt 6：https://www.qt.io/ （LGPL v3 / 商业双许可）
- PyQt6：https://www.riverbankcomputing.com/software/pyqt/ （GPL v3 / 商业双许可）
- Chromium / Blink（经由 QtWebEngine）：BSD 许可证及第三方许可证

### Rust 标准库与运行时

- https://www.rust-lang.org/ （MIT / Apache-2.0）

### 随包分发的中文字体

随安装包与源码仓库分发的中文字体为 **思源宋体 Noto Serif SC**，
版权归 Adobe 所有，以 **SIL Open Font License, Version 1.1** 授权：

- 字体文件：`fonts/NotoSerifSC-Regular.otf`
- 许可证全文：[fonts/OFL.txt](fonts/OFL.txt)
- 项目主页：https://github.com/notofonts/noto-cjk

OFL 1.1 允许自由使用、修改、再分发与嵌入到软件中，要求随分发附带
许可证文本，且不得单独售卖字体本身 —— 本项目均已满足。

> **历史说明**：早期版本的安装包曾随包分发方正系列、仿宋系列、楷体系列
> 等**商业字体**（共 21 个，约 192 MB）。这类字体受版权保护、再分发受限，
> 且不符合 SignPath Foundation 对开源分发物的要求（「不得包含专有、
> 非开源组件」），因此已从分发包中移除。
> 若本机已安装方正系列字体，应用仍会优先使用它们（界面观感不变）；
> 未安装时自动回落到随包的思源宋体。

---

## 商标

"Yc浏览器" 及其它相关标识为本项目名称。Windows、Microsoft、Chromium、
Blink、Qt、PyQt6 等商标归各自权利人所有。
