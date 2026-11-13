#!/usr/bin/env python3
"""Windows Authenticode 代码签名工具。

为 Yc浏览器 的 Windows 产物（便携程序 / NSIS 安装包）提供签名能力。

三条签名路线（按优先级自动选择）：

1. **SignPath Foundation**（推荐，开源项目免费）
   证书签发给 SignPath Foundation 本身，由其核验二进制确实来自你的公开仓库。
   私钥存放在 SignPath 的 HSM，签名请求需人工审批。
   前提：项目需 OSI 认可的开源许可证 + GitHub 公开仓库 + CI 自动化构建。
   参考：https://signpath.org

2. **微软 Artifact Signing（原 Trusted Signing）**
   通过 Azure 账户 + 身份验证，签发短时效（数天）证书，
   私钥始终不出云端，CI 用 GitHub OIDC 认证调用。
   前提：Azure 订阅 + 完成个人/组织身份验证（需法律文件，人工审核）。
   注意：Public Trust 目前对中国大陆个人开发者不开放。
   参考：https://learn.microsoft.com/azure/trusted-signing/

3. **商业 OV/EV 代码签名证书**（DigiCert / Sectigo / GlobalSign / SSL.com IV）
   自费购买，OV 需组织或（SSL.com IV）个人身份，EV 需实体。
   2023 年起 CA/B Forum 要求私钥必须存于硬件令牌或云签名服务。
   注意：EV 证书已不再是 SmartScreen 的即时豁免条件。

用法：
    python tools/sign_windows.py --check              # 检查签名工具与证书
    python tools/sign_windows.py --selfsign           # 生成自签证书（仅本机测试用）
    python tools/sign_windows.py --sign <file.exe>    # 签名并加 RFC3161 时间戳
    python tools/sign_windows.py --verify <file.exe>   # 验证签名
"""
import argparse
import datetime
import glob
import os
import shutil
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERT_NAME = "YcBrowser Code Signing"
DEFAULT_TIMESTAMP_URL = "http://timestamp.digicert.com"


# ---------------------------------------------------------------- 工具定位

def find_signtool():
    """定位 signtool.exe（随 Windows SDK 分发）。"""
    exe = shutil.which("signtool")
    if exe:
        return exe
    roots = [
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        r"C:\Program Files (x86)",
        r"C:\Program Files",
    ]
    for root in roots:
        kits = os.path.join(root, "Windows Kits", "10", "bin")
        if not os.path.isdir(kits):
            continue
        # 优先 x64
        cands = sorted(glob.glob(os.path.join(kits, "*", "x64", "signtool.exe")),
                       reverse=True)
        cands += sorted(glob.glob(os.path.join(kits, "*", "x86", "signtool.exe")),
                        reverse=True)
        if cands:
            return cands[0]
    return None


def run(cmd, **kw):
    print("+", " ".join(cmd) if isinstance(cmd, list) else cmd)
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def run_powershell(script):
    """执行多行 PowerShell 脚本。

    用 -EncodedCommand（UTF-16LE Base64）传递，避免多行字符串被
    PowerShell 的 -Command 参数解析搞乱，同时天然规避引号转义问题。
    编码用 errors="replace" 兜底 —— Windows PowerShell 默认输出 GBK。
    """
    import base64
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-OutputFormat", "Text",
         "-EncodedCommand", enc],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


# ---------------------------------------------------------------- 子命令

def cmd_check(args):
    """检查签名链路就绪度。"""
    ok = True
    signtool = find_signtool()
    if signtool:
        print(f"[OK]   signtool: {signtool}")
        r = run([signtool, "/?"])
        print("      signtool 可执行")
    else:
        ok = False
        print("[缺失] signtool.exe —— 随 Windows SDK 分发。")
        print("       可安装：winget install Microsoft.WindowsSDK")

    certs = list_personal_certs()
    if certs:
        print(f"[OK]   证书库中有 {len(certs)} 张带私钥的代码签名证书：")
        for c in certs:
            print(f"       - {c}")
    else:
        print("[缺失] 没有带私钥的代码签名证书。")
        print("       本机测试可用：python tools/sign_windows.py --selfsign")
        print("       正式发布需向 CA 购买，或申请 SignPath Foundation 免费证书。")

    if os.environ.get("AZURE_SIGNING_ENDPOINT"):
        print("[OK]   Azure Artifact Signing 环境变量已配置")
    else:
        print("[提示] 未配置 Azure Artifact Signing（AZURE_SIGNING_ENDPOINT）")

    return 0 if ok else 1


