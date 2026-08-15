"""DDW Client-Side License Validator（客户端许可证验证器，v2 Ed25519）。

功能：
1. 读取本地许可证缓存文件（license_cache.json）
2. 用 Ed25519 公钥验签（客户端只持有公钥，无任何可签名密钥）
3. 检查有效期
4. 校验机器指纹绑定（许可证与当前机器匹配）
5. 返回已授权的插件列表
6. 支持离线模式（管理端不可达时使用缓存）

安全要点（P0 三件套）：
- 对称 HMAC → 非对称 Ed25519：客户端无法自签
- 验证失败 fail-closed（由 core/main.load_plugins 门控，本模块只返回结果）
- license 绑定机器指纹：整套部署拷走也无法换机使用

许可证文件格式（license_cache.json, format v2）：
{
  "license_key": "LIC-20260803-001",
  "customer": "武汉锐果互动信息技术有限公司",
  "instance_id": "16G-Mac-mini-M4",
  "machine_fingerprint": "32位hex指纹",
  "valid_from": "2026-08-03",
  "valid_to": "2027-08-03",
  "authorized_plugins": ["ddw-license-core", "ddw-instance-binding", ...],
  "issued_by": "DDW-Admin",
  "issued_at": "2026-08-03T10:00:00+00:00",
  "license_format_version": 2,
  "sig_algo": "ed25519",
  "signature": "base64(64字节Ed25519签名)"
}

公钥解析顺序（客户端）：
1. validate_license_file(public_key=...) 显式传入
2. 环境变量 DDW_LICENSE_PUBLIC_KEY（base64）
3. deployment.yaml 的 license.public_key（base64）

安全要求（对抗性验证加固）：未配置任何公钥 → 验签直接失败并给出明确报错
（"未配置许可证公钥"），绝不回退到内置占位公钥（避免"忘配公钥但验签静默
失败/行为不明"）。未配置公钥的部署只能使用免费插件（fail-closed）。
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.utils.machine_fingerprint import get_machine_fingerprint

logger = logging.getLogger(__name__)

# 许可证格式版本：v1=HMAC-SHA256（已废弃），v2=Ed25519
LICENSE_FORMAT_VERSION = 2

# P1 宽限期：license 到期后仍可用的天数（信息/UI 层，load_plugins 授权行为不变）
GRACE_PERIOD_DAYS = 30
# P1 提前警告：到期前多少天开始 UI 黄色警告
LICENSE_WARN_AHEAD_DAYS = 30

# 公钥未配置时的报错文案（fail-closed，拒绝静默回退）
PUBLIC_KEY_MISSING_MESSAGE = (
    "未配置许可证公钥（DDW_LICENSE_PUBLIC_KEY 或 deployment.yaml "
    "license.public_key），无法验签"
)

_HEXDIGITS = set("0123456789abcdefABCDEF")

# 旧格式（HMAC-SHA256）签名特征：64 位 hex
_OLD_SIG_LEN = 64


def _looks_like_old_hmac(data: Dict[str, Any]) -> bool:
    """旧格式（HMAC v1）检测：无 sig_algo 标记且签名为 64 位 hex。"""
    if data.get("sig_algo"):
        return False
    sig = data.get("signature", "")
    if not isinstance(sig, str):
        return False
    if len(sig) != _OLD_SIG_LEN:
        return False
    return all(c in _HEXDIGITS for c in sig)


def _load_public_key(
    public_key: Union[str, bytes, Ed25519PublicKey, None],
) -> Ed25519PublicKey:
    """解析 Ed25519 公钥：显式参数 → 环境变量 → deployment.yaml。

    Raises:
        ValueError: 未配置任何公钥（fail-closed，绝不回退占位公钥）。
    """
    if isinstance(public_key, Ed25519PublicKey):
        return public_key
    if isinstance(public_key, bytes):
        return Ed25519PublicKey.from_public_bytes(public_key)
    if isinstance(public_key, str):
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))

    env_key = os.environ.get("DDW_LICENSE_PUBLIC_KEY", "").strip()
    if env_key:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(env_key))

    try:
        from core.config import get_settings

        cfg = get_settings().raw.get("license", {})
        cfg_key = str(cfg.get("public_key", "") or "").strip()
        if cfg_key:
            return Ed25519PublicKey.from_public_bytes(base64.b64decode(cfg_key))
    except Exception as e:  # noqa: BLE001  # 配置读取失败按未配置处理（fail-closed）
        logger.warning(
            "license validator: failed to read license.public_key from settings: %s", e
        )

    raise ValueError(PUBLIC_KEY_MISSING_MESSAGE)


def _canonical_message(data: Dict[str, Any]) -> bytes:
    """签名/验签的规范化消息：全字段（排除 signature）排序后 JSON 序列化。"""
    sign_data = {k: v for k, v in data.items() if k != "signature"}
    return json.dumps(sign_data, sort_keys=True, ensure_ascii=False).encode("utf-8")


def validate_license_file(
    license_path: str | Path,
    public_key: Union[str, bytes, Ed25519PublicKey, None] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """验证本地许可证文件。

    Returns:
        (is_valid, reason, license_data)
    """
    path = Path(license_path)

    if not path.exists():
        return False, "许可证文件不存在", {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return False, f"许可证文件读取失败: {e}", {}
    if not isinstance(data, dict):
        return False, "许可证文件格式错误（应为 JSON 对象）", {}

    # 旧格式（HMAC）检测：不静默通过、也不放行
    if _looks_like_old_hmac(data):
        return False, "许可证格式过旧，请联系锐果换发", data

    # 验签（Ed25519）
    signature_b64 = data.get("signature", "")
    if not signature_b64:
        return False, "许可证缺少签名（可能被篡改）", data
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError):
        return False, "许可证签名格式错误", data
    try:
        pub = _load_public_key(public_key)
        pub.verify(signature, _canonical_message(data))
    except ValueError as e:
        # 未配置公钥：明确报错（fail-closed），不静默
        return False, str(e), data
    except InvalidSignature:
        return False, "许可证签名验证失败（可能被篡改）", data

    # 验证有效期
    valid_to_str = data.get("valid_to", "")
    try:
        valid_to = date.fromisoformat(valid_to_str)
        if date.today() > valid_to:
            return False, f"许可证已过期（有效期至 {valid_to_str}）", data
    except (ValueError, TypeError):
        return False, f"许可证有效期格式错误: {valid_to_str}", data

    valid_from_str = data.get("valid_from", "")
    try:
        valid_from = date.fromisoformat(valid_from_str)
        if date.today() < valid_from:
            return False, f"许可证尚未生效（生效日期 {valid_from_str}）", data
    except (ValueError, TypeError):
        pass  # valid_from 是可选的

    # 验证实例ID（非空）
    instance_id = data.get("instance_id", "")
    if not instance_id:
        return False, "许可证缺少实例ID", data

    # 验证机器指纹绑定
    bound_fingerprint = data.get("machine_fingerprint", "")
    if not bound_fingerprint:
        return False, "许可证缺少机器指纹", data
    if bound_fingerprint != get_machine_fingerprint():
        return False, "许可证与当前机器不匹配，如需迁移请联系锐果", data

    return True, "许可证验证通过", data


def get_authorized_plugins(license_data: Dict[str, Any]) -> List[str]:
    """从许可证数据中提取已授权的插件列表。"""
    return license_data.get("authorized_plugins", [])


def is_plugin_authorized(license_data: Dict[str, Any], plugin_name: str) -> bool:
    """检查指定插件是否被授权（"*" 表示全部授权）。"""
    authorized = get_authorized_plugins(license_data)
    if "*" in authorized:
        return True
    return plugin_name in authorized


def _default_license_path() -> Path:
    """默认 license 缓存路径（与 core/main.load_plugins 的读取方式一致）。"""
    try:
        from core.config import get_settings

        raw = get_settings().raw.get("license", {})
        cache = raw.get("cache_path", "./data/license_cache.json")
    except Exception:  # noqa: BLE001  # 配置读取失败时用默认路径
        cache = "./data/license_cache.json"
    return Path(cache)


def _parse_valid_to(data: Dict[str, Any]) -> Optional[date]:
    """解析 license 中的 valid_to 日期；格式非法返回 None。"""
    raw = data.get("valid_to", "")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None


def evaluate_license(
    license_path: Optional[str | Path] = None,
    public_key: Union[str, bytes, Ed25519PublicKey, None] = None,
) -> Dict[str, Any]:
    """评估本地许可证状态（P1：宽限期 / 提前警告）。

    返回：{
        "licensed": bool,
        "customer": str | None,
        "license_code": str | None,
        "valid_to": "YYYY-MM-DD" | None,
        "days_left": int | None,          # 负数=已过期天数（宽限期内）
        "in_grace_period": bool,          # 到期后 ≤30 天宽限期
        "warning_level": "none"|"soon"|"grace"|"invalid",
    }

    注意：宽限期仅作用于信息/UI 层；``load_plugins`` 的授权过滤（P0 fail-closed）
    行为保持不变。
    """
    path = Path(license_path) if license_path is not None else _default_license_path()
    is_valid, reason, data = validate_license_file(path, public_key)

    base = {
        "licensed": False,
        "customer": data.get("customer"),
        "license_code": data.get("license_key"),
        "valid_to": data.get("valid_to"),
        "days_left": None,
        "in_grace_period": False,
        "warning_level": "invalid",
    }

    if is_valid:
        valid_to = _parse_valid_to(data)
        days_left = (valid_to - date.today()).days if valid_to else None
        soon = days_left is not None and days_left <= LICENSE_WARN_AHEAD_DAYS
        warning = "soon" if soon else "none"
        return {
            **base,
            "licensed": True,
            "days_left": days_left,
            "warning_level": warning,
        }

    # 无效：仅当原因是“已过期”且落在宽限期内时，信息层仍视为可用
    if "已过期" in reason:
        valid_to = _parse_valid_to(data)
        if valid_to is not None:
            days_over = (date.today() - valid_to).days
            if 0 <= days_over <= GRACE_PERIOD_DAYS:
                logger.warning(
                    "license in grace period customer=%s valid_to=%s days_over=%d",
                    data.get("customer"),
                    valid_to.isoformat(),
                    days_over,
                )
                return {
                    **base,
                    "licensed": True,  # 宽限期内可用（UI 红色警告）
                    "days_left": -days_over,
                    "in_grace_period": True,
                    "warning_level": "grace",
                }
    return base


__all__ = [
    "LICENSE_FORMAT_VERSION",
    "GRACE_PERIOD_DAYS",
    "LICENSE_WARN_AHEAD_DAYS",
    "validate_license_file",
    "evaluate_license",
    "get_authorized_plugins",
    "is_plugin_authorized",
]
