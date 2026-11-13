#!/usr/bin/env bash
# ============================================================
# Yc浏览器 —— GitHub 公开仓库与 Release 发布脚本
#
# 用途：把本地仓库推送到公开 GitHub 仓库，并创建带安装包的 Release。
#       这一步是 SignPath Foundation 申请的前置条件（SignPath 要求
#       「项目已有至少一个公开发布版本」，且仓库必须公开）。
#
# 用法：
#   bash tools/publish_github.sh --repo yc-browser
#   bash tools/publish_github.sh --repo yc-browser --dry-run
#
# 前置条件：
#   1. 已安装 GitHub CLI：winget install --id GitHub.cli
#   2. 已完成认证：gh auth login
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPO_SLUG="yc-browser"
DRY_RUN=0
SKIP_RELEASE=0

while [ $# -gt 0 ]; do
    case "$1" in
        --repo) REPO_SLUG="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --skip-release) SKIP_RELEASE=1; shift ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
done

# ---------- 工具检查 ----------
if ! command -v gh >/dev/null 2>&1; then
    echo "✗ 未找到 gh（GitHub CLI）。请先执行：winget install --id GitHub.cli" >&2
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "✗ 未找到 git" >&2
    exit 1
fi

echo "=== 1/6 环境检查 ==="
gh --version | head -1
git --version

# ---------- 认证检查 ----------
echo ""
echo "=== 2/6 认证检查 ==="
if ! gh auth status >/dev/null 2>&1; then
    echo "✗ GitHub CLI 未认证。请先执行："
    echo "    gh auth login"
    echo "  （选择 GitHub.com → HTTPS → 浏览器登录；SignPath 要求账号启用 MFA）"
    exit 1
fi
GH_USER="$(gh api user --jq .login)"
echo "已认证账号: $GH_USER"

# ---------- 版本号 ----------
VERSION="$(grep 'VERSION' src/version.py | cut -d'"' -f2)"
echo "当前版本: $VERSION"

# ---------- 待推送内容核对 ----------
echo ""
echo "=== 3/6 待推送内容核对 ==="
if [ -n "$(git status --porcelain)" ]; then
    echo "检测到未提交的改动："
    git status --short
    echo "→ 先提交再发布（保持 Release 与源码版本一致）"
    if [ "$DRY_RUN" -eq 0 ]; then
        read -r -p "是否现在提交？(y/N) " ans
        if [ "${ans:-N}" = "y" ] || [ "${ans:-N}" = "Y" ]; then
            git add -A
            git commit -m "chore: 发布前同步 v${VERSION}"
        fi
    fi
fi

echo "待推送文件数: $(git ls-files | wc -l)"
echo "其中敏感文件检查："
if git ls-files | grep -qiE '\.(pfx|p12|pem|key)$|(^|/)\.env$'; then
    echo "✗ 发现疑似敏感文件，中止推送："
    git ls-files | grep -iE '\.(pfx|p12|pem|key)$|(^|/)\.env$'
    exit 1
fi
echo "  ✓ 无证书/私钥/密钥文件入库"

# ---------- 创建仓库 ----------
echo ""
echo "=== 4/6 创建/关联公开仓库 ==="
TARGET_REPO="${GH_USER}/${REPO_SLUG}"
if gh repo view "$TARGET_REPO" >/dev/null 2>&1; then
    echo "仓库已存在: https://github.com/$TARGET_REPO"
else
    echo "将创建公开仓库: https://github.com/$TARGET_REPO"
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "  [dry-run] 跳过实际创建"
    else
        gh repo create "$TARGET_REPO" \
            --public \
            --description "Yc浏览器 —— 多引擎浏览器（Blink / WebKit / Trident 兼容），Rust 原生核心 + PyQt6 前端，支持实时翻译与多线程高速下载" \
            --source . \
            --remote origin \
            --push
        echo "✓ 仓库已创建并完成首次推送"
    fi
fi

# ---------- 关联远端（dry-run 或仓库已存在的情况）----------
if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "https://github.com/$TARGET_REPO.git"
    echo "已添加远端 origin"
fi

if [ "$DRY_RUN" -eq 0 ]; then
    echo "推送 main 分支..."
    git push -u origin main
fi

# ---------- Release ----------
echo ""
echo "=== 5/6 创建 Release ==="
if [ "$SKIP_RELEASE" -eq 1 ]; then
    echo "  [跳过] --skip-release 已指定"
else
    TAG="v${VERSION}"
    echo "Tag: $TAG"

    # 收集要上传的安装包
    ARTIFACTS=()
    for f in installer/YcBrowser-${VERSION}-setup.exe \
             "package/omnibrowser_${VERSION}_amd64.deb" \
             "package/omnibrowser-deepin_${VERSION}_amd64.deb"; do
        [ -f "$f" ] && ARTIFACTS+=("$f")
    done

    if [ "${#ARTIFACTS[@]}" -eq 0 ]; then
        echo "⚠️ 未找到 ${VERSION} 的安装包，跳过 Release"
    else
        echo "待上传产物："
        for a in "${ARTIFACTS[@]}"; do
            printf "  - %s  (%.1f MB)\n" "$a" "$(echo "scale=1; $(stat -c%s "$a" || stat -f%z "$a")/1048576" | bc)"
        done

        if [ "$DRY_RUN" -eq 1 ]; then
            echo "  [dry-run] 跳过实际发布"
        else
            # 创建 tag
            git tag -a "$TAG" -m "发布 $TAG" 2>/dev/null || echo "  (tag 已存在，跳过创建)"
            git push origin "$TAG" 2>/dev/null || echo "  (tag 推送跳过)"

            NOTES=$(cat <<EOF
## Yc浏览器 ${VERSION}

多引擎浏览器：Blink / WebKit / Trident 兼容档位，Rust 原生核心 + PyQt6 前端。

### 本次发布

- Windows 安装包（NSIS）
- Linux deb 包（openKylin / deepin 双变体）

### 特性

- 多引擎兼容：可切换 Blink / WebKit / Trident 兼容档位
- 实时翻译：MyMemory / Google / LibreTranslate / 自定义端点
- 多连接分片高速下载引擎
- 分辨率 / DPI 自适应、多标签、无痕模式、下载管理、媒体嗅探

### 安装

\`\`\`bash
# Linux
sudo apt install ./omnibrowser-${VERSION}_amd64.deb

# Windows —— 运行 YcBrowser-${VERSION}-setup.exe
\`\`\`

### 代码签名

Windows 安装包为**自签名**（仅用于开发验证，Windows 会提示「未知发布者」）。
正式发布将接入 SignPath Foundation 免费开源签名。

许可证：MIT
EOF
)
            gh release create "$TAG" \
                --title "Yc浏览器 ${VERSION}" \
                --notes "$NOTES" \
                "${ARTIFACTS[@]}" || echo "⚠️ Release 创建失败（可手动执行 gh release create）"
        fi
    fi
fi

# ---------- 收尾 ----------
echo ""
echo "=== 6/6 下一步 ==="
cat <<EOF
仓库地址: https://github.com/$TARGET_REPO

接下来去申请 SignPath 免费签名：
  1. 打开 https://about.signpath.io/apply
  2. 选择 "Open Source" 类别，填写仓库地址
  3. 说明项目用途（浏览器发行版），并附上本仓库链接
  4. 若需立即发布，可附上上述 Release 的链接作为「已有发布版本」证明
  5. 提交后等待基金会审核（通常数个工作日）

同时务必：
  ✓ 在 GitHub 账号设置里启用两步验证（MFA）—— SignPath 强制要求
  ✓ 在 SignPath 账号同样启用 MFA
EOF