def list_personal_certs():
    """列出当前用户证书库中带私钥的代码签名证书（用 certutil 避免 PowerShell 依赖）。"""
    out = []
    try:
        r = subprocess.run(
            ["certutil", "-user", "-store", "My"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        return out
    # 解析 certutil 输出中的"使用者"字段，过滤 Code Signing 用途
    blocks = r.stdout.split("=" * 40)
    for b in blocks:
        if "代码签名" in b or "Code Signing" in b or "代码签名用途" in b:
            for line in b.splitlines():
                if "使用者" in line or "Subject:" in line:
                    out.append(line.strip())
                    break
    return out


def cmd_selfsign(args):
    """生成自签代码签名证书（仅用于本机测试，不会获得公开信任）。"""
    # 注意：PowerShell 里的 {text} 会被 Python 的 f-string/format 误解析，
    # 因此这里用普通字符串 + 拼接，避免大括号被当作占位符。
    ps = (
        '$ErrorActionPreference = "Stop"\n'
        '$name = "' + CERT_NAME + '"\n'
        '$existing = Get-ChildItem Cert:\\CurrentUser\\My | '
        'Where-Object { $_.Subject -like "*$name*" }\n'
        'if ($existing) {\n'
        '  Write-Output ("EXISTING|" + $existing[0].Thumbprint + "|" + $existing[0].Subject)\n'
        '  exit 0\n'
        '}\n'
        '# 新建代码签名证书（EKU = Code Signing 1.3.6.1.5.5.7.3.3）\n'
        '$r = New-SelfSignedCertificate -Type CodeSigningCert '
        '-Subject "CN=$name, O=Yc Browser, C=CN" '
        '-CertStoreLocation "Cert:\\CurrentUser\\My" -KeyAlgorithm RSA -KeyLength 3072 '
        '-HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears(3) -KeyExportPolicy Exportable '
        '-KeyUsage DigitalSignature\n'
        'Write-Output ("CREATED|" + $r.Thumbprint + "|" + $r.Subject)\n'
    )
    r = run_powershell(ps)
    print(r.stdout.strip())
    if r.returncode != 0:
        print((r.stderr or "").strip())
        return 1
    # 导出 PFX 供 signtool 使用
    tp = None
    for line in r.stdout.splitlines():
        if "|" in line:
            parts = line.split("|")
            if len(parts) >= 2:
                tp = parts[1].strip()
    if tp:
        pfx = os.path.join(ROOT, "installer", "yc-signing.pfx")
        exp = (
            '$ErrorActionPreference = "Stop"\n'
            '$c = Get-ChildItem Cert:\\CurrentUser\\My | '
            'Where-Object { $_.Thumbprint -eq "' + tp + '" }\n'
            '$pw = ConvertTo-SecureString -String "' + args.password + '" '
            '-Force -AsPlainText\n'
            'Export-PfxCertificate -Cert $c -FilePath "' + pfx + '" -Password $pw | Out-Null\n'
            'Write-Output "EXPORTED"\n'
        )
        r2 = run_powershell(exp)
        print((r2.stdout or "").strip() or (r2.stderr or "").strip())
        print(f"PFX: {pfx}")
        print("注意：自签证书不受 Windows 公开信任，用户仍会看到「未知发布者」。")
    return 0


def cmd_sign(args):
    """对文件执行 Authenticode 签名。"""
    signtool = find_signtool()
    if not signtool:
        print("❌ 未找到 signtool.exe，请安装 Windows SDK")
        return 1
    if not os.path.isfile(args.file):
        print(f"❌ 文件不存在: {args.file}")
        return 1

    cmd = [signtool, "sign"]
    if args.pfx:
        cmd += ["/f", args.pfx]
        if args.password:
            cmd += ["/p", args.password]
    else:
        cmd += ["/a"]  # 自动选择证书库中的证书
    # SHA-256 + RFC3161 时间戳（证书到期后签名依然有效）
    cmd += ["/fd", "SHA256", "/tr", args.timestamp, "/td", "SHA256"]
    if args.name:
        cmd += ["/n", args.name]
    cmd += ["/v", args.file]

    r = run(cmd)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr.strip())
        return 1
    print(f"✅ 已签名: {args.file}")
    return cmd_verify(args)


def _pe_has_signature(path):
    """检查 PE 文件是否带有 Authenticode 签名。

    直接解析 PE 头的数据目录（IMAGE_DIRECTORY_ENTRY_SECURITY，即索引 4）：
    该项的 Size 非 0 即表示文件末尾附带了 WIN_CERTIFICATE 签名块。

    之所以不用 PowerShell 的 Get-AuthenticodeSignature 逐个查：一是每文件
    启动一次进程开销大，二是其输出通道（CLIXML）在批量场景下容易出现
    转义与编码问题。纯解析更确定、更快。
    """
    try:
        with open(path, "rb") as f:
            # DOS 头：e_lfanew 在偏移 0x3C
            f.seek(0x3C)
            lfanew = struct.unpack("<I", f.read(4))[0]
            if lfanew < 0x40 or lfanew > 0x10000:
                return False

            f.seek(lfanew)
            if f.read(4) != b"PE\x00\x00":
                return False

            # COFF 头：Machine(2) + NumberOfSections(2) + ... + SizeOfOptionalHeader(2)
            coff = f.read(20)
            size_opt = struct.unpack("<H", coff[16:18])[0]
            if size_opt == 0:
                return False

            # 可选头：Magic 决定 PE32 / PE32+
            opt_start = f.tell()
            magic = struct.unpack("<H", f.read(2))[0]
            if magic == 0x10B:      # PE32
                dd_offset = opt_start + 96
            elif magic == 0x20B:    # PE32+
                dd_offset = opt_start + 112
            else:
                return False

            # 数据目录第 5 项（索引 4）= Certificate Table
            f.seek(dd_offset + 4 * 8)
            _cert_offset, cert_size = struct.unpack("<II", f.read(8))
            return cert_size > 0
    except (OSError, struct.error):
        return False


def cmd_sign_tree(args):
    """批量签名目录树下的所有可执行文件（.exe / .dll / .pyd）。

    背景：PyInstaller 产物里的 Python 扩展模块（.pyd）不带 Authenticode
    签名。在启用了 Windows 应用控制策略（WDAC/AppLocker）的机器上，
    未签名的 .pyd 会被系统直接拦截，导致「DLL load failed ... 应用程序
    控制策略已阻止此文件」。因此发布前必须对产物逐个签名。

    已由原厂签名的文件（Qt 官方 DLL 等）会被跳过，保留其原有签名。
    """
    signtool = find_signtool()
    if not signtool:
        print("❌ 未找到 signtool.exe，请安装 Windows SDK")
        return 1
    if not os.path.isdir(args.directory):
        print(f"❌ 目录不存在: {args.directory}")
        return 1

    # 1) 收集目标文件并检查签名状态
    targets = []
    for dirpath, _dirnames, filenames in os.walk(args.directory):
        for fn in filenames:
            if fn.lower().endswith((".exe", ".dll", ".pyd")):
                targets.append(os.path.join(dirpath, fn))
    if not targets:
        print("目录下没有需要签名的文件")
        return 0

    unsigned = [t for t in targets if not _pe_has_signature(t)]
    print(f"扫描到 {len(targets)} 个可执行文件")
    print(f"已有签名（跳过）: {len(targets) - len(unsigned)} 个")
    print(f"待签名: {len(unsigned)} 个")

    if not unsigned:
        return 0

    # 2) 逐个签名
    ok, failed = 0, 0
    for i, f in enumerate(unsigned, 1):
        cmd = [signtool, "sign"]
        if args.pfx:
            cmd += ["/f", args.pfx]
            if args.password:
                cmd += ["/p", args.password]
        else:
            cmd += ["/a"]
        cmd += ["/fd", "SHA256", "/tr", args.timestamp, "/td", "SHA256", "/v", f]
        rr = run(cmd)
        if rr.returncode == 0:
            ok += 1
        else:
            failed += 1
            print(f"  ✗ 签名失败: {f}")
            if rr.stderr:
                print("    " + rr.stderr.strip().splitlines()[-1])
        if i % 25 == 0:
            print(f"  ...进度 {i}/{len(unsigned)}")

    print(f"\n✅ 签名完成：成功 {ok}，失败 {failed}")
    return 0 if failed == 0 else 1


def cmd_verify(args):
    """验证 Authenticode 签名。"""
    signtool = find_signtool()
    if not signtool:
        print("❌ 未找到 signtool.exe")
        return 1
    r = run([signtool, "verify", "/pa", "/v", args.file])
    print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip())
    return r.returncode


