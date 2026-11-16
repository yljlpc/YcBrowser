#!/usr/bin/env bash
# ============================================================
# Yc浏览器 —— 一键推送源码到 GitHub 并创建 Release
#
# 用法：
#   bash tools/sync_github.sh --token <PAT>              # 推送代码 + 创建 Release
#   bash tools/sync_github.sh --token <PAT> --skip-release  # 只推代码
#   bash tools/sync_github.sh --check                    # 只做环境自检
#
# PAT 要求：classic token 需勾选 repo scope；
#           fine-grained token 需对 yljlpc/YcBrowser 授予 Contents:Read&Write
#           与 Actions:Read&Write（创建 Release 需要）。
#
# 说明：本机 git 走 gh-proxy.com 代理访问 GitHub（直连会被网络阻断），
#       因此 remote URL 必须是 https://gh-proxy.com/https://github.com/<repo>
#       且 git-credentials 里要有对应 host 的凭据条目。
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPO="yljlpc/YcBrowser"
REMOTE_PROXY="https://gh-proxy.com/https://github.com/${REPO}"
TOKEN=""
SKIP_RELEASE=0
CHECK_ONLY=0
RELEASE_NOTES=""

while [ $# -gt 0 ]; do
    case "$1" in
        --token) TOKEN="${2:?--token 需要 PAT}"; shift 2 ;;
        --repo) REPO="${2:?}"; REMOTE_PROXY="https://gh-proxy.com/https://github.com/${REPO}"; shift 2 ;;
        --skip-release) SKIP_RELEASE=1; shift ;;
        --check) CHECK_ONLY=1; shift ;;
        --notes) RELEASE_NOTES="${2:?}"; shift 2 ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
done

echo "=== 1/5 环境自检 ==="
git --version
command -v curl >/dev/null && echo "curl: ok"
echo "仓库: $REPO"
echo "代理远端: $REMOTE_PROXY"

# 代理连通性
if timeout 30 curl -sS -o /dev/null -w "  gh-proxy 连通: HTTP %{http_code}\n" \
        "https://gh-proxy.com/https://github.com/${REPO}" 2>/dev/null; then
    :
else
    echo "  ⚠️ 代理访问异常，请检查网络" >&2
fi

if [ "$CHECK_ONLY" = "1" ]; then
    echo "自检结束。"; exit 0
fi

if [ -z "$TOKEN" ]; then
    echo "✗ 未提供 PAT。用法：bash tools/sync_github.sh --token <PAT>" >&2
    exit 1
fi

# ---------- 凭据写入 ----------
CRED="$HOME/.git-credentials"
chmod 600 "$CRED" 2>/dev/null || true

python3 - "$TOKEN" "$REPO" "$CRED" <<'PY'
import os, re, sys
token, repo, cred = sys.argv[1], sys.argv[2], sys.argv[3]
owner = repo.split("/")[0]
entries = []
if os.path.exists(cred):
    with open(cred, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(line)
# 去掉同 host 的旧条目，替换为新令牌
def host_of(u):
    m = re.match(r"^https?://[^@]*@([^/]+)", u)
    return m.group(1) if m else ""
keep = [e for e in entries if host_of(e) not in ("github.com", "gh-proxy.com")]
keep.append(f"https://{owner}:{token}@github.com")
keep.append(f"https://{owner}:{token}@gh-proxy.com")
with open(cred, "w", encoding="utf-8") as fh:
    fh.write("\n".join(keep) + "\n")
os.chmod(cred, 0o600)
print(f"已写入凭据条目（host: github.com / gh-proxy.com）")
PY

# ---------- 远端 ----------
echo ""
echo "=== 2/5 设置远端 ==="
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_PROXY"
git remote -v

echo ""
echo "=== 3/5 推送代码 ==="
git push -u origin main

if [ "$SKIP_RELEASE" = "1" ]; then
    echo "已跳过 Release 创建。"; exit 0
fi

# ---------- Release ----------
echo ""
echo "=== 4/5 创建 Release ==="
VER="$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' src/version.py | head -1)"
echo "版本: $VER"

TAG="v${VER}"
if [ -z "$RELEASE_NOTES" ]; then
    RELEASE_NOTES="$(cat <<EOF
Yc浏览器 v${VER}

本版修复：
- 修复页面点击无反应：setHtml 提供标准 https base URL（原 about:blank / 自定义
  scheme 会形成 opaque origin，Chromium 不发射链接导航请求）
- 内部页二级目录链接（主页 ↔ 关于）可正常点击
- 支持 target="_blank" 与 window.open() 打开新标签页（覆写 createWindow 接管）
- 点击外部链接后地址栏恢复显示真实 URL

真实输入（XTEST）点击响应测试 11/11 通过。
EOF
)"
fi

