# Windows 代码签名指南（Yc浏览器）

本文说明 Windows 发布产物的 Authenticode 签名机制、开源项目的三条可行路线，
以及本项目的推荐落地方式。

---

## 一、先说结论

> **「通过微软签名」有三条路，优先级如下：**

| 路线 | 成本 | 适用 | 私钥位置 | 关键限制 |
|---|---|---|---|---|
| **SignPath Foundation** | 免费 | OSI 开源许可证项目 | SignPath 的 HSM | 证书签发给 SignPath Foundation，发布者显示 "SignPath Foundation"；需人工审批；需 GitHub 公开仓库 + CI 自动化构建 |
| **微软 Artifact Signing**（原 Trusted Signing） | 约 $9.99/月 | 商业软件分发 | 微软云端，永不出域 | Public Trust 目前只开放美国、加拿大个人开发者；组织有另一份地区名单，**当前不含中国大陆**；身份验证需法律文件、人工审核 |
| **商业 OV/EV 证书**（DigiCert / Sectigo / GlobalSign / SSL.com IV） | 数百～数千美元/年 | 需要自有企业身份 | 硬件令牌或云签名 | 2023 年起 CA/B Forum 强制私钥硬件存储；**EV 已不再是 SmartScreen 即时豁免条件** |

**对 Yc浏览器 的建议**：先走 **SignPath Foundation**（免费、专为开源设计），
若因地区或审批不通过，再评估商业 OV 证书（IV 类型可签个人身份，无需公司主体）。

---

## 二、签名到底解决什么问题

Authenticode 签名做两件事：

1. **绑定发布者身份** —— Windows 显示"已验证的发布者"，而不是"未知发布者"。
2. **防篡改** —— 签名后文件任何一字节被改动，签名立即失效。

**它不做什么**（这是最常见的误解）：

- ❌ 不保证软件没有病毒 / 没有 bug
- ❌ 不保证 SmartScreen 不弹窗 —— SmartScreen 靠的是**文件下载信誉**，需要积累
  干净的下载量，与签名有效性是两套独立机制
- ❌ 不保证企业环境（AppLocker / WDAC）放行

> Windows 官方明确说明：**OV 证书和 Artifact Signing 都需要 SmartScreen 信誉积累**。
> 不要为了"保证立即无提示"而购买 EV 证书。

---

## 三、真实案例：开源项目是怎么做的

### 案例 1：SignPath Foundation（免费路线，最值得抄）

**官方项目**（SignPath 官网列出的已获支持项目）：

| 项目 | 做法 |
|---|---|
| **7-Zip** | SignPath Foundation 证书 |
| **Inkscape** | SignPath Foundation 证书 |
| **GIMP** | SignPath Foundation 证书 |
| **Flameshot** | SignPath Foundation 证书 |
| **Git Extensions** | SignPath Foundation 证书 |
| **Stellarium** | SignPath Foundation 证书 |
| **NETworkManager** | SignPath.io 免费服务 + Foundation 证书 |
| **Super Productivity** | 发布者显示 "SignPath Foundation"，SHA256 + 时间戳 |

**工作原理**：

```
GitHub Actions 构建 → 上传未签名产物 → SignPath 提交签名请求
    → SignPath 核验「二进制确实来自你的公开仓库」→ 人工审批
    → SignPath HSM 用其证书签名 → 签名产物回传 → 发布
```

**核心价值**：证书签发给 **SignPath Foundation**，而不是签发给你个人。
SignPath 通过核验"这个二进制是不是从你仓库构建出来的"来背书 ——
这解决了开源项目的根本痛点：证书通常签发给个人/企业，用户无法验证软件来自源码仓库。

**申请条件**（全部满足才可能获批）：

- OSI 认可的开源许可证（不允许双许可）
- 无恶意软件 / 潜在不受欢迎程序
- 项目仍在积极维护
- 已有至少一个已发布版本
- 下载页有功能说明
- GitHub 与 SignPath 账号**都**启用 MFA
- 构建流程完全自动化
- 签名请求需人工审批（不能全自动放行）

**本项目落地要点**：
- 当前仓库**不是 git 仓库**（无 `.git`）→ SignPath 的"可信构建系统"无法接入，**必须先 `git init` 并推到 GitHub**
- 需安装 SignPath GitHub App 并配置 API Token（4 个 Secret）
- 产物必须是 PE 格式（本项目产 `.exe`，符合）

### 案例 2：Azure Artifact Signing（微软自己的云签名服务）

**参考实现**：`usetrmnl/trmnl-remarkable` 项目的 `docs/code-signing.md` 是很完整的范本。

配置矩阵：

| 类型 | 变量名 | 位置 |
|---|---|---|
| Account URI | `AZURE_SIGNING_ENDPOINT` | Repository **Variable** |
| Trusted Signing 账户名 | `AZURE_SIGNING_ACCOUNT` | Repository **Variable** |
| 证书配置文件名 | `AZURE_SIGNING_PROFILE` | Repository **Variable** |
| Entra 租户 ID | `AZURE_TENANT_ID` | Repository **Secret** |
| 应用注册 Client ID | `AZURE_CLIENT_ID` | Repository **Secret** |
| 订阅 ID | `AZURE_SUBSCRIPTION_ID` | Repository **Secret** |

要点：
- 用 **GitHub OIDC** 向 Azure 认证，**私钥永远不出现在 runner 或仓库里**
- 应用注册需授予 signing account 的 **Artifact Signing Certificate Profile Signer** 角色
- 需要 **federated credential**，其 subject 必须匹配仓库的 release environment
  → 所以工作流里必须声明 `environment: release`，删掉就认证失败