def main():
    parser = argparse.ArgumentParser(description="Windows Authenticode 签名工具")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("check", help="检查签名工具与证书")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("selfsign", help="生成自签证书（本机测试）")
    p.add_argument("--password", default="ycbuild", help="PFX 密码")
    p.set_defaults(func=cmd_selfsign)

    p = sub.add_parser("sign", help="签名文件")
    p.add_argument("file")
    p.add_argument("--pfx", help="PFX 证书路径（省略则自动选证书库中的证书）")
    p.add_argument("--password", help="PFX 密码")
    p.add_argument("--name", help="按使用者名选择证书")
    p.add_argument("--timestamp", default=DEFAULT_TIMESTAMP_URL, help="RFC3161 时间戳服务器")
    p.set_defaults(func=cmd_sign)

    p = sub.add_parser("verify", help="验证签名")
    p.add_argument("file")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("sign-tree", help="批量签名目录下的 .exe/.dll/.pyd")
    p.add_argument("directory")
    p.add_argument("--pfx", help="PFX 证书路径（省略则自动选证书库中的证书）")
    p.add_argument("--password", help="PFX 密码")
    p.add_argument("--timestamp", default=DEFAULT_TIMESTAMP_URL, help="RFC3161 时间戳服务器")
    p.set_defaults(func=cmd_sign_tree)

    args = parser.parse_args()
    if not getattr(args, "func", None):
        args = parser.parse_args(["check"])
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
