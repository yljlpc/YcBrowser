#!/usr/bin/env python3
"""获批后一键配置 SignPath 签名链路。

SignPath Foundation 批准后，需要在仓库里完成三件事：
  1. 写入 4 个 Secrets（API Token、Organization ID、Project Slug、签名策略 slug）
  2. 写入 1 个 Repository Variable（SIGNPATH_ENABLED 开关）
  3. （可选）用 admin 权限推一个测试 tag，验证签名请求能被正常受理

本脚本完成前两步，并可选执行第三步。

用法：
    python tools/configure_signpath_secrets.py \\
        --api-token xxx \\
        --organization-id 12345 \\
        --project-slug ycbrowser \\
        --signing-policy-slug release-signing \\
        [--artifact-configuration-slug windows-installer] \\
        [--repo yljlpc/YcBrowser] [--enable]

参数也可以从环境变量读取：
    SIGNPATH_API_TOKEN / SIGNPATH_ORGANIZATION_ID / SIGNPATH_PROJECT_SLUG /
    SIGNPATH_SIGNING_POLICY_SLUG / SIGNPATH_ARTIFACT_CONFIGURATION_SLUG
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"

SECRETS = {
    "SIGNPATH_API_TOKEN": "SignPath API Token（Submitter 权限）",
    "SIGNPATH_ORGANIZATION_ID": "SignPath 组织 ID",
    "SIGNPATH_PROJECT_SLUG": "SignPath 项目 slug",
    "SIGNPATH_SIGNING_POLICY_SLUG": "签名策略 slug（通常为 release-signing）",
    "SIGNPATH_ARTIFACT_CONFIGURATION_SLUG": "产物配置 slug（可选，如 windows-installer）",
}


def api(method, path, token, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = r.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise SystemExit(f"{method} {path} 失败：HTTP {e.code}\n{detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="yljlpc/YcBrowser")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token（需 repo + admin 权限）")
    ap.add_argument("--api-token", default=os.environ.get("SIGNPATH_API_TOKEN"))
    ap.add_argument("--organization-id", default=os.environ.get("SIGNPATH_ORGANIZATION_ID"))
    ap.add_argument("--project-slug", default=os.environ.get("SIGNPATH_PROJECT_SLUG"))
    ap.add_argument("--signing-policy-slug", default=os.environ.get("SIGNPATH_SIGNING_POLICY_SLUG"))
    ap.add_argument("--artifact-configuration-slug",
                    default=os.environ.get("SIGNPATH_ARTIFACT_CONFIGURATION_SLUG"))
    ap.add_argument("--enable", action="store_true", help="同时把 vars.SIGNPATH_ENABLED 设为 true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.token:
        raise SystemExit("需要 GitHub token（设置 GITHUB_TOKEN 或传 --token）")

    values = {
        "SIGNPATH_API_TOKEN": args.api_token,
        "SIGNPATH_ORGANIZATION_ID": args.organization_id,
        "SIGNPATH_PROJECT_SLUG": args.project_slug,
        "SIGNPATH_SIGNING_POLICY_SLUG": args.signing_policy_slug,
        "SIGNPATH_ARTIFACT_CONFIGURATION_SLUG": args.artifact_configuration_slug,
    }

    missing = [k for k in ("SIGNPATH_API_TOKEN", "SIGNPATH_ORGANIZATION_ID",
                           "SIGNPATH_PROJECT_SLUG", "SIGNPATH_SIGNING_POLICY_SLUG")
               if not values.get(k)]
    if missing:
        raise SystemExit(
            "缺少必需参数：\n" + "\n".join(f"  --{k.lower().replace('_', '-')}  ({SECRETS[k]})" for k in missing))

    print(f"目标仓库：{args.repo}\n")
    for k, v in values.items():
        if not v:
            continue
        shown = (v[:6] + "…" + v[-4:]) if k == "SIGNPATH_API_TOKEN" else v
        print(f"  {k} = {shown}   ← {SECRETS[k]}")

    if args.dry_run:
        print("\n--dry-run，未写入任何配置。")
        return

    # 1) Secrets
    for k, v in values.items():
        if not v:
            continue
        # 先删除同名 secret（已存在时 PUT 会返回 422）
        try:
            api("DELETE", f"/repos/{args.repo}/actions/secrets/{k}", args.token)
        except SystemExit:
            pass
        api("PUT", f"/repos/{args.repo}/actions/secrets/{k}", args.token,
            {"encrypted_value": _b64(v), "key_id": _key_id(args.token, args.repo)})
        print(f"✔ Secret 已写入：{k}")

    # 2) Variable
    if args.enable:
        try:
            api("DELETE", f"/repos/{args.repo}/actions/variables/SIGNPATH_ENABLED", args.token)
        except SystemExit:
            pass
        api("POST", f"/repos/{args.repo}/actions/variables", args.token,
            {"name": "SIGNPATH_ENABLED", "value": "true"})
        print("✔ 变量已写入：vars.SIGNPATH_ENABLED = true")

    print("\n完成。签名流程已启用 —— 打一个 v* tag 即可触发：")
    print("    git tag v<新版本> -m '...' && git push origin v<新版本>")
    print("\n随后到 https://app.signpath.io 人工批准签名请求，")
    print("CI 会自动下载签名产物、校验签名并发布 Release。")


def _key_id(token, repo):
    data = api("GET", f"/repos/{repo}/actions/secrets/public-key", token)
    return data["key_id"]


def _b64(text):
    import base64
    return base64.b64encode(text.encode()).decode()


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    main()