- 证书**短时效（数天）**，因此**时间戳是强制项**
- 身份验证需法律身份文件，**无法脚本化**

### 案例 3：商业 CA 证书（最传统的路线）

- **OV（Organization Validation）**：需企业主体；部分 CA 提供个人 IV 证书（SSL.com IV）
- **EV（Extended Validation）**：需更严格审核；可签驱动（需 WHQL）；**不再保证 SmartScreen 即时放行**
- CA/B Forum 2023 年 6 月起强制：**IV 私钥必须存于 FIPS 认证的硬件令牌或云签名服务**
- 公开代码签名证书**最长有效期约 459–460 天**（多年订阅 ≠ 一张证书能用多年）
- 中国大陆可用 CA：**Certum**（通过 SSLdun 授权）、**GDCA / 沃通**
  （后者提供微软官方推荐的代码签名证书，含 OV 与 EV）

### 案例 4：自签证书（仅限内部测试）

`usetrmnl/trmnl-remarkable` 在接入 Azure 之前就用自签证书发布了 2.2.1 及更早版本。

自签证书**能防篡改，但不获得公开信任**：
- 用户仍见"未知发布者" / SmartScreen 警告
- 每台测试机需手动信任该根证书
- 必须在发布包中附上 `.cer`（仅公钥）+ 指纹信息，供用户独立核验

---

## 四、本项目的签名工具

已实现 `tools/sign_windows.py`：

```bash
python tools/sign_windows.py check              # 检查 signtool 与证书就绪度
python tools/sign_windows.py selfsign           # 生成自签证书（本机测试用）
python tools/sign_windows.py sign <file.exe>    # 签名 + SHA256 + RFC3161 时间戳
python tools/sign_windows.py verify <file.exe>  # 验证签名
```

签名命令等价于：

```powershell
signtool sign /f cert.pfx /p <密码> /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 app.exe
```

**时间戳不可省略**：CA/B Forum 要求代码签名必须带 RFC3161 时间戳，
否则证书过期后签名立即失效，时间戳能让签名在证书过期后依然有效。

---

## 五、本机环境的特殊障碍（重要）

**这台机器启用了 WDAC（Windows Defender Application Control）企业签名级别强制**：

```
CodeIntegrityPolicyEnforcementStatus: 2
UserModeCodeIntegrityPolicyEnforcementStatus: 2
Policy ID: {0283ac0f-fff1-49ae-ada1-8a933130cad6}
```

后果：

| 文件 | 签名状态 | 结果 |
|---|---|---|
| `Qt6Core.dll` | **Valid**（The QT Company Oy） | ✅ 允许加载 |
| `QtCore.pyd` | **NotSigned** | ❌ 被策略拦截 |

代码完整性日志（事件 3077）：
> Code Integrity determined that a process (...) attempted to load
> `...PyQt6\QtCore.pyd` that did not meet the **Enterprise signing level**
> requirements or violated code integrity policy.

**这恰恰说明了签名的价值**：在企业级 WDAC 强制策略下，
**未签名的二进制根本无法运行**。即使最终用户机器没有这���策略，
SmartScreen 的信誉机制也遵循同样的逻辑 —— 有签名的软件走"已验证发布者"通道。

### 应对方案

1. **正式发布**：向 Qt 官方申请对 `*.pyd` 的签名覆盖，或使用已签名的 Qt 官方发行包；
   最佳实践是**不在自建 wheel 上折腾**，直接用 Riverbank 官方 PyQt6 wheel
   （其 `.pyd` 是否签名取决于发行版，需实测）。
2. **本机开发**：把 PyQt6 安装到不受该策略约束的位置，或使用
   `python tools/verify_load.py` 之类的自检脚本确认加载状态。
3. **本项目现状**：打包链路本身**不依赖运行时加载 PyQt6** ——
   PyInstaller 在**构建时**把 `.pyd` 静态收集进产物，构建机上加载失败
   不影响打包，但**产物在受策略的机器上运行会被拦**。
   这一点必须在发布前实测验证。

---

## 六、给本项目的行动清单

**立即可做**：

- [x] 提供 `tools/sign_windows.py` 签名工具
- [ ] 安装 Windows SDK（提供 signtool）—— `winget install Microsoft.WindowsSDK`
- [ ] 生成本机自签证书做**流程验证**（明确告知用户：非公开信任）
- [ ] 在 CI 中加入签名步骤，把凭据走 GitHub Secrets / Azure OIDC

**发布前必做**：

- [ ] `git init` + 推到 GitHub（SignPath 的硬性前提）
- [ ] 确认许可证为 OSI 认可（MIT / Apache-2.0 均可，当前 Cargo.toml 写的是 MIT）
- [ ] 向 SignPath Foundation 提交申请（signpath.org/apply）
- [ ] 走 Windows SDK → 编译 → 签名 → 验证 的完整流水线

**长期**：

- [ ] 若 SignPath 审批不通过 → 评估 SSL.com IV（个人身份，无需公司）或 Certum / GDCA
- [ ] 监控 SmartScreen 信誉积累情况（干净下载量）

---

## 七、参考链接

- SignPath Foundation：https://signpath.org
- 微软 Artifact Signing：https://learn.microsoft.com/azure/trusted-signing/
- 微软 Authenticode 文档：https://learn.microsoft.com/windows/win32/seccrypto/
- SignPath 案例参考：https://super-productivity.com/code-signing/
- Azure OIDC 签名范本：https://github.com/usetrmnl/trmnl-remarkable/blob/main/docs/code-signing.md
- 中国大陆 CA 对比：https://www.trustauth.com.cn/zx/1098.html
