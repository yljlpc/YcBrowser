# Code signing policy

> Free code signing provided by SignPath.io, certificate by SignPath Foundation.

本文档说明 Yc浏览器（YcBrowser）的代码签名策略。

---

## 签名者是谁

本项目的 Windows 发行包由 **SignPath Foundation** 签发证书进行 Authenticode
签名。证书签发给基金会本身，而非任何个人或公司；基金会核验「被签名的二进制
确实构建自本公开仓库的源码」，并以自身名义为其背书。

因此用户看到的发布者名称是 **SignPath Foundation**。

## 签名覆盖范围

| 产物 | 是否签名 |
|---|---|
| `YcBrowser-<版本>-setup.exe`（Windows NSIS 安装包） | ✅ 签名 |
| 便携目录内的全部 `.exe` / `.dll` / `.pyd` | ✅ 签名 |
| Linux `.deb` 包 | ✅ 签名（Debian 包签名机制） |

## 构建与验证

- 构建在 **GitHub Actions** 中自动完成（见 `.github/workflows/build-windows.yml`），
  GitHub 已注册为 SignPath 的「可信构建系统」。
- **不使用任何跨构建的产物缓存**：每次发布都从源码重新编译 Rust 核心并重新
  打包，保证二进制与该 tag 对应的源码一一对应。
- 构建配置全部来自源码控制中的文件，不依赖 CI 界面的临时覆盖。
- 每次发布前执行 `python tools/verify_bundle.py dist/OmniBrowser`，
  静态核对 Qt 运行时、WebEngine 资源与依赖闭包是否齐备。

## 审批流程

签名请求**必须由具有 approver 角色的成员人工批准**，不会自动发布。

- 提交者（submitter）发起签名请求
- approver 审阅该 tag 的源码变更与构建日志
- 批准后 SignPath 用 HSM 中的私钥签名并加盖可信时间戳

## 团队角色

| 角色 | 职责 | 成员 |
|---|---|---|
| **Author** | 可直接向仓库提交变更，无需额外评审 | [`@yljlpc`](https://github.com/yljlpc) |
| **Reviewer** | 负责评审非 committer 提交的 PR | [`@yljlpc`](https://github.com/yljlpc) |
| **Approver** | 负责批准每一次签名请求 | [`@yljlpc`](https://github.com/yljlpc) |

> 本项目目前由单一维护者 `yljlpc` 承担上述三种角色。SignPath Foundation
> 要求角色职责清晰且每次签名都有人工批准，该约束通过 SignPath 控制台中
> 配置的 approver 权限与「人工批准」签名策略落实：即使只有一名成员，
> 签名请求也不会自动通过，必须由 approver 在 SignPath 面板中显式批准。
> 未来引入新成员时，应将 Reviewer 角色移交给独立的评审者。

> 所有团队成员均已在 **GitHub** 与 **SignPath** 账号上启用
> **多因素认证（MFA）**。

## 隐私

本项目的隐私实践见 [PRIVACY.md](PRIVACY.md)。

## 上游组件

随包分发的第三方组件（如 Qt 6、PyQt6、Rust crates）保留其各自原有签名或许可证，
不由本项目的证书重新签名。完整清单见 [LICENSE](../LICENSE)。

## 报告问题

若发现签名流程被滥用，或某个被签名的发布物与本仓库源码不符，
请通过仓库的 Security Advisory 私密上报，不要公开披露。
