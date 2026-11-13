"""生成规范的两级 PKI：根 CA（CA:TRUE）+ 代码签名叶证书。

为什么需要两级
--------------
当前的 yc-signing.pfx 是**自签名**证书（Subject == Issuer，无 BasicConstraints）。
Authenticode 的 Get-AuthenticodeSignature 判它为 Valid（因为本机 Root 存储里有它），
但 WDAC / Smart App Control 的 "Enterprise signing level" 判定要求签名链满足
更严格的规则，其中最关键的一条是：

    签名证书必须由一个**真正的 CA**（BasicConstraints CA:TRUE）签发，
    即链长至少为 2（叶 -> CA -> 根），而不是叶本身就是根。

本脚本生成：
  1. YcBrowser Root CA    —— 自签、CA:TRUE、带 KeyCertSign
  2. YcBrowser Code Sign —— 由 Root CA 签发、CA:FALSE、带 Code Signing EKU

用法：
  python tools/make_pki.py --out installer/pki --password ycbuild
"""
import argparse
import datetime
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _name(cn: str, org: str) -> x509.Name:
    return x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
    ])


def build(out_dir: str, password: str, days: int = 3650):
    os.makedirs(out_dir, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc)
    # 留一点回溯余量，避免因时钟偏差导致签名被判为"尚未生效"
    start = now - datetime.timedelta(days=1)
    end = now + datetime.timedelta(days=days)

    # ---------- 根 CA ----------
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    root_name = _name("YcBrowser Root CA", "Yc Browser")
    root_pub = root_key.public_key()

    root_cert = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_pub)
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(root_pub),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )

    # ---------- 叶证书（代码签名） ----------
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    leaf_name = _name("YcBrowser Code Signing", "Yc Browser")
    leaf_pub = leaf_key.public_key()

    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(root_name)
        .public_key(leaf_pub)
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(leaf_pub),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_pub),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )

    # ---------- 落盘 ----------
    root_pfx = os.path.join(out_dir, "yc-root-ca.pfx")
    leaf_pfx = os.path.join(out_dir, "yc-code-signing.pfx")
    root_cer = os.path.join(out_dir, "yc-root-ca.cer")

    def _write_pfx(path, key, cert, extra=()):
        # PKCS12 规范要求私钥与证书一同封装（signtool 依赖这一点来定位证书链）
        blob = pkcs12.serialize_key_and_certificates(
            name=cert.subject.rfc4514_string().encode("utf-8"),
            key=key,
            cert=cert,
            cas=list(extra),
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
        )
        with open(path, "wb") as f:
            f.write(blob)
        with open(path.replace(".pfx", ".pem"), "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(path.replace(".pfx", ".cer"), "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.DER))

    _write_pfx(root_pfx, root_key, root_cert)
    _write_pfx(path=leaf_pfx, key=leaf_key, cert=leaf_cert, extra=(root_cert,))

    with open(root_cer, "wb") as f:
        f.write(root_cert.public_bytes(serialization.Encoding.PEM))

    print("根 CA  :", root_pfx)
    print("  Subject:", root_cert.subject.rfc4514_string())
    print("  Thumb :", root_cert.fingerprint(hashes.SHA256()).hex().upper())
    print("叶证书 :", leaf_pfx)
    print("  Subject:", leaf_cert.subject.rfc4514_string())
    print("  Issuer :", leaf_cert.issuer.rfc4514_string())
    print("  Thumb :", leaf_cert.fingerprint(hashes.SHA256()).hex().upper())
    print("根证书 PEM:", root_cer)
    return root_cert, leaf_cert


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="installer/pki")
    ap.add_argument("--password", default="ycbuild")
    ap.add_argument("--days", type=int, default=3650)
    args = ap.parse_args()
    build(args.out, args.password, args.days)
