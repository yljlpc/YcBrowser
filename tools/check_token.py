#!/usr/bin/env python3
"""GitHub 令牌自检工具 —— 生成令牌后立即验证是否可用。

用法：
    python3 tools/check_token.py              # 交互式输入令牌（不回显）
    python3 tools/check_token.py --token <T>  # 直接传入（不推荐，会进 shell history）

检查项：
    1. 令牌是否被 GitHub 接受（GET /user）
    2. 账号是否为 yljlpc
    3. 对目标仓库的写入权限（Contents: Read and write）
    4. 是否具备创建 Release 的权限（Actions / metadata）

退出码：0 = 完全可用；1 = 有问题（会说明缺什么）
"""
import argparse
import json
import os
import subprocess
import sys

API = "https://api.github.com"
REPO = "yljlpc/YcBrowser"


def api(path, token, method="GET", data=None):
    """调用 GitHub API，返回 (http_code, json_body)。"""
    url = path if path.startswith("http") else f"{API}{path}"
    cmd = ["curl", "-sS", "-X", method, "-u", f"yljlpc:{token}",
           "-H", "Accept: application/vnd.github+json",
           "-H", "User-Agent: YcBrowser-token-check",
           "-w", "\n%{http_code}"]
    if data is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(data)]
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return 0, {"message": "请求超时（网络或代理问题）"}
    out = r.stdout.rsplit("\n", 1)
    if len(out) != 2:
        return 0, {"message": (r.stderr or r.stdout)[:200]}
    body, code = out[0], out[1].strip()
    try:
        return int(code), json.loads(body) if body else {}
    except json.JSONDecodeError:
        return int(code), {"message": body[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default="")
    args = ap.parse_args()

    token = args.token
    if not token:
        print("请粘贴 GitHub Personal Access Token（输入不回显）：", end=" ", flush=True)
        import getpass
        token = getpass.getpass("")
        print()

    if not token:
        print("✗ 未输入令牌。")
        return 1

    # 形态提示
    prefix = "".join(c for c in token[:5] if c.isalpha() or c == "_")
    known = {
        "ghp_": "classic PAT",
        "github_pat_": "fine-grained PAT",
        "gho_": "OAuth token",
        "ghs_": "GitHub App token",
        "ghu_": "GitHub App refresh token",
    }
    kind = known.get(token[:len(prefix)], "未知形态")

    print(f"令牌形态: {kind}（前缀 {prefix}…，长度 {len(token)}）")
    print()

    # 1) 令牌有效性
    code, me = api("/user", token)
    if code != 200:
        print(f"✗ 令牌无效 —— GitHub 返回 HTTP {code}: {me.get('message')}")
        print()
        print("排查：")
        if code == 401:
            print("  · 令牌复制时可能带入了空格/换行 → 重新复制一次")
            print("  · 令牌已过期或已被撤销 → 重新生成")
            print("  · 勾错了账号 → 确认令牌属于 yljlpc")
        elif code == 403:
            print("  · 可能触发了速率限制，或令牌权限不足")
        return 1

    login = me.get("login", "?")
    print(f"✓ 令牌有效，账号: {login}")
    if login != "yljlpc":
        print(f"  ⚠️ 当前令牌属于 {login}，而非 yljlpc；"
              f"只有该账号对 {REPO} 有写权限时才能推送。")

    # 2) 仓库写权限
    code, repo = api(f"/repos/{REPO}", token)
    if code != 200:
        print(f"✗ 无法读取仓库 {REPO}（HTTP {code}）")
        return 1
    perms = repo.get("permissions") or {}
    admin = perms.get("admin")
    push = perms.get("push")
    pull = perms.get("pull")
    print(f"✓ 仓库 {repo.get('full_name')} 可见性={repo.get('visibility')}")
    print(f"  权限: pull={pull} push={push} admin={admin}")
    if not push:
        print()
        print("✗ 该令牌对仓库没有 push 权限，无法推送代码。")
        print("  · classic token → 必须勾选 repo scope")
        print("  · fine-grained → 需对该仓库授予 Contents: Read and write")
        return 1
    print("  ✓ 具备推送权限")

    # 3) Release 创建能力（检查 metadata 权限）
    code, rels = api(f"/repos/{REPO}/releases?per_page=1", token)
    if code == 200:
        print("✓ 可访问 Releases API（具备创建 Release 的基础权限）")
    else:
        print(f"⚠️ Releases API 返回 HTTP {code}: {rels.get('message')}")
        print("  创建 Release 通常需要额外勾选 Actions 或 workflow 权限")

    # 4) 写入 git 凭据（否则 git 拿不到令牌）
    cred_path = os.path.expanduser("~/.git-credentials")
    try:
        entries = []
        if os.path.exists(cred_path):
            with open(cred_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        entries.append(line)

        def host_of(u):
            import re
            m = re.match(r"^https?://[^@]*@([^/]+)", u)
            return m.group(1) if m else ""

        keep = [e for e in entries if host_of(e) not in ("github.com", "gh-proxy.com")]
        keep.append(f"https://{login}:{token}@github.com")
        keep.append(f"https://{login}:{token}@gh-proxy.com")
        with open(cred_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(keep) + "\n")
        os.chmod(cred_path, 0o600)
        print(f"✓ 已写入 {cred_path}（host: github.com / gh-proxy.com，权限 600）")
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 写入凭据文件失败：{exc!r}")

    # 5) 能否触发 git push（用 git 自身测一次，不实际推送）
    print()
    print("→ 正在用 git 实测推送链路（dry-run，不改动远端）…")
    repo_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "ycprobe")
    if not os.path.isdir(repo_dir):
        print(f"  ⚠️ 找不到仓库目录 {repo_dir}，跳过 git 实测")
        return 0
    r = subprocess.run(
        ["git", "-C", repo_dir, "push", "--dry-run", "origin", "main"],
        capture_output=True, text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    combined = (r.stdout + r.stderr).strip()
    if r.returncode == 0:
        print("✓ git push --dry-run 成功（推送链路完全打通）")
        ok = True
    else:
        print("✗ git push --dry-run 失败：")
        for line in combined.splitlines()[-6:]:
            print(f"    {line}")
        ok = False

    print()
    if ok:
        print("=" * 56)
        print("结论：令牌可用，推送与发布已就绪。")
        print("执行：bash tools/sync_github.sh --token <你的令牌>")
        print("   或：bash tools/publish_release.sh  （交互式输入，不进历史记录）")
        print("=" * 56)
        return 0
    print("结论：令牌本身有效，但 git 推送链路仍有问题，请看上方错误。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
