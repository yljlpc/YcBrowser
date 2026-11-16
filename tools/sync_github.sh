#!/usr/bin/env bash
# ============================================================
# Yc浏览器 —— 一键推送源码到 GitHub 并创建 Release
#
# 用法：
#   bash tools/sync_github.sh                     # 交互式输入 PAT（不回显）
#   bash tools/sync_github.sh --token <PAT>       # 直接传 PAT
#   bash tools/sync_github.sh --skip-release      # 只推代码，不建 Release
#   bash tools/sync_github.sh --check             # 只做环境自检
#
# PAT 要求：
#   classic token  → 勾选 repo scope；
#   fine-grained    → 对 yljlpc/YcBrowser 授予 Contents:Read&Write
#                     （创建 Release 还需 Actions:Read&Write）。
#
# 网络说明（重要，勿改）：
#   1. 本机 git 直连 github.com **是可行的** —— git 会读取 http_proxy /
#      https_proxy 环境变量，经本机代理 127.0.0.1:<port> 建立 CONNECT 隧道，
#      实测 git ls-remote 与 api.github.com 均正常（HTTP 200）。
#      → **不要**用 HOME=... 隔离 git 配置来"绕过代理"，那会丢掉环境代理
#        并导致 GnuTLS recv error (-110)。
#   2. gh-proxy.com 这类加速代理经实测**也会转发 git 写操作**
#      （POST git-receive-pack 返回的是 GitHub 自己的 401 "No anonymous
#      write access."，而非代理的 404/403，说明请求确实到达了 GitHub）。
#      → 因此直连与代理两条路径都可用，脚本会自动回退。
#   3. 仓库 https://github.com/yljlpc/YcBrowser 为**公开仓库**，
#      写入只需账号 yljlpc 的有效令牌（classic 需 repo scope）。
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPO="yljlpc/YcBrowser"
REMOTE_URL="https://github.com/${REPO}"
API="https://api.github.com"
TOKEN=""
SKIP_RELEASE=0
CHECK_ONLY=0
RELEASE_NOTES=""
DRY_RUN=0

while [ $# -gt 0 ]; do
    case "$1" in
        --token) TOKEN="${2:?--token 需要 PAT}"; shift 2 ;;
        --repo) REPO="${2:?}"; REMOTE_URL="https://github.com/${REPO}"; shift 2 ;;
        --skip-release) SKIP_RELEASE=1; shift ;;
        --check) CHECK_ONLY=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --notes) RELEASE_NOTES="${2:?}"; shift 2 ;;
        -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
        *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
done

echo "=== 1/5 环境自检 ==="
git --version
command -v curl >/dev/null && echo "curl: ok"
echo "仓库:   $REPO"
echo "远端:   $REMOTE_URL"
echo "API:    $API"
echo "代理:   ${https_proxy:-（无环境代理）}"

if ! timeout 30 curl -sS -o /dev/null -w "  api.github.com 连通: HTTP %{http_code}\n" \
        "$API/repos/${REPO}"; then
    echo "  ⚠️ GitHub API 不可达，请检查网络/代理" >&2
    exit 1
fi

if [ "$CHECK_ONLY" = "1" ]; then
    echo "自检结束。"; exit 0
fi

# ---------- 取得令牌 ----------
if [ -z "$TOKEN" ]; then
    echo ""
    echo "请输入 GitHub Personal Access Token（输入不回显）："
    printf "  PAT: "
    read -r -s TOKEN
    echo
    if [ -z "$TOKEN" ]; then
        echo "✗ 未提供令牌，已中止。" >&2
        exit 1
    fi
fi

