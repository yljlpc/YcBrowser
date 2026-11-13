# OmniBrowser 功能测试报告

- 日期：2026-11-11
- 环境：openKylin 3.0 (huanghe) / Qt 6.10.2 / PyQt6 6.10.2 / Rust 1.99.1 / WebKit2GTK 2.28.1
- 运行方式：`QT_QPA_PLATFORM=offscreen`（无头）+ `tools/test_browser.py`
- 结论：**28 / 28 全部通过**；另在 Xvfb 下完成真实渲染截图验证。

## A. Rust 核心 IPC（13 项）

| # | 用例 | 结果 |
|---|------|------|
| 1 | ping | PASS |
| 2 | 导航：裸域名 example.org → https://example.org | PASS |
| 3 | 导航：localhost:8080 → http://localhost:8080（不送搜索引擎） | PASS |
| 4 | 导航：含空格「rust 语言」→ 百度搜索 URL（百分号编码） | PASS |
| 5 | 导航：显式 scheme 保留 | PASS |
| 6 | 导航：omni://settings → 内部页 | PASS |
| 7-9 | 引擎规格：Blink / WebKit / Trident 三档均返回有效 UA | PASS |
| 10 | Trident 档 UA 含 Trident 标记 | PASS |
| 11 | Blink 档 UA 含 Chrome 标记 | PASS |
| 12 | 文档模式协商：`IE=EmulateIE7` → IE7（真实页面写法） | PASS |
| 13 | 文档模式协商：`IE=edge` → Edge | PASS |

另有 Rust 侧单元测试 **10 / 10 通过**（`cargo test`）。

## B. 前端 GUI（15 项）

| # | 用例 | 结果 |
|---|------|------|
| 1 | 随附中文字体注册（22 个字族成功加载） | PASS |
| 2 | 自适应缩放系数取值合理（0.8–2.2） | PASS |
| 3 | apply_ui_scale 应用不崩溃 | PASS |
| 4 | 工具栏图标尺寸随缩放变化 | PASS |
| 5 | 标签加载 data URL | PASS |
| 6 | JS 读取页面标题（Blink 渲染 + runJavaScript 通路） | PASS |
| 7 | 二次加载后标题更新 | PASS |
| 8 | 历史可后退 | PASS |
| 9 | 后退后标题恢复 | PASS |
| 10 | 前进后标题恢复 | PASS |
| 11 | 切换 Trident 引擎后 UA 变为 IE11 串 | PASS |
| 12 | 切回 Blink 后 UA 变回 Chromium 串 | PASS |
| 13 | 内部关于页渲染（中文标题正确读回） | PASS |
| 14 | 多标签新增计数 +1 | PASS |
| 15 | 网页缩放因子 > 0 且随自适应变化 | PASS |

## C. 真实渲染截图（Xvfb / offscreen）

- `outputs/omni_ui.png`：整窗截图 —— 工具栏（后退/前进/刷新/停止/主页）、
  地址栏、引擎下拉「Blink（Chromium）」、搜索引擎下拉「必应」、
  「＋新标签」「设置」按钮、标签页（中文标题+favicon）、状态栏「缩放 80%」。
- `outputs/omni_page.png`：页面渲染层截图 —— 中文标题/正文/链接均由
  Blink 实际排版输出，字体渲染正常。

## 过程中发现并修复的问题

1. **Cargo.toml 缺 `[package]` 表头** → cargo 误判 virtual manifest，补齐后通过。
2. **JSON `parse` 是自由函数** 而非 `Json::parse` → ipc.rs/lib.rs 调用点修正。
3. **`IE=EmulateIE7` 未被识别**（真实页面常见写法）→ `from_ua_compatible`
   增加 `emulateie` 前缀剥离，新增回归测试。
4. **Qt6 枚举路径变化**：`QStyle.SP_*` → `QStyle.StandardPixmap.SP_*`，
   `SP_DirHome` → `SP_DirHomeIcon`。
5. **Qt6 UA 设置层级变化**：UA 在 `QWebEngineProfile` 而非 page 层 →
   每标签改用独立 profile，实现真正的按标签引擎隔离。
6. **测试脚手架**：data URL 内嵌中文会经 URL 层转码（测试法问题，非浏览器
   缺陷），改用 ASCII 标题做导航/历史断言，中文渲染改由 setHtml+UTF-8 meta 验证。
