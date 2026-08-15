#!/usr/bin/env python3
"""打包并签名 DDW 插件为 .ddwplugin 包（P1 插件签名）。

用法：
    python scripts/package_plugin.py \
        --src plugins/ddw_my_plugin \
        --private-key ./license_keys/license_signing_private_key.pem \
        --output ./dist/ddw_my_plugin.ddwplugin

说明：
- 包为 zip：含 manifest.yaml + 插件代码 + .ddwplugin.sig（Ed25519 签名）。
- 签名对象 = 包内全部文件（相对路径:sha256 清单），任何文件被改都会验签失败。
- 私钥复用 ``scripts/gen_license_keys.py`` 生成的 Ed25519 密钥对（发证端持有）；
  安装端需配置公钥：export DDW_PLUGIN_SIGNING_PUBLIC_KEY=<base64 公钥>
- 安装验签：core/plugin_manager/installer.install_from_package()
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.plugin_manager.installer import sign_package  # noqa: E402


def load_signing_key(private_key_path: Path) -> Ed25519PrivateKey:
    """加载 Ed25519 私钥（PEM，未加密）。"""
    private_key_path = Path(private_key_path)
    if not private_key_path.exists():
        raise FileNotFoundError(f"私钥文件不存在: {private_key_path}")
    try:
        key = serialization.load_pem_private_key(
            private_key_path.read_bytes(), password=None
        )
    except ValueError as e:
        raise ValueError(
            f"私钥文件解析失败（应为未加密 PKCS8 PEM）: {e}"
        ) from e
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError(
            "私钥不是 Ed25519 密钥，请用 scripts/gen_license_keys.py 重新生成"
        )
    return key


def main() -> int:
    parser = argparse.ArgumentParser(
        description="打包并签名 DDW 插件为 .ddwplugin 包"
    )
    parser.add_argument(
        "--src", required=True, help="插件目录（含 manifest.yaml + 代码）"
    )
    parser.add_argument("--private-key", required=True, help="Ed25519 私钥 PEM 路径")
    parser.add_argument("--output", required=True, help="输出 .ddwplugin 文件路径")
    args = parser.parse_args()

    try:
        private_key = load_signing_key(Path(args.private_key))
        out = sign_package(Path(args.src), private_key, Path(args.output))
    except (OSError, ValueError, TypeError) as e:
        print(f"[error] 打包签名失败: {e}", file=sys.stderr)
        return 1

    print(f"[write] 签名插件包 → {out}")
    print("[info] 安装端配置：export DDW_PLUGIN_SIGNING_PUBLIC_KEY=<base64 公钥>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
