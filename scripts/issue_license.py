#!/usr/bin/env python3
"""签发 DDW 许可证文件（v2，Ed25519 签名，仅发证端使用）。

用法：
    python scripts/issue_license.py \\
        --private-key ./license_keys/license_signing_private_key.pem \\
        --license-key LIC-20260803-001 \\
        --customer "武汉锐果互动信息技术有限公司" \\
        --instance-id 16G-Mac-mini-M4 \\
        --machine-fingerprint <32位hex，省略则自动采集本机指纹> \\
        --valid-days 365 \\
        --authorized-plugins ddw-license-core,ddw-instance-binding \\
        --output ./data/license_cache.json

说明：
- 私钥仅发证端持有；客户端只验签（DDW_LICENSE_PUBLIC_KEY）。
- machine_fingerprint 用于绑定目标机器：可在目标机器上执行
  python -c "from core.utils.machine_fingerprint import get_machine_fingerprint;
  print(get_machine_fingerprint())"
  采集后传入；不传则默认绑定运行本脚本的机器。
- 输出文件含 license_format_version=2 / sig_algo=ed25519 标记，
  客户端据此识别旧 HMAC 格式（"许可证格式过旧，请联系锐果换发"）。
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# 允许 scripts/ 直接以仓库根运行（from core.utils import ...）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.utils.license_validator import LICENSE_FORMAT_VERSION  # noqa: E402


def load_private_key(private_key_path: Path) -> Ed25519PrivateKey:
    """从 PEM 文件加载 Ed25519 私钥。"""
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


def issue_license(
    private_key: Ed25519PrivateKey,
    license_key: str,
    customer: str,
    instance_id: str,
    machine_fingerprint: str,
    valid_days: int,
    authorized_plugins: List[str],
    issued_by: str = "DDW-Admin",
) -> dict:
    """构造许可证载荷并 Ed25519 签名，返回完整 license 字典。"""
    if valid_days <= 0:
        raise ValueError("valid_days 必须为正整数")
    if not machine_fingerprint:
        raise ValueError(
            "machine_fingerprint 不能为空（--machine-fingerprint 或自动采集）"
        )
    if not license_key or not customer or not instance_id:
        raise ValueError("license_key / customer / instance_id 均不能为空")

    today = date.today()
    valid_to = date.fromordinal(today.toordinal() + valid_days)

    payload = {
        "license_key": license_key,
        "customer": customer,
        "instance_id": instance_id,
        "machine_fingerprint": machine_fingerprint,
        "valid_from": today.isoformat(),
        "valid_to": valid_to.isoformat(),
        "authorized_plugins": list(authorized_plugins) or ["*"],
        "issued_by": issued_by,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "license_format_version": LICENSE_FORMAT_VERSION,
        "sig_algo": "ed25519",
    }

    # 规范化消息与客户端验签保持一致：
    # 排除 signature 字段，sort_keys + ensure_ascii=False
    sign_data = {k: v for k, v in payload.items() if k != "signature"}
    message = json.dumps(sign_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    signature = private_key.sign(message)
    payload["signature"] = base64.b64encode(signature).decode()

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="签发 DDW 许可证文件（Ed25519 v2，发证端专用）"
    )
    parser.add_argument(
        "--private-key",
        required=True,
        help="Ed25519 私钥 PEM 路径（gen_license_keys.py 生成）",
    )
    parser.add_argument(
        "--license-key", required=True, help="许可证号，如 LIC-20260803-001"
    )
    parser.add_argument("--customer", required=True, help="客户名称")
    parser.add_argument("--instance-id", required=True, help="实例ID（目标部署标识）")
    parser.add_argument(
        "--machine-fingerprint",
        default=None,
        help="目标机器指纹（32位hex）；省略则采集本机指纹",
    )
    parser.add_argument(
        "--valid-days", type=int, default=365, help="有效期天数（默认 365）"
    )
    parser.add_argument(
        "--authorized-plugins",
        default="",
        help="授权插件列表，逗号分隔；空=全部（*）",
    )
    parser.add_argument("--issued-by", default="DDW-Admin", help="签发方标识")
    parser.add_argument(
        "--output",
        default="./data/license_cache.json",
        help="许可证输出路径（默认 ./data/license_cache.json）",
    )
    args = parser.parse_args()

    try:
        private_key = load_private_key(Path(args.private_key))

        machine_fingerprint = args.machine_fingerprint
        if not machine_fingerprint:
            from core.utils.machine_fingerprint import get_machine_fingerprint

            machine_fingerprint = get_machine_fingerprint()
            print(
                f"[info] 未指定 --machine-fingerprint，已采集本机指纹: "
                f"{machine_fingerprint}"
            )

        authorized_plugins = [
            p.strip() for p in args.authorized_plugins.split(",") if p.strip()
        ]
        payload = issue_license(
            private_key=private_key,
            license_key=args.license_key,
            customer=args.customer,
            instance_id=args.instance_id,
            machine_fingerprint=machine_fingerprint,
            valid_days=args.valid_days,
            authorized_plugins=authorized_plugins,
            issued_by=args.issued_by,
        )
    except (OSError, ValueError, TypeError) as e:
        print(f"[error] 发证失败: {e}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"[write] 许可证 → {output}")
    print(
        f"[info] 客户: {payload['customer']} / 有效期至: {payload['valid_to']} / "
        f"授权插件: {payload['authorized_plugins']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
