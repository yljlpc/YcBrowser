# SignPath Foundation 申请表 —— 逐字段填写稿

> 申请入口：<https://signpath.org/apply>
>
> 本文件按 signpath.org/apply 的真实字段逐条给出**可直接粘贴**的答案。
> 标注 🔒 的字段涉及个人身份信息，**必须由账号持有人本人填写**，不得由他人代填。
> 标注 ⚠️ 的字段涉及本人声明，**必须由本人阅读条款后亲自勾选**，不得预先勾选。

配套文档：[05-signpath-application.md](05-signpath-application.md)（流程与背景说明）

---

## 一、项目信息（自动填入）

| 字段 | 是否必填 | 填写内容 |
|---|---|---|
| **Project Name** | 必填 | `YcBrowser` |
| **Repository URL** | 必填 | `https://github.com/yljlpc/YcBrowser` |
| **Homepage URL** | 必填 | `https://github.com/yljlpc/YcBrowser` |
| **Download URL** | 选填 | `https://github.com/yljlpc/YcBrowser/releases` |
| **Privacy Policy URL** | 选填 | `https://github.com/yljlpc/YcBrowser/blob/main/PRIVACY.md` |
| **Wikipedia URL** | 选填 | 留空（本项目无维基条目） |
| **Tagline** | 必填 | 见下方 §1.1 |
| **Description** | 必填 | 见下方 §1.2 |
| **Reputation** | 必填 | 见下方 §1.3 |
| **Maintainer Type** | 选填 | `Individual maintainer(s)` |
| **Build System** | 选填 | `GitHub Actions` |

### 1.1 Tagline

> 一句话说明项目是什么、给谁用。控制在 100 字符内。

```
Multi-engine desktop browser with live translation and a multi-connection downloader.
```

### 1.2 Description

> 说明：这是什么类型的应用、目标用户是谁、分发什么产物、是否由 CI 从公开源码构建。

```
YcBrowser is an open-source desktop web browser for Windows and Linux. It is built on a
Rust native core (navigation, document-mode negotiation, language detection, sentence
splitting and download planning) with a PyQt6 / Qt 6 WebEngine shell. It targets desktop
users who want a browser that handles Chinese-English page translation and large-file
downloads efficiently, without installing a separate runtime.

The project distributes a Windows NSIS installer (YcBrowser-<version>-setup.exe) and
Debian packages (.deb) through GitHub Releases. The Windows installer is fully
self-contained: it bundles the complete Qt 6 runtime (platform plugins, WebEngine
renderer process and resources, ICU data, V8 snapshots), a Python runtime, the VC++
runtime, Chinese fonts and the Rust native core, so it runs on a machine with no
preinstalled software or dependencies.

All binaries are built by GitHub Actions from the public repository, from the tagged
commit only. The build does not reuse cached build artifacts, and each release
publishes a SHA-256 checksum. The repository contains the full corresponding source,
build scripts, automated tests (Rust unit tests and pure-logic Python tests), a
privacy policy and a code signing policy.
```

### 1.3 Reputation

> ⚠️ **必须诚实陈述**。夸大或虚构使用数据会导致申请被直接拒绝，且基金会会
> 核对仓库真实状态。下面的内容与仓库当前实际状态一致。

```
YcBrowser is a newly public open-source project; its first public release was
v1.1.13 in November 2026. It does not yet have significant external adoption, and
the repository currently has no stars, forks or third-party contributions. This
project is submitted at the start of its public life.

Evidence of quality and transparency that does exist today:
- MIT license (OSI approved), with a full third-party component and license notice
- All binaries are produced by GitHub Actions from tagged commits; build logs are
  public and every release publishes a SHA-256 checksum
- Automated tests run in CI: Rust unit tests for the native core, plus pure-logic
  Python tests for translation segmentation, settings, bookmarks and UI geometry
- A written privacy policy, a written code signing policy, and documented known
  boundaries in the README (available in both Chinese and English)
- The Windows installer is verified for runtime completeness (Qt plugins, WebEngine
  resources, PE dependency closure) by an automated bundle verification script
- The `main` branch is protected: changes land through pull requests and must pass
  the CI check, so build scripts and CI configuration are reviewed source
- A manifest for the official Windows Package Manager (winget) has been submitted to
  microsoft/winget-pkgs (pull request #479246), giving the project a first
  distribution channel beyond GitHub Releases
```

---

## 二、维护者信息 🔒（本人填写）

| 字段 | 是否必填 | 说明 |
|---|---|---|
| **First Name** | 必填 | 本人名字 |
| **Last Name** | 必填 | 本人姓氏 |
| **Email** | 必填 | 用于接收审核通知，**必须能正常收信** |
| **Company Name** | 选填 | 个人维护者**留空**（留空不影响审核） |
| **Primary Discovery Channel** | 必填 | 诚实选择实际接触 SignPath 的渠道 |
| **Exact discovery source** | 选填 | 填写实际来源，如 `Web search`、`GitHub`、`Friend's recommendation` |

