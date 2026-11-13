#!/usr/bin/env bash
# SignPath Foundation 申请准备脚本
#
# 一键完成申请前的前置工作：
#   1) 校验 SignPath 的硬性前提（许可证 / README / CI / git）
#   2) 初始化 git 仓库并做首次提交（若尚未初始化）
#   3) 生成申请材料清单，供填写 signpath.org/apply 表单时参考
#
# 用法：
#   bash tools/prepare_signpath.sh            # 检查 + 准备
#   bash tools/prepare_signpath.sh --check    # 只检查，不改动
#   bash tools/prepare_signpath.sh --init     # 只做 git 初始化与首次提交

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

MODE="prepare"
for arg in "$@"; do
  case $arg in
    --check) MODE="check" ;;
    --init)  MODE="init" ;;
  esac
done

info()  { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()  { echo -e "${YELLOW}[注意]${NC} $1"; }
fail()  { echo -e "${RED}[缺失]${NC} $1"; }
step()  { echo ""; echo -e "${YELLOW}==> $1${NC}"; }

SCORE=0
TOTAL=5

step "1/5 校验 SignPath 硬性前提"

# ① OSI 认可的开源许可证
if [ -f LICENSE ] && grep -q "MIT License" LICENSE; then
  info "LICENSE 存在且为 MIT（OSI 认可）"
  SCORE=$((SCORE+1))
else
  fail "缺少 LICENSE 或非 MIT —— SignPath 要求 OSI 认可的开源许可证"
fi

# ② 下载页功能说明
if [ -f README.md ] && [ $(wc -l < README.md) -gt 50 ]; then
  info "README.md 存在且内容完整（$(wc -l < README.md) 行）"
  SCORE=$((SCORE+1))
else
  fail "缺少 README.md 或内容过简 —— SignPath 要求下载页有功能说明"
fi

# ③ CI 自动化构建
if [ -d .github/workflows ]; then
  info "CI 配置存在：$(ls .github/workflows | tr '\n' ' ')"
  SCORE=$((SCORE+1))
else
  fail "缺少 .github/workflows —— SignPath 要求构建流程完全自动化"
fi

# ④ git 仓库
if [ -d .git ]; then
  info "git 仓库已初始化（分支：$(git rev-parse --abbrev-ref HEAD)）"
  SCORE=$((SCORE+1))
else
  fail "尚未初始化 git 仓库 —— SignPath 需要 GitHub 作为可信构建系统"
fi

# ⑤ SignPath 集成脚本
if grep -q "signpath" .github/workflows/*.yml 2>/dev/null; then
  info "CI 已接入 SignPath 签名步骤"
else
  warn "CI 中未检测到 SignPath 签名步骤（需在申请获批后配置 Secrets）"
fi

step "2/5 检查仓库卫生"

# 大目录不应入库
if git rev-parse --git-dir >/dev/null 2>&1; then
  TRACKED=$(git ls-files | wc -l)
  info "已跟踪文件：$TRACKED 个"
  BIG=$(git ls-files | grep -cE "^(package|_stage|core/target|dist)/" || true)
  if [ "$BIG" -eq 0 ]; then
    info "无构建产物入库（package/ _stage/ core/target/ 已排除）"
  else
    warn "有 $BIG 个构建产物被跟踪，建议检查 .gitignore"
  fi
fi

step "3/5 检查签名工具链"

if python tools/sign_windows.py check >/dev/null 2>&1; then
  info "signtool 与签名链路就绪"
else
  warn "签名工具链未完全就绪（不影响申请，本地验证可稍后处理）"
fi

if [ "$MODE" = "check" ]; then
  step "检查完成：$SCORE/$TOTAL 项前提满足"
  exit 0
fi

step "4/5 初始化 git 仓库"

if [ ! -d .git ]; then
  git init
  git branch -m main
  git config user.name "Yc Browser"
  git config user.email "yc@omnibrowser.local"
  git add -A
  git commit -m "Yc浏览器 v1.1.13 初始开源提交

多引擎浏览器：Rust 原生核心 + PyQt6/Qt6 前端。
Blink / WebKit / Trident 兼容档位，实时翻译，多连接分片下载。

许可证：MIT"
  info "git 仓库已初始化并完成首次提交"
else
  info "git 仓库已存在，跳过初始化"
fi

step "5/5 生成申请材料"

VERSION=$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' src/version.py | head -1)
DESC=$(sed -n '/^## 功能特性/,/^## 架构/p' README.md | head -20 | tr '\n' ' ')

cat <<EOF
════════════════════════════════════════════════════════════
  SignPath Foundation 申请材料（复制到 signpath.org/apply）
════════════════════════════════════════════════════════════

【项目名称】
Yc浏览器 / YcBrowser

【仓库 URL】
https://github.com/<你的账号>/yc-browser
  ⚠️ 必须先推送到 GitHub 公开仓库，命令：
     git remote add origin https://github.com/<你的账号>/yc-browser.git
     git push -u origin main

【许可证】
MIT

【构建系统】
GitHub Actions（见 .github/workflows/build-windows.yml）

【产物类型】
Windows PE 可执行文件 —— NSIS 安装包（YcBrowser-${VERSION}-setup.exe）

【项目版本】
${VERSION}

【项目描述】（粘贴到申请表）
${DESC}

【功能概述】
Yc浏览器 是一款以 Rust 原生核心 + PyQt6（Qt 6）构建的多功能桌面浏览器，
支持实时翻译与高速下载。主要特性：
· 多引擎兼容：Blink（默认）/ WebKit / Trident 兼容模式，每标签独立 profile
· 实时翻译：术语统一 + 口语化改写，多后端可切换
· 高速下载：多连接分片 + 动态再平衡 + 断点续传（移植 SwiftDL 算法内核）
· 分辨率 / DPI 自适应、多标签、无痕窗口、下载管理、媒体嗅探

【平台】
Windows 10/11 64 位（另有 Linux .deb 版本）

════════════════════════════════════════════════════════════
  申请后需在 GitHub Secrets 配置 4 个变量（详见 docs/05-signpath-application.md）：
    SIGNPATH_API_TOKEN / SIGNPATH_ORGANIZATION_ID
    SIGNPATH_PROJECT_SLUG / SIGNPATH_SIGNING_POLICY_SLUG
════════════════════════════════════════════════════════════
EOF

echo ""
echo -e "${GREEN}完成。下一步：${NC}"
echo "  1) 推送仓库到 GitHub（公开）"
echo "  2) 在 GitHub 与 SignPath 启用 MFA"
echo "  3) 前往 https://signpath.org/apply 提交申请"
echo "  4) 详见 docs/05-signpath-application.md"
