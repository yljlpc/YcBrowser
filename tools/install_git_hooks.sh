#!/usr/bin/env bash
# 安装 git hooks：提交时自动递增版本号。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p .git/hooks
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
# Yc浏览器：版本号随源码修改次数自动递增
exec python3 tools/auto_bump_version.py
HOOK
chmod +x .git/hooks/pre-commit
echo "已安装 pre-commit hook：$(pwd)/.git/hooks/pre-commit"