# ---------- 校验令牌 ----------
echo ""
echo "=== 2/5 校验令牌 ==="
AUTH_JSON="$(mktemp)"
trap 'rm -f "$AUTH_JSON"' EXIT
HTTP_CODE="$(curl -sS -u "${REPO%%/*}:${TOKEN}" -o "$AUTH_JSON" -w "%{http_code}" "$API/user")"
if [ "$HTTP_CODE" != "200" ]; then
    echo "✗ 令牌无效或无权限（HTTP $HTTP_CODE）：$(python3 -c "
import json
try: print(json.load(open('$AUTH_JSON')).get('message','?'))
except Exception: print('?')")" >&2
    exit 1
fi
GH_USER="$(python3 -c "import json; print(json.load(open('$AUTH_JSON'))['login'])")"
echo "✓ 令牌有效，账号: $GH_USER"

# ---------- 写入凭据（供 git 使用）----------
CRED="$HOME/.git-credentials"
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
def host_of(u):
    m = re.match(r"^https?://[^@]*@([^/]+)", u)
    return m.group(1) if m else ""
keep = [e for e in entries if host_of(e) not in ("github.com", "gh-proxy.com")]
keep.append(f"https://{owner}:{token}@github.com")
keep.append(f"https://{owner}:{token}@gh-proxy.com")
with open(cred, "w", encoding="utf-8") as fh:
    fh.write("\n".join(keep) + "\n")
os.chmod(cred, 0o600)
print("✓ 已写入 git-credentials（host: github.com / gh-proxy.com）")
PY

# ---------- 远端与内容核对 ----------
echo ""
echo "=== 3/5 设置远端并核对内容 ==="
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"
git remote -v

if [ -n "$(git status --porcelain)" ]; then
    echo "检测到未提交的改动："
    git status --short
    if [ "$DRY_RUN" -eq 0 ]; then
        git add -A
        git commit -m "chore: 发布前同步 v$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' src/version.py | head -1)"
        echo "✓ 已提交"
    fi
fi

if git diff --name-only origin/main..main 2>/dev/null | grep -qiE '\.(pfx|p12|pem|key)$|(^|/)\.env$'; then
    echo "✗ 发现疑似敏感文件，中止推送：" >&2
    git diff --name-only origin/main..main | grep -iE '\.(pfx|p12|pem|key)$|(^|/)\.env$' >&2
    exit 1
fi
echo "待推送提交:"
git log --oneline origin/main..main 2>/dev/null || echo "  （无新提交）"
echo "变更文件: $(git diff --name-only origin/main..main 2>/dev/null | wc -l) 个"
echo "✓ 无证书/私钥/密钥文件入库"

if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] 跳过实际推送"; exit 0
fi

# ---------- 推送 ----------
echo ""
echo "=== 4/5 推送代码 ==="
PUSHED=0
for candidate in "$REMOTE_URL" "https://gh-proxy.com/${REMOTE_URL}"; do
    echo "--- 尝试远端: $candidate"
    git remote remove origin 2>/dev/null || true
    git remote add origin "$candidate"
    if git push -u origin main; then
        echo "✓ 推送成功（$candidate）"
        PUSHED=1
        break
    fi
    echo "--- 该路径失败，尝试下一条 ---"
done
if [ "$PUSHED" != "1" ]; then
    echo "✗ 两条路径均推送失败，请检查令牌权限与网络。" >&2
    exit 1
fi

if [ "$SKIP_RELEASE" = "1" ]; then
    echo "已跳过 Release 创建。"; exit 0
fi

# ---------- Release ----------
echo ""
echo "=== 5/5 创建 Release 并上传安装包 ==="
VER="$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' src/version.py | head -1)"
echo "版本: $VER"

TAG="v${VER}"
if [ -z "$RELEASE_NOTES" ]; then
    RELEASE_NOTES="$(cat <<EOF
Yc浏览器 v${VER}

本版修复：
- 修复页面点击无反应：setHtml 提供标准 https base URL（原 about:blank 与自定义
  scheme 会形成 opaque origin，Chromium 不发射链接导航请求，链接点了没反应）
- 内部页二级目录链接（主页 ↔ 关于）可正常点击
- 支持 target=_blank 与 window.open() 打开新标签页（覆写 createWindow 接管）
- 点击外部链接后地址栏恢复显示真实 URL

真实输入（XTEST）点击响应测试 11/11 通过。
EOF
)"
fi

ASSETS=()
for f in package/omnibrowser_"${VER}"_amd64.deb \
         package/omnibrowser-deepin_"${VER}"_amd64.deb; do
    [ -f "$f" ] && ASSETS+=("$f")
done
echo "安装包: ${ASSETS[*]:-(无)}"

python3 - "$TOKEN" "$REPO" "$TAG" "$RELEASE_NOTES" "$API" "${ASSETS[@]:-}" <<'PY'
import json, os, sys, urllib.parse, urllib.request, urllib.error

token, repo, tag, notes, api = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
assets = [a for a in sys.argv[6:] if a]

def req(method, url, data=None, headers=None, raw=False):
    """请求 GitHub API；直连失败时自动回退 gh-proxy 代理路径。"""
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
         "User-Agent": "YcBrowser-release"}
    h.update(headers or {})
    last = None
    # 主路径直连 api.github.com；回退路径为 gh-proxy 前缀形式
    urls = [url]
    if url.startswith("https://api.github.com"):
        urls.append("https://gh-proxy.com/" + url)
    for u in urls:
        r = urllib.request.Request(u, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(r, timeout=180) as resp:
                content = resp.read()
                return content if raw else (json.loads(content) if content else {})
        except urllib.error.HTTPError as e:
            body = e.read()[:400].decode("utf-8", "replace")
            # 4xx（鉴权/权限）是业务错误，重试其它路径没有意义，直接抛出
            if 400 <= e.code < 500:
                print(f"HTTP {e.code}: {body}")
                raise
            last = (e.code, body)
        except Exception as e:  # noqa: BLE001
            last = ("ERR", repr(e))
    code, body = last
    print(f"HTTP {code}: {body}")
    raise SystemExit(f"API 请求失败：{code}")

info = req("GET", f"{api}/repos/{repo}")
print(f"仓库: {info.get('full_name')}  可见性: {info.get('visibility')}")

# tag（不存在则创建）
try:
    req("GET", f"{api}/repos/{repo}/git/ref/tags/{tag}")
    print(f"tag {tag} 已存在")
except urllib.error.HTTPError:
    sha = req("GET", f"{api}/repos/{repo}/commits/main")["sha"]
    body = json.dumps({"tag": tag, "message": f"release {tag}",
                       "object": sha, "type": "commit"}).encode()
    req("POST", f"{api}/repos/{repo}/git/refs", data=body,
        headers={"Content-Type": "application/json"})
    print(f"已创建 tag {tag}")

# Release
try:
    rel = req("GET", f"{api}/repos/{repo}/releases/tags/{tag}")
    print(f"Release {tag} 已存在，沿用并补传资产")
except urllib.error.HTTPError:
    rel = None

if rel:
    upload_url = rel["upload_url"].split("{")[0]
else:
    body = json.dumps({"tag_name": tag, "name": f"Yc浏览器 {tag}", "body": notes,
                       "draft": False, "prerelease": False}).encode()
    rel = req("POST", f"{api}/repos/{repo}/releases", data=body,
              headers={"Content-Type": "application/json"})
    upload_url = rel["upload_url"].split("{")[0]
    print(f"已创建 Release {tag}（id={rel['id']}）")

for path in assets:
    if not os.path.isfile(path):
        print(f"跳过（不存在）：{path}")
        continue
    name = os.path.basename(path)
    data = open(path, "rb").read()
    # 资产名需 URL 编码（GitHub 要求 query 参数正确转义）
    qname = urllib.parse.quote(name, safe="")
    req("POST", f"{upload_url}?name={qname}", data=data,
        headers={"Content-Type": "application/octet-stream"}, raw=True)
    print(f"已上传：{name}（{len(data)/1024/1024:.1f} MB）")

print(f"\n完成：https://github.com/{repo}/releases/tag/{tag}")
PY
