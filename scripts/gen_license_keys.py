#!/usr/bin/env python3
"""生成 Ed25519 许可证签发密钥对（仅发证端使用，严禁分发私钥）。

用法：
    python scripts/gen_license_keys.py [--output-dir ./license_keys]

产物：
    license_signing_private_key.pem   私钥（权限 600，*.pem 已被 .gitignore 忽略）
    license_public_key.pem            公钥（权限 644）

输出 base64 公钥，发证/部署时配置到客户端：
- 环境变量 DDW_LICENSE_PUBLIC_KEY（base64）
- 或 deployment.yaml 的 license.public_key（base64）

私钥仅供 scripts/issue_license.py 发证使用；私钥一旦泄露，
请立即重新生成密钥对并换发全部许可证。
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PRIVATE_KEY_NAME = "license_signing_private_key.pem"
PUBLIC_KEY_NAME = "license_public_key.pem"


def generate_keypair(output_dir: Path, overwrite: bool = False) -> Path:
    """生成 Ed25519 密钥对，私钥权限 600。返回私钥文件路径。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    private_path = output_dir / PRIVATE_KEY_NAME
    public_path = output_dir / PUBLIC_KEY_NAME

    for p in (private_path, public_path):
        if p.exists() and not overwrite:
            print(f"[skip] {p} 已存在（如需覆盖请加 --overwrite）")
            continue

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    if not private_path.exists() or overwrite:
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        private_path.write_bytes(private_pem)
        os.chmod(private_path, 0o600)
        print(f"[write] 私钥 → {private_path} (chmod 600)")
    else:
        print(f"[skip] 私钥 {private_path} 已存在，未覆盖")

    if not public_path.exists() or overwrite:
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_path.write_bytes(public_pem)
        os.chmod(public_path, 0o644)
        print(f"[write] 公钥 → {public_path}")
    else:
        print(f"[skip] 公钥 {public_path} 已存在，未覆盖")

    public_b64 = base64.b64encode(public_key.public_bytes_raw()).decode()
    print()
    print("=" * 70)
    print("base64 公钥（配置到客户端）：")
    print(public_b64)
    print("=" * 70)
    print("客户端配置方式：")
    print("  export DDW_LICENSE_PUBLIC_KEY=<上面的 base64 公钥>")
    print("  或 deployment.yaml: license.public_key: <上面的 base64 公钥>")
    print()
    print("⚠ 私钥文件请妥善保管，切勿提交 git / 分发到客户端。")
    return private_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="生成 Ed25519 许可证签发密钥对（发证端专用）"
    )
    parser.add_argument(
        "--output-dir",
        default="./license_keys",
        help="密钥输出目录（默认 ./license_keys，已被 .gitignore 忽略）",
    )
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的密钥文件")
    args = parser.parse_args()

    try:
        generate_keypair(Path(args.output_dir), overwrite=args.overwrite)
    except OSError as e:
        print(f"[error] 密钥生成失败: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
