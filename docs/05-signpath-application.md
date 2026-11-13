# SignPath Foundation 免费签名申请指南

> 目标：为零成本获得 Windows Authenticode 公开受信任签名，
> 让 Yc浏览器 的安装包不再显示「未知发布者」，并消除 SmartScreen 干扰。
>
> 本文件是**可执行的申请清单** —— 按顺序做，每步都有明确的完成标准。

---

## 一、结论先行

SignPath Foundation 是**目前唯一专门为开源项目提供免费、公开受信任
Windows 代码签名**的方案。已获支持的项目包括：

**7-Zip · Inkscape · GIMP · Flameshot · Git Extensions · Stellarium ·
NETworkManager · Super Productivity · KoriyoZIP** 等。

它的核心机制与商业 CA 完全不同：

| | 商业 CA | SignPath Foundation |
|---|---|---|
| 证书签发给谁 | **你个人 / 你的公司** | **SignPath Foundation** |
| 用户看到的发布者 | 你的名字 | "SignPath Foundation" |
| 私钥在哪 | 你的硬件令牌 | **SignPath 的 HSM**（永不出域） |
| 如何证明二进制可信 | 无法证明来自源码 | **SignPath 核验构建来自你的公开仓库** |

也就是说，**SignPath 用"我为这个仓库背书"替代了"我为这个人背书"** ——
这正是开源项目获得公开信任的唯一可行路径。

---

## 二、申请前置条件（全部必须满足）

SignPath Foundation 的官方资格要求：

- [x] **OSI 认可的开源许可证**（不允许双许可）→ 本项目用 **MIT** ✅ 已就绪
- [x] **无恶意软件 / 无潜在不受欢迎程序** ✅
- [x] **项目仍在积极维护** ✅
- [x] **已有至少一个已发布版本**（以可签名的形式）→ v1.1.14 Release 已发布（<https://github.com/yljlpc/YcBrowser/releases/tag/v1.1.14>）
      <https://github.com/yljlpc/YcBrowser/releases> ✅
- [x] **下载页有功能说明** → 已建 [README.md](../README.md)（中英双版本）✅
- [x] **GitHub 仓库公开** → <https://github.com/yljlpc/YcBrowser> ✅ 已完成
- [x] **构建流程完全自动化** → 已建 [.github/workflows/build-windows.yml](../.github/workflows/build-windows.yml) ✅
- [x] **无专有非开源组件** → 已将随包方正商业字体（21 个 / 192MB）替换为
      **思源宋体 Noto Serif SC（OFL 1.1）** ✅
- [x] **构建脚本与 CI 配置纳入代码评审** → `main` 分支保护已启用 ✅
- [x] **官方分发渠道** → GitHub Releases + winget 收录 PR
      <https://github.com/microsoft/winget-pkgs/pull/479246> ✅
- [ ] **GitHub 与 SignPath 账号均启用 MFA** ← 待完成（需账号持有人操作）
- [ ] **SignPath 账号有 API Token**（Submitter 权限）← 获批后在控制台创建
- [ ] **仓库已开启 2FA 要求**（要求所有贡献者启用 MFA）← 待完成
- [ ] **可见度信号**（stars / 外部贡献 / 独立文章）← 待积累，见下方 §步骤 2.5

> 📋 **逐字段表单答案**：见 [docs/07-signpath-form-answers.md](07-signpath-form-answers.md)
> —— 该文件按 signpath.org/apply 的真实字段逐条给出可直接粘贴的答案。
> ⚠️ **可见度是最大的不确定因素**，见下文「申请前必做的准备」。

---

## 三、逐步操作

### 步骤 1：初始化 Git 仓库并推到 GitHub ✅ 已完成

仓库已初始化并推送到公开 GitHub 仓库：

```
https://github.com/yljlpc/YcBrowser
```

- 分支：`main`（8+ 次提交，含完整构建链路与签名策略）
- 标签：`v1.1.14`（指向 `c13099c`，含启动与安装性能优化）
- 工作区干净，无构建产物入库

