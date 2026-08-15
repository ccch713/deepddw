"""设备绑定验证（DDW AI Hub v5.4 — 安全加固）。

admin 角色登录时额外验证设备指纹，防止未授权设备访问管理后台。
设备白名单通过配置或环境变量管理。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 设备白名单（可通过环境变量 DDW_ADMIN_DEVICE_WHITELIST 覆盖）
# ---------------------------------------------------------------------------

ADMIN_DEVICE_WHITELIST: Dict[str, Dict[str, Any]] = {
    "32G-Mac-mini": {
        "serial": "D9CXVC9Q5L",
        "screen_hints": ["2560x1440", "1920x1080"],
    },
    "128G-MBP": {
        "serial": "C7M6MG97JL",
        "screen_hints": ["3456x2234", "2560x1600", "1728x1117"],
    },
}


def get_device_whitelist() -> Dict[str, Dict[str, Any]]:
    """读取设备白名单。优先从环境变量读取 JSON，否则用硬编码。"""
    env = os.environ.get("DDW_ADMIN_DEVICE_WHITELIST")
    if env:
        import json

        try:
            return json.loads(env)
        except json.JSONDecodeError:
            logger.warning("invalid DDW_ADMIN_DEVICE_WHITELIST JSON, using defaults")
    return ADMIN_DEVICE_WHITELIST


def _match_device(fp: Dict[str, Any], device_info: Dict[str, Any]) -> bool:
    """设备匹配逻辑。

    匹配条件（任一满足即可）：
    1. serial_number 完全匹配
    2. screen_resolution 在 screen_hints 中
    """
    # serial 匹配
    fp_serial = fp.get("serial_number") or fp.get("serial")
    if fp_serial and fp_serial == device_info.get("serial"):
        return True

    # 屏幕分辨率匹配
    fp_screen = fp.get("screen_resolution") or fp.get("screen")
    hints = device_info.get("screen_hints", [])
    if fp_screen and fp_screen in hints:
        return True

    return False


def verify_device(
    fingerprint: Dict[str, Any],
    phone: Optional[str] = None,
) -> Tuple[bool, str]:
    """验证设备是否在白名单中。

    Args:
        fingerprint: 设备指纹 dict，包含 serial_number / screen_resolution 等
        phone: 用户手机号（用于日志）

    Returns:
        (ok, reason) 元组
    """
    if not fingerprint:
        return False, "缺少设备指纹"

    whitelist = get_device_whitelist()
    for name, info in whitelist.items():
        if _match_device(fingerprint, info):
            logger.info("device verified: phone=%s device=%s", phone, name)
            return True, f"匹配设备: {name}"

    logger.warning("device verification failed: phone=%s fp=%s", phone, fingerprint)
    return False, "设备不在白名单中"


def verify_user_device(
    user: Any,
    fingerprint: Dict[str, Any],
) -> Tuple[bool, str]:
    """账号级设备验证（红线）。

    逻辑：
    1. user.device_required 为 False → 直接放行
    2. user.device_allowlist 存在且非空 → 只匹配 allowlist
    3. 否则回退全局 ADMIN_DEVICE_WHITELIST

    Args:
        user: User ORM 对象（需 device_required / device_allowlist 字段）
        fingerprint: 设备指纹 dict

    Returns:
        (ok, reason) 元组
    """
    # 1. 无设备限制 → 放行
    if not getattr(user, "device_required", False):
        return True, "no device restriction"

    # 2. 检查用户级 allowlist
    allowlist = getattr(user, "device_allowlist", None)
    if allowlist and isinstance(allowlist, dict):
        for name, info in allowlist.items():
            if _match_device(fingerprint, info):
                logger.info("user device verified: phone=%s device=%s", user.phone, name)
                return True, f"匹配用户设备: {name}"
        logger.warning("user device verification failed: phone=%s fp=%s", user.phone, fingerprint)
        return False, "设备不在用户允许列表中"

    # 3. 回退全局白名单
    return verify_device(fingerprint, phone=getattr(user, "phone", None))


__all__ = ["ADMIN_DEVICE_WHITELIST", "get_device_whitelist", "verify_device", "verify_user_device"]