> ⚠️ `Primary Discovery Channel` 与 `Exact discovery source` 要求**如实填写**。
> 若此前通过 AI 助手或搜索得知，请照实写。

---

## 三、声明与提交

| 字段 | 操作 |
|---|---|
| **Code of Conduct consent** | ⚠️ **本人阅读 <https://signpath.org/terms> 后亲自勾选**。不得预先勾选或自动化提交 |
| **Other communications** | 不勾选（除非明确希望接收营销邮件） |
| **reCAPTCHA** | 本人手动完成 |

**提交顺序**：

1. 先完成 [05-signpath-application.md](05-signpath-application.md) 中的
   「步骤 2.5 申请前必做的准备」（尤其 winget 收录与技术文章）
2. 确认仓库已有 **Release**（至少 v1.1.13）
3. 确认 GitHub 账号已启用 MFA，且仓库要求贡献者启用 MFA
4. 打开 <https://signpath.org/apply>，按本文件逐项填写
5. 亲自阅读条款并勾选 Code of Conduct consent
6. 亲自完成 reCAPTCHA 并提交
7. 记录提交确认信息与申请状态

---

## 四、审阅者会核对的要点

| 核对项 | 本项目落实位置 |
|---|---|
| OSI 认可许可证 | [LICENSE](../LICENSE)（MIT，含第三方组件声明） |
| 仓库公开 | <https://github.com/yljlpc/YcBrowser> |
| 有已发布版本 | <https://github.com/yljlpc/YcBrowser/releases> |
| 下载页描述了功能 | [README.md](../README.md) 的「功能特性」「安装」章节 |
| 字面文字 "Code signing policy" | [CODE_SIGNING_POLICY.md](../CODE_SIGNING_POLICY.md) |
| 字面句 "Free code signing provided by SignPath.io, certificate by SignPath Foundation." | 同上文件首段 |
| Author / Reviewer / Approver 角色与成员 | 同上文件「团队角色」表（当前均为 `@yljlpc`） |
| 隐私政策 | [PRIVACY.md](../PRIVACY.md) |
| 可信构建系统 | [.github/workflows/build-windows.yml](../.github/workflows/build-windows.yml) |
| 无缓存复用构建产物 | 工作流只缓存 cargo 依赖下载，不缓存 `core/target` |
| 产物元数据一致 | NSIS `VIAddVersionKey` + PyInstaller `--version-file`，版本单一来源 `src/version.py` |
| 每次发布人工批准 | SignPath approver 角色 + `release-signing` 策略 |

---

## 五、获批后的控制台配置（速查）

1. **注册 SignPath 账号** → 立即启用 MFA
2. **添加可信构建系统**：`Project → Trusted Build Systems → Add → GitHub.com`
   → 选择 `yljlpc/YcBrowser` → 授权
3. **创建产物配置（Artifact Configuration）**
   ```
   Name:  windows-installer
   Root Element: ZIP
   PE Files:
     - Path: YcBrowser-1.1.13-setup.exe
       Product Version: 1.1.13
   ```
4. **创建签名策略（Signing Policy）**
   ```
   Name: release-signing
   Type: Authenticode
   Artifact Configuration: windows-installer
   Approval: Required（必须人工批准）
   Timestamping: Trusted
   ```
5. **创建 API Token**：`My Profile → API Tokens → Create API Token`
   → Permissions 选 `Submitter` → **只显示一次，立即保存**
6. **配置 GitHub Secrets 与 Variable**（见 §步骤 6 于 05 文档）
7. **重新打 tag 触发签名**
   ```bash
   git tag v1.1.14 -m "..."
   git push origin v1.1.14
   ```
8. **在 SignPath 面板批准签名请求** → CI 自动回传签名产物并发布 Release
9. **验证**
   ```powershell
   Get-AuthenticodeSignature "YcBrowser-1.1.14-setup.exe" | Format-List
   # 期望：Status = Valid，SignerCertificate.Subject 含 SignPath Foundation
   ```

---

## 六、如果被拒

SignPath Foundation 允许在积累足够外部可见度后再次申请。官方在 2026 年 10 月
的案例中给出的拒绝理由是 *"for lack of public visibility, not for quality"*。

因此若被拒，**不是代码质量问题**，按下列顺序补强后重新提交：

1. winget 收录被合并
2. 至少一篇第三方视角的技术文章
3. 积累 20+ stars 或若干外部 Issue / PR
4. 持续发版并保持 Issue 响应

同时可启用 [05-signpath-application.md](05-signpath-application.md) 第五节的
付费回退方案（SSL.com IV 证书 / Certum）。