# 收集安装包
ASSETS=()
for f in package/omnibrowser_"${VER}"_amd64.deb \
         package/omnibrowser-deepin_"${VER}"_amd64.deb; do
    [ -f "$f" ] && ASSETS+=("$f")
done
echo "安装包: ${ASSETS[*]:-(无)}"

echo ""
echo "=== 5/5 上传 Release 资产 ==="
python3 - "$TOKEN" "$REPO" "$TAG" "$RELEASE_NOTES" "${ASSETS[@]:-}" <<'PY'
import json, os, sys, urllib.request, urllib.error

token, repo, tag, notes = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
assets = [a for a in sys.argv[5:] if a]
api = "https://gh-proxy.com/https://api.github.com"

def req(method, url, data=None, headers=None, raw=False):
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
         "User-Agent": "YcBrowser-release"}
    h.update(headers or {})
    body = data
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            content = resp.read()
            return content if raw else (json.loads(content) if content else {})
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read()[:400].decode('utf-8','replace')}")
        raise

# 1) 仓库信息
info = req("GET", f"{api}/repos/{repo}")
print(f"仓库: {info.get('full_name')}  可见性: {info.get('visibility')}")

# 2) 创建 tag（若不存在）
tag_obj = None
try:
    tag_obj = req("GET", f"{api}/repos/{repo}/git/ref/tags/{tag}")
except SystemExit:
    tag_obj = None
except Exception:
    tag_obj = None

if not tag_obj:
    sha = req("GET", f"{api}/repos/{repo}/commits/main")["sha"]
    body = json.dumps({"tag": tag, "message": f"release {tag}", "object": sha,
                       "type": "commit"}).encode()
    req("POST", f"{api}/repos/{repo}/git/refs", data=body,
        headers={"Content-Type": "application/json"})
    print(f"已创建 tag {tag}")

# 3) 创建 Release
rel = req("GET", f"{api}/repos/{repo}/releases/tags/{tag}")
if rel.get("id"):
    print(f"Release {tag} 已存在，沿用并补传资产")
    upload_url = rel["upload_url"].split("{")[0]
    rel_id = rel["id"]
else:
    body = json.dumps({"tag_name": tag, "name": f"Yc浏览器 {tag}",
                       "body": notes, "draft": False, "prerelease": False}).encode()
    rel = req("POST", f"{api}/repos/{repo}/releases", data=body,
              headers={"Content-Type": "application/json"})
    upload_url = rel["upload_url"].split("{")[0]
    rel_id = rel["id"]
    print(f"已创建 Release {tag}（id={rel_id}）")

# 4) 上传资产
for path in assets:
    if not os.path.isfile(path):
        print(f"跳过（不存在）：{path}")
        continue
    name = os.path.basename(path)
    data = open(path, "rb").read()
    req("POST", f"{upload_url}?name={name}", data=data,
        headers={"Content-Type": "application/octet-stream"}, raw=True)
    print(f"已上传：{name}（{len(data)/1024/1024:.1f} MB）")

print(f"\n完成：https://github.com/{repo}/releases/tag/{tag}")
PY
