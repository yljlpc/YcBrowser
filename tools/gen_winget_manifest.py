#!/usr/bin/env python3
"""生成 winget-pkgs 的包清单（manifest）。

winget 是微软官方的 Windows 包管理器，也是开源项目最重要的官方分发渠道之一。
被 winget 收录后，Windows 用户可以用 `winget install YcBrowser.YcBrowser`
直接安装 —— 这同时也是 SignPath Foundation 开源代码签名审核看重的
「官方分发渠道」信号。

用法：
    python tools/gen_winget_manifest.py --version 1.1.13
    python tools/gen_winget_manifest.py --version 1.1.13 --repo yljlpc/YcBrowser

产出目录：
    winget/manifests/y/YcBrowser/YcBrowser/<版本>/

清单规范（ManifestVersion 1.12.0）包含四个文件：
    YcBrowser.YcBrowser.yaml            —— 版本清单（版本号、默认语言）
    YcBrowser.YcBrowser.installer.yaml  —— 安装器清单（下载地址、校验和、开关）
    YcBrowser.YcBrowser.locale.zh-CN.yaml
    YcBrowser.YcBrowser.locale.en-US.yaml

校验和直接从 GitHub Release 资产的 digest 字段读取（GitHub 会对上传的
资产计算 SHA-256），不依赖本地下载产物。
"""
import argparse
import json
import os
import sys
import urllib.request

REPO = "yljlpc/YcBrowser"
PACKAGE = "YcBrowser"
IDENTIFIER = f"{PACKAGE}.{PACKAGE}"
MANIFEST_VERSION = "1.28.0"
RELEASE_URL = "https://github.com/{repo}/releases/tag/v{version}"
DOWNLOAD_URL = ("https://github.com/{repo}/releases/download/v{version}/"
                "YcBrowser-{version}-setup.exe")

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DESC_ZH = """\
Yc浏览器是一款开源的多引擎桌面浏览器，基于 Rust 原生核心与 PyQt6（Qt 6 WebEngine）构建。

主要特性：

• 多引擎兼容 —— Blink（Chromium 内核 + V8）为默认引擎，同时支持 WebKit 用户代理与 Trident 兼容模式（按 X-UA-Compatible 协商文档模式并注入遗留 DOM 垫片）。每个标签页使用独立的 QWebEngineProfile，可按标签页隔离引擎与用户代理。

• 实时英译中 —— 提取页面可见正文并逐句翻译，配合术语统一与口语化改写后回填 DOM，可一键还原原文。后端支持 MyMemory（免费）、Google、LibreTranslate 及自定义端点。

• 高速下载引擎 —— 单文件最多 32 个连接并行分片，支持动态再平衡、限速与断点续传，并按扩展名自动归档到视频、音乐、程序、压缩包、文档等分类目录。

• 界面与体验 —— 多标签、独立地址栏、历史、书签、页面查找、下载管理、开发者工具；分辨率自适应缩放；无痕窗口、打印与导出 PDF。

Windows 安装包完全自带运行时：Qt 6 全部运行时（平台插件、WebEngine 渲染进程与资源包、ICU 数据、V8 快照）、Python 运行时、VC++ 运行库、中文字体与 Rust 原生核心，目标机器无需预装任何软件或环境。
"""

DESC_EN = """\
YcBrowser is an open-source multi-engine desktop browser built on a Rust native core with a PyQt6 (Qt 6 WebEngine) shell.

• Multi-engine compatibility — Blink (Chromium content + V8) by default, plus a WebKit user-agent and Trident compatibility mode that negotiates document mode via X-UA-Compatible and injects legacy DOM shims. Every tab has its own QWebEngineProfile, so engine and user agent can be isolated per tab.

• Live English-to-Chinese translation — visible page text is extracted and translated sentence by sentence, with terminology unification and colloquial rewriting applied before the result is written back into the DOM; one click restores the original. Backends: MyMemory (free), Google, LibreTranslate or a custom endpoint.

• High-speed download engine — up to 32 parallel connections per file, with dynamic rebalancing, throttling, resume support and automatic archiving by file type.

• Interface — multi-tab browsing, history, bookmarks, find-in-page, download manager, developer tools, resolution-aware scaling, incognito windows, printing and PDF export.

The Windows installer is fully self-contained: it bundles the complete Qt 6 runtime, a Python runtime, the VC++ runtime, Chinese fonts and the Rust native core, so it runs on a machine with no preinstalled software or environment.
"""


def indent_block(text, n=2):
    """给多行文本整体加缩进，使其能放进 YAML 块标量（|-）内。"""
    pad = " " * n
    lines = text.rstrip("\n").split("\n")
    return "\n".join(pad + ln if ln.strip() else "" for ln in lines)


def fit(text, limit=1024, label="Description"):
    """winget 的 Description 上限为 1024 字符，超出时按句号边界裁剪。"""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    dot = cut.rfind(". ")
    if dot > limit * 0.5:
        cut = cut[:dot + 1]
    else:
        cut = cut[:limit].rstrip() + "..."
    print(f"⚠️  {label} 超长（{len(text)} > {limit}），已裁剪到 {len(cut)} 字符")
    return cut