### 步骤 2：清理不应入库的产物 ✅ 已完成

已写入 [.gitignore](../.gitignore)，实际入库 **98 个文件 / 约 1.3 MB**：

- 排除：`/dist/`、`/build/`、`*.spec`、`/installer/*.exe`、`/installer/*.pfx`、
  `/core/target/`、`/_stage/`、`package/` 下的产物、`__pycache__` 等
- 保留：`LICENSE`、`README.md`、`docs/`、`.github/workflows/`、`src/`、
  `core/src/`、`installer/*.py`、`installer/*.nsi`、`tools/`、`assets/`、
  `CODE_SIGNING_POLICY.md`、`PRIVACY.md`

> 这些正是 SignPath 审阅的对象，缺一不可。

### 步骤 2.5：申请前必做的准备（决定成败的一步）

> ⚠️ **这是本项目目前最大的风险点，务必正视。**
>
> 2026 年 10 月有一个公开案例：某开源项目（piscout）提交 SignPath
> Foundation 申请后被 **Declined**，官方理由是
> **"for lack of public visibility, not for quality"** ——
> 即项目质量没问题，而是**没有足够的外部可见度信号**。
>
> 基金会考察的不是代码写得好不好，而是**"这是一个有人在用的真实项目吗"**。

基金会通常看重的信号：

| 信号 | 说明 | 本项目现状 |
|---|---|---|
| GitHub Stars / Forks | 最基础的社区认可度 | ⬜ 目前为 0，需要积累 |
| 外部贡献者 | 非作者本人提交的 PR / Issue | ⬜ 无 |
| 独立第三方讨论 | 非作者撰写的文章、Reddit / Stack Overflow / 社区帖子 | ⬜ 无 |
| 机构或组织背书 | 被某个开源组织收录、赞助、推荐 | ⬜ 无 |
| 持续活跃 | 多个版本、规律更新、Issue 有响应 | ✅ v1.1.13 / v1.1.14，CI 持续构建 |
| 发行渠道分发 | 被 winget / Chocolatey 等官方仓库收录 | ✅ winget 收录 PR 已提交（microsoft/winget-pkgs#479246，待维护者合并） |

**申请前能立刻做的（不需要等用户量）**：

1. **提交 winget manifest** ✅ **已完成** —— PR 已提交至
   <https://github.com/microsoft/winget-pkgs/pull/479246>。
   清单文件在仓库 `winget/manifests/y/YcBrowser/YcBrowser/1.1.14/` 下，
   用 `tools/gen_winget_manifest.py`（生成）与 `tools/submit_winget_manifest.py`
   （提交）可重复执行。收录后即成为微软官方分发渠道。
2. **写一篇技术文章** —— 介绍 Rust 核心 + PyQt6 + QtWebEngine 的打包与
   完全独立交付实践（解决 WDAC 拦截、Qt 插件缺失、离线安装包体积控制等），
   发到掘金 / 知乎 / CSDN / Reddit r/Python / Hacker News。
   **必须是第三方视角的真实技术内容**，不得伪装成独立推荐。
