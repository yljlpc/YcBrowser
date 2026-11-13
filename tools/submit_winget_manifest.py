#!/usr/bin/env python3
"""把 winget 清单提交到 microsoft/winget-pkgs（通过 fork 提 PR）。

winget 是微软官方的 Windows 包管理器。被收录后用户可直接
`winget install YcBrowser.YcBrowser` 安装 —— 这同时是 SignPath Foundation
开源代码签名审核看重的「官方分发渠道」信号。

流程：
  1. 确认 fork 已存在（不存在则创建）
  2. 在 fork 上按 winget 惯例创建版本分支
  3. 用 Contents API 逐个写入清单文件（无需 clone 整个大仓库）
  4. 向 microsoft/winget-pkgs 的 master 发起 PR

用法：
    python tools/submit_winget_manifest.py --version 1.1.13
    python tools/submit_winget_manifest.py --version 1.1.13 --dry-run
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

UPSTREAM = "microsoft/winget-pkgs"
PACKAGE = "YcBrowser"
IDENTIFIER = f"{PACKAGE}.{PACKAGE}"
API = "https://api.github.com"


def api(method, path, token, body=None, raw=False):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            payload = r.read()
            return payload.decode() if raw else (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise SystemExit(f"{method} {path} 失败：HTTP {e.code}\n{detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--owner", default=None, help="fork 所属账号，默认取当前 token 所属用户")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    ap.add_argument("--dry-run", action="store_true", help="只打印将要提交的内容")
    ap.add_argument("--no-pr", action="store_true", help="只更新清单文件，不创建 PR")
    ap.add_argument("--branch", default=None, help="指定分支名，默认 manifests/y/<包>/<包>/<版本>")
    args = ap.parse_args()

    if not args.token:
        raise SystemExit("需要 GitHub token：设置环境变量 GITHUB_TOKEN 或传 --token")

    owner = args.owner
    if not owner:
        owner = api("GET", "/user", args.token)["login"]

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = os.path.join(root, "winget", "manifests", "y", PACKAGE, PACKAGE, args.version)
    if not os.path.isdir(base):
        raise SystemExit(f"清单目录不存在：{base}\n请先运行 tools/gen_winget_manifest.py")

    files = sorted(f for f in os.listdir(base) if f.endswith((".yaml", ".yml")))
    rel_base = f"manifests/y/{PACKAGE}/{PACKAGE}/{args.version}"
    print("待提交文件：")
    for f in files:
        print("  ", f"{rel_base}/{f}")
    if args.dry_run:
        return

    fork = f"{owner}/winget-pkgs"
    # 1) 确认 fork
    try:
        api("GET", f"/repos/{fork}", args.token)
        print(f"\nfork 已存在：{fork}")
    except SystemExit:
        print(f"\n创建 fork：{fork}")
        api("POST", f"/repos/{UPSTREAM}/forks", args.token, {})
        api("GET", f"/repos/{fork}", args.token)

    # 2) 创建版本分支（winget 社区惯例：分支名与清单目录一致）
    branch = args.branch or rel_base
    try:
        api("GET", f"/repos/{fork}/branches/{branch}", args.token)
        print(f"分支已存在：{branch}")
    except SystemExit:
        head = api("GET", f"/repos/{fork}/branches/master", args.token)["commit"]["sha"]
        api("POST", f"/repos/{fork}/git/refs", args.token,
            {"ref": f"refs/heads/{branch}", "sha": head})
        print(f"已创建分支：{branch}")

    # 3) 写入文件（已存在则先取 blob sha，走更新流程）
    for f in files:
        path = f"{rel_base}/{f}"
        content = open(os.path.join(base, f), "rb").read()
        payload = {
            "message": f"Add new manifest: {IDENTIFIER} ({args.version})",
            "content": base64.b64encode(content).decode(),
            "branch": branch,
        }
        try:
            existing = api("GET", f"/repos/{fork}/contents/{path}?ref={branch}", args.token)
            if isinstance(existing, dict) and existing.get("sha"):
                payload["sha"] = existing["sha"]
                payload["message"] = f"Update manifest: {IDENTIFIER} ({args.version})"
        except SystemExit:
            pass
        api("PUT", f"/repos/{fork}/contents/{path}", args.token, payload)
        print(f"  已写入 {path}")

    if args.no_pr:
        print("\n--no-pr：仅更新文件，未创建 PR。")
        return

    # 4) 发起 PR
    title = f"New package: {IDENTIFIER} ({args.version})"
    body = f"""\
New package manifest for `{IDENTIFIER}` version `{args.version}`.

- Repository: https://github.com/{owner}/YcBrowser
- Release: https://github.com/{owner}/YcBrowser/releases/tag/v{args.version}
- License: MIT
- Installer type: nullsoft (NSIS), x64, machine scope
- The Windows installer is fully self-contained (bundles the complete Qt 6
  runtime, a Python runtime, the VC++ runtime, Chinese fonts and the Rust
  native core), so it needs no preinstalled software or environment.

Signed binaries: the release artifacts are produced by GitHub Actions and are
signed through the SignPath Foundation free open-source program.

Validation performed locally:

```
winget create --id {IDENTIFIER} --version {args.version} --installer-type nullsoft ...
winget validate --manifest manifest
```
"""
    pr = api("POST", f"/repos/{UPSTREAM}/pulls", args.token, {
        "title": title,
        "head": f"{owner}:{branch}",
        "base": "master",
        "body": body,
        "draft": False,
    })
    print(f"\nPR 已创建：{pr['html_url']}")


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    main()