def api_get(url, token=None):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def release_digest(repo, version, token=None):
    """取 Release 资产的 SHA-256（GitHub 会对上传资产计算 digest）。"""
    try:
        data = api_get(f"https://api.github.com/repos/{repo}/releases/tags/v{version}", token)
    except Exception as exc:  # Release 尚未发布或无访问权限
        raise SystemExit(
            f"无法读取 {repo} 的 v{version} Release：{exc}\n"
            f"请先完成该版本的发布，再用 --sha256 手动指定校验和。")
    name = f"YcBrowser-{version}-setup.exe"
    for asset in data.get("assets", []):
        if asset["name"] == name:
            digest = asset.get("digest") or ""
            if digest.startswith("sha256:"):
                return digest.split(":", 1)[1].upper()
            raise SystemExit(
                f"资产 {name} 没有 digest 字段，无法自动生成 InstallerSha256。\n"
                f"请手动下载并计算：certutil -hashfile {name} SHA256")
    raise SystemExit(f"Release v{version} 中找不到资产 {name}")


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print("生成:", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True, help="版本号，如 1.1.13")
    ap.add_argument("--repo", default=REPO, help="GitHub 仓库 owner/name")
    ap.add_argument("--out", default=None, help="输出根目录，默认 <仓库>/winget")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token")
    ap.add_argument("--sha256", default=None,
                    help="手动指定安装包 SHA-256（Release 尚未发布或资产无 digest 时使用）")
    args = ap.parse_args()

    v = args.version
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = args.out or os.path.join(root, "winget")
    base = os.path.join(out, "manifests", "y", PACKAGE, PACKAGE, v)
    os.makedirs(base, exist_ok=True)

    sha = args.sha256.upper() if args.sha256 else release_digest(args.repo, v, args.token)
    if len(sha) != 64 or not all(c in "0123456789ABCDEF" for c in sha):
        raise SystemExit(f"SHA-256 格式不正确：{sha}")
    url = DOWNLOAD_URL.format(repo=args.repo, version=v)
    repo_url = f"https://github.com/{args.repo}"
    release = RELEASE_URL.format(repo=args.repo, version=v)

    # 1) 版本清单
    write(os.path.join(base, f"{IDENTIFIER}.yaml"), f"""\
# yaml-language-server: $schema=https://aka.ms/winget-manifest.version.{MANIFEST_VERSION}.schema.json

PackageIdentifier: {IDENTIFIER}
PackageVersion: {v}
DefaultLocale: zh-CN
ManifestType: version
ManifestVersion: {MANIFEST_VERSION}
""")

    # 2) 安装器清单（NSIS）
    write(os.path.join(base, f"{IDENTIFIER}.installer.yaml"), f"""\
# yaml-language-server: $schema=https://aka.ms/winget-manifest.installer.{MANIFEST_VERSION}.schema.json

PackageIdentifier: {IDENTIFIER}
PackageVersion: {v}
Scope: machine
UpgradeBehavior: uninstallPrevious
Installers:
- Architecture: x64
  InstallerType: nullsoft
  InstallerUrl: {url}
  InstallerSha256: {sha}
  InstallerSwitches:
    Silent: /S
    SilentWithProgress: /S
  ProductCode: {PACKAGE}
  AppsAndFeaturesEntries:
  - DisplayName: Yc浏览器 {v}
    DisplayVersion: {v}
    Publisher: Yc
ManifestType: installer
ManifestVersion: {MANIFEST_VERSION}
""")

    # 3) 中文本地化（DefaultLocale，ManifestType 为 defaultLocale）
    write(os.path.join(base, f"{IDENTIFIER}.locale.zh-CN.yaml"), f"""\
# yaml-language-server: $schema=https://aka.ms/winget-manifest.defaultLocale.{MANIFEST_VERSION}.schema.json

PackageIdentifier: {IDENTIFIER}
PackageVersion: {v}
PackageLocale: zh-CN
Publisher: Yc
PublisherUrl: {repo_url}
PublisherSupportUrl: {repo_url}/issues
PrivacyUrl: {repo_url}/blob/main/PRIVACY.md
PackageName: Yc浏览器
PackageUrl: {release}
License: MIT
LicenseUrl: {repo_url}/blob/main/LICENSE
Copyright: © 2026 yljlpc
ShortDescription: 基于 Rust 核心与 Qt 6 的多引擎桌面浏览器，支持实时翻译与高速下载。
Description: |-
{indent_block(fit(DESC_ZH))}
Tags:
- browser
- translation
- downloader
- webengine
ManifestType: defaultLocale
ManifestVersion: {MANIFEST_VERSION}
""")

    # 4) 英文本地化（普通 locale）
    write(os.path.join(base, f"{IDENTIFIER}.locale.en-US.yaml"), f"""\
# yaml-language-server: $schema=https://aka.ms/winget-manifest.locale.{MANIFEST_VERSION}.schema.json

PackageIdentifier: {IDENTIFIER}
PackageVersion: {v}
PackageLocale: en-US
Publisher: Yc
PublisherUrl: {repo_url}
PublisherSupportUrl: {repo_url}/issues
PrivacyUrl: {repo_url}/blob/main/PRIVACY.md
PackageName: YcBrowser
PackageUrl: {release}
License: MIT
LicenseUrl: {repo_url}/blob/main/LICENSE
Copyright: © 2026 yljlpc
ShortDescription: A multi-engine desktop browser built on a Rust core and Qt 6, with live translation and a fast downloader.
Description: |-
{indent_block(fit(DESC_EN))}
Tags:
- browser
- translation
- downloader
- webengine
ManifestType: locale
ManifestVersion: {MANIFEST_VERSION}
""")

    print()
    print("winget 提交路径:", base.replace(os.sep, "/"))
    print("InstallerSha256:", sha)
    print("安装命令: winget install --id", IDENTIFIER)


if __name__ == "__main__":
    main()