3. **持续发版并回复 Issue** —— 保持提交节奏与 Issue 响应本身就是活跃度证据。
4. **完善 README 英文版** ✅ **已完成** —— 见
   [README.en.md](https://github.com/yljlpc/YcBrowser/blob/main/README.en.md)，
   降低国际审阅者的理解成本与「仅面向国内用户」的顾虑。

**申请时机建议**：完成上述 1、2 项后再提交，一次通过率显著更高。
若被拒，官方允许在积累起足够可见度后再次申请。

### 步骤 3：启用 MFA

- **GitHub**：Settings → Password and authentication → Enable MFA（必做，SignPath 强制要求）
- **SignPath**：注册后立即在账号设置中启用 MFA

### 步骤 4：提交申请

1. 访问 <https://signpath.org/apply>
2. 填写项目信息：
   - **项目名**：Yc浏览器 / YcBrowser
   - **仓库 URL**：你的 GitHub 公开仓库地址
   - **许可证**：MIT
   - **构建系统**：GitHub Actions
   - **产物类型**：Windows PE 可执行文件（`.exe`）
   - **项目描述**：粘贴 README 的功能特性段落
3. 提交后等待审核（**通常数个工作日**）

审核关注点：
- 许可证是否 OSI 认可
- 项目是否真实可用、有实际功能
- 是否有可疑行为（挖矿、捆绑、灰色地带功能）
- 仓库历史是否健康

### 步骤 5：配置 SignPath 面板

获批后会拿到 **Organization ID** 与 **Project Slug**。登录 <https://app.signpath.io>：

**5.1 添加可信构建系统**

```
Project → Trusted Build Systems → Add → GitHub.com
→ 选择你的仓库 → 授权
```

**5.2 配置产物格式（Artifact Configuration）**

SignPath 需要知道产物里哪个文件是 PE 可执行文件：

```
Configuration Name: windows-installer
Root Element: ZIP
PE Files:
  - Path: YcBrowser-<version>-setup.exe
    Product Version: 1.1.14
```

> 若 GitHub 上传的是 ZIP 包裹，需在此声明 ZIP 内部结构；
> 若直接上传 exe，则 Root Element 选 `PE`。

**5.3 创建 API Token**

```
My Profile → API Tokens → Create API Token
  Name: "GitHub Actions"
  Permissions: Submitter
```

**Token 只显示一次**，立刻保存。

### 步骤 6：配置 GitHub Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret：

| Secret 名称 | 值 | 来源 |
|---|---|---|
| `SIGNPATH_API_TOKEN` | 上一步保存的 Token | SignPath 面板 |
| `SIGNPATH_ORGANIZATION_ID` | 组织 ID | SignPath 面板 URL 或设置页 |
| `SIGNPATH_PROJECT_SLUG` | 项目 slug | SignPath 面板 URL |
| `SIGNPATH_SIGNING_POLICY_SLUG` | 通常为 `release-signing` | SignPath 面板 |
| `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` | 上一步的产物配置名 | SignPath 面板 |

另需设置一个**仓库变量**（Repository Variables，非 Secret）作为总开关：

| 变量名 | 值 | 说明 |
|---|---|---|
| `SIGNPATH_ENABLED` | `true` | 不设或非 `true` 时签名步骤整体跳过 |

> Repository → Settings → Secrets and variables → **Actions** →
> `New repository secret` 与 `New repository variable` 两个页签分别添加。
>
> **为什么需要开关**：`secrets` context 不能直接用于 `if` 条件表达式，
> 工作流因此把签名配置提升为 **job 级 `env`**，再用 `vars.SIGNPATH_ENABLED`
> 作为显式开关 —— 这样在还没获批、secrets 为空时，签名步骤会干净跳过，
> 而不会因为读不到 secret 报错。

> ⚠️ **GitHub Action 名称必须是** `SignPath/github-action-submit-signing-request@v3`。
> 早期版本误用的 `signpath/signpath-action` **仓库并不存在**，会导致整个
> workflow 在「准备 action」阶段就失败 —— **即使该步骤被 `if` 跳过**，
> 因为 GitHub 会在 job 开始前预下载所有 `uses:` 引用的 action。
> 这一点已在本项目实际踩坑并修复。

### 步骤 7：触发签名

```bash
git tag v1.1.14
git push origin v1.1.14
```

CI 会自动：构建 → 上传产物 → 提交签名请求 → **等待你在 SignPath 面板人工审批** → 签名 → 回传。

**人工审批是强制环节**，SignPath 不会自动放行 —— 这是它的安全设计。

### 步骤 8：验证

```powershell
Get-AuthenticodeSignature "YcBrowser-1.1.14-setup.exe" | Format-List
```

应显示：

```
Status              : Valid
SignerCertificate   : CN=SignPath Foundation, ...
```

或图形界面：右键 exe → 属性 → 数字签名 → 显示 **"SignPath Foundation"**。

---

## 四、SignPath 不解决什么

**SmartScreen 信誉（SmartScreen Reputation）**

即使签名有效，SmartScreen 仍可能弹窗"Windows 已保护你的电脑" ——
这是**下载量信誉**机制，与签名有效性是两套独立的东西。

- 新证书从零开始积累
- 干净的下载量积累后，提示会逐渐消失
- **EV 证书也不再保证即时放行** —— 微软已明确说明 OV 与 Artifact Signing
  都需要积累信誉

**唯一的加速手段**：让更多用户从官方渠道下载，积累干净的下载记录。

**其他限制**：
- 证书签发给 SignPath Foundation，用户看到的发布者不是"Yc浏览器"
- 签名请求必须人工审批，无法完全无人值守
- 私有/闭源版本不在支持范围内（只签公开仓库的构建产物）

---

## 五、如果 SignPath 审批不通过

按优先级回退：

### 5.1 SSL.com IV Code Signing（个人身份，无需公司）

- **IV（Individual Validation）** 证书 —— 不需要注册公司，验证个人身份证件即可
- 约 $60–$100/年
- 私钥通过 FIPS 认证 USB 令牌或云签名服务（eSigner for Code）保存
- 签发快（验证通过后数分钟）
- 这是目前**唯一的国际品牌、可签个人身份**的代码签名证书

```bash
# 用 eSigner 或令牌导出 PFX 后
python tools/sign_windows.py sign setup.exe --pfx cert.pfx --password <密码>
```

### 5.2 Certum / GDCA（中国大陆可申请）

- **Certum**：欧洲 CA，通过国内授权商 SSLdun 提供
- **GDCA（沃通）**：国内 CA，代码签名证书由微软官方推荐的 CA 签发
- 均需企业主体（个人证书支持有限）

### 5.3 自签证书（仅内部测试用）

已在本机验证可行：

```bash
python tools/sign_windows.py selfsign
python tools/sign_windows.py sign setup.exe --pfx installer/yc-signing.pfx --password ycbuild
```

**自签证书能防篡改，但不获得公开信任** —— 用户仍见"未知发布者"。
仅适用于内部测试机（手动信任根证书）。

---

## 六、本机环境的一个特殊事实

这台构建机启用了 **WDAC 企业签名级别强制**：

```
CodeIntegrityPolicyEnforcementStatus: 2
UserModeCodeIntegrityPolicyEnforcementStatus: 2
Policy ID: {0283ac0f-fff1-49ae-ada1-8a933130cad6}
```

实测结果：

| 文件 | 签名状态 | 结果 |
|---|---|---|
| `Qt6Core.dll` | **Valid**（The QT Company Oy） | ✅ 允许加载 |
| `QtCore.pyd` | **NotSigned** | ❌ 被策略拦截 |

代码完整性日志（事件 3077）：
> Code Integrity determined that a process (...) attempted to load
> `...PyQt6\QtCore.pyd` that did not meet the **Enterprise signing level**
> requirements or violated code integrity policy.

**这恰恰证明了签名的价值**：在企业级策略下，**未签名的二进制根本无法运行**。

**对本项目的实际影响**：
- 打包链路本身**不受影响**（PyInstaller 在构建时静态收集 `.pyd`）
- 但产物在**受同等策略约束**的机器上运行会被拦
- PyQt6 的 `.pyd` 由 Riverbank 官方签名与否需实测；若未签名，
  受管终端（企业环境、WDAC 强制）将无法运行本应用
- 这也是**正式发布务必申请签名**的硬性理由

---

## 七、官方条款逐条对照（2026-11 核实）

来源：<https://www.signpath.org/terms>（该页标注为 Draft，以官网为准）

### A. 免费 OSS 订阅的资格条件

| 条款 | 本项目状态 |
|---|---|
| 不含恶意软件或潜在不受欢迎程序 | ✅ |
| 使用 OSI 认可的开源许可证，且**所有组件均无双许可** | ✅ MIT（见 [LICENSE](../LICENSE)） |
| 不含专有、非开源组件（System Libraries 除外） | ✅ 依赖均为开源（Qt6/LGPL、PyQt6/GPL、Rust crates/MIT+Apache、思源宋体/OFL）。**已移除随包的方正商业字体**（21 个 / 192MB），改用 SIL OFL 1.1 的思源宋体 |
| 项目仍在积极维护 | ✅ |
| **必须已以将要签名的形式发布过** | ⬜ 需先在 GitHub 创建 Release |
| 功能必须在下载页或应用商店条目中描述 | ✅ [README](../README.md) |
| 不得包含识别/利用安全漏洞或规避执行环境限制的功能 | ✅ 浏览器本体（DevTools 属标准浏览器功能） |
| 不得损害用户隐私与安全 | ✅ 见 [PRIVACY.md](../PRIVACY.md) |
| 未经警告不得修改用户系统配置 | ✅ 仅写安装目录与用户数据目录 |
| 提供安装功能的软件必须提供卸载说明 | ✅ NSIS 卸载程序 |

### B. 项目主页必须包含的内容（**逐字要求**）

SignPath 要求仓库主页含有：

- [x] 字面文字 **"Code signing policy"** → [CODE_SIGNING_POLICY.md](../CODE_SIGNING_POLICY.md)
- [x] 字面句子 **"Free code signing provided by SignPath.io, certificate by SignPath Foundation."**
      → 同上文件首段
- [x] 角色划分与成员列表（Author / Reviewer / Approver）→ 同上文件
- [x] 隐私政策链接 → [PRIVACY.md](../PRIVACY.md)

> ⚠️ 角色成员需填入真实 GitHub 用户名；**所有成员必须启用 MFA**。

### C. 构建要求（origin verification）

| 要求 | 本项目落实 |
|---|---|
| 二进制须以可验证方式构建自本仓库源码 | ✅ GitHub Actions 触发 |
| 构建配置来自源码控制，**不得**用 CI 界面临时覆盖 | ✅ 构建脚本全部入库 |
| **不得复用早期构建的缓存产物** | ✅ CI 只缓存 cargo 依赖下载，**不缓存 `core/target`** |
| 构建脚本与 CI 配置计为源码，需经评审 | ✅ 走 PR 评审流程 |
| 产物元数据正确：产品名匹配项目名、版本每次一致 | ✅ NSIS `VIAddVersionKey` + PyInstaller `--version-file`，版本取自 `src/version.py` |
| 每次发布需人工批准签名 | ✅ SignPath approver 角色 |

### D. 可签名的产物类型

SignPath 支持 Windows 可执行文件、MSI、CAB、APX/MSIX、**NuGet**、
**RPM**、**Debian 包**、OCI 镜像等。本项目的
`YcBrowser-<版本>-setup.exe` 与 `omnibrowser_*.deb` 均在支持范围内。

> 上游组件（Qt6 DLL 等）保留各自原有签名，不由本项目证书重签；
> 条款允许包含未签名的上游二进制，但保留未来收紧的权利。

---

## 八、参考资料

- SignPath Foundation 官网：<https://signpath.org>
- 申请入口：<https://signpath.org/apply>
- 控制台：<https://app.signpath.io>
- 文档：<https://about.signpath.io/documentation>
- **官方条款（资格条件）：<https://www.signpath.org/terms>**
- **GitHub Action（正确地址）：<https://github.com/SignPath/github-action-submit-signing-request>**
- 逐字段表单答案：[docs/07-signpath-form-answers.md](07-signpath-form-answers.md)
- 已签名项目参考：<https://super-productivity.com/code-signing/>
- Azure Artifact Signing（备选）：<https://learn.microsoft.com/azure/trusted-signing/>
- 微软 Authenticode：<https://learn.microsoft.com/windows/win32/seccrypto/>
