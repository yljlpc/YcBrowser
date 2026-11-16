#!/usr/bin/env bash
# ============================================================
# Yc浏览器 —— GitHub 推送助手（引导式）
#
# 本脚本负责：检查环境 → 引导获取 PAT → 安全输入 → 执行推送与 Release。
# PAT 不会出现在命令行历史里（用 read -s 读取）。
#
# 用法：
#   bash tools/publish_release.sh
#   bash tools/publish_release.sh --repo owner/name
#   bash tools/publish_release.sh --skip-release    # 只推代码
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPO="yljlpc/YcBrowser"
SKIP_RELEASE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --repo) REPO="${2:?}"; shift 2 ;;
        --skip-release) SKIP_RELEASE=1; shift ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
done

cat <<BANNER
================================================================
  Yc浏览器 —— GitHub 推送助手
================================================================
  仓库：${REPO}
  需要一个 GitHub Personal Access Token（PAT）。

  获取方式（任选其一）：
    A) classic token
       https://github.com/settings/tokens/new
       → 勾选 repo scope → 生成后立即复制（ghp_ 开头）
    B) fine-grained token
       https://github.com/settings/personal-access-tokens/new
       → 仅选本仓库 → Contents: Read and write
                        Actions:  Read and write

  令牌只会保存在本机 ~/.git-credentials（权限 600），
  不会出现在命令行历史里。
================================================================
BANNER

echo
printf "请粘贴 PAT（输入不回显，直接粘贴后回车）："
read -r -s PAT
echo
if [ -z "$PAT" ]; then
    echo "✗ 未输入令牌，已中止。" >&2
    exit 1
fi

ARGS=(--token "$PAT" --repo "$REPO")
[ "$SKIP_RELEASE" = "1" ] && ARGS+=(--skip-release)

bash tools/sync_github.sh "${ARGS[@]}"

# 清理 shell 变量中的令牌
unset PAT
