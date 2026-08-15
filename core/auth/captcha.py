"""图片验证码生成/校验（DDW AI Hub 登录安全闭环）。

验证码字符集：23456789ABCDEFGHJKLMNPQRSTUVWXYZ（去 0/O/1/I/L/S/5/Z/2 混淆对）。
存储：Redis 优先（ddw:captcha:{captcha_id} TTL 120s），不可用降级内存 dict。
限流：L0 验证码错误计数（ddw:captcha_fail:{ip}:{captcha_id}），连续 3 次错误 → 该 id 作废 + 同 IP 60s 拒绝换码。
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import os
import time
import uuid
from typing import Optional, Tuple

from captcha.image import ImageCaptcha

logger = logging.getLogger(__name__)

# 验证码字符集（去混淆对：0/O/1/I/L/S/5/Z/2）
CAPTCHA_CHARS = "346789ABCDEFGHJKMNPQRTUVWXY"
CAPTCHA_LENGTH = 4
CAPTCHA_TTL = 120  # 秒
CAPTCHA_WIDTH = 130
CAPTCHA_HEIGHT = 42

# L0 限流：连续 3 次错误 → 该 captcha_id 作废
MAX_CAPTCHA_FAILS = 3
# 同 IP 60s 内拒绝换码（验证码错误后）
CAPTCHA_FAIL_COOLDOWN = 60

# ---------------------------------------------------------------------------
# Redis 连接复用 auth.py 的 _get_redis
# ---------------------------------------------------------------------------
_redis_failed_logged = False


def _get_redis():
    """惰性连接 Redis；复用 core.api.auth 的连接。"""
    global _redis_failed_logged
    try:
        from core.api.auth import _get_redis as _auth_get_redis
        return _auth_get_redis()
    except Exception:
        if not _redis_failed_logged:
            logger.warning("captcha redis unavailable, using in-memory store")
            _redis_failed_logged = True
        return None


# ---------------------------------------------------------------------------
# 内存验证码存储（Redis 不可用时降级）
# ---------------------------------------------------------------------------
_CAPTCHA_STORE: dict[str, tuple[str, float]] = {}  # captcha_id -> (code, expire_ts)
_CAPTCHA_FAIL_STORE: dict[str, tuple[int, float]] = {}  # key -> (count, expire_ts)
_CAPTCHA_IP_COOLDOWN: dict[str, float] = {}  # ip -> expire_ts


def _redis_key(captcha_id: str) -> str:
    return f"ddw:captcha:{captcha_id}"


def _redis_fail_key(ip: str, captcha_id: str) -> str:
    return f"ddw:captcha_fail:{ip}:{captcha_id}"


def _redis_ip_cooldown_key(ip: str) -> str:
    return f"ddw:captcha_cooldown:{ip}"


def generate_captcha() -> Tuple[str, str, int]:
    """生成验证码图片。

    Returns:
        (captcha_id, image_base64, expires_in) 元组
    """
    captcha_id = uuid.uuid4().hex
    # 生成随机验证码
    code = "".join(
        CAPTCHA_CHARS[ord(os.urandom(1)) % len(CAPTCHA_CHARS)]
        for _ in range(CAPTCHA_LENGTH)
    )

    # 生成图片
    image_captcha = ImageCaptcha(width=CAPTCHA_WIDTH, height=CAPTCHA_HEIGHT)
    image_data = image_captcha.generate(code)
    image_bytes = image_data.getvalue()
    image_base64 = "data:image/png;base64," + base64.b64encode(image_bytes).decode("utf-8")

    # 存储验证码
    _store_captcha(captcha_id, code)

    return captcha_id, image_base64, CAPTCHA_TTL


def _store_captcha(captcha_id: str, code: str) -> None:
    """存储验证码：Redis + 内存双写。"""
    expire_at = time.time() + CAPTCHA_TTL
    _CAPTCHA_STORE[captcha_id] = (code, expire_at)

    r = _get_redis()
    if r is not None:
        try:
            r.setex(_redis_key(captcha_id), CAPTCHA_TTL, code)
        except Exception as exc:
            logger.warning("captcha redis setex failed: %s", exc)


def verify_captcha(
    captcha_id: str,
    captcha_code: str,
    ip: Optional[str] = None,
) -> Tuple[bool, str]:
    """校验验证码。

    Args:
        captcha_id: 验证码 ID
        captcha_code: 用户输入的验证码
        ip: 客户端 IP（用于 L0 限流）

    Returns:
        (ok, reason) 元组
    """
    # 检查 IP 冷却期
    if ip and _is_ip_cooldown(ip):
        return False, "验证码错误次数过多，请稍后再试"

    # 检查 captcha_id 是否有效
    code = _get_stored_code(captcha_id)
    if code is None:
        return False, "验证码错误或已过期"

    # 检查失败次数（L0 限流）
    if ip:
        fail_count = _get_fail_count(ip, captcha_id)
        if fail_count >= MAX_CAPTCHA_FAILS:
            _invalidate_captcha(captcha_id)
            _set_ip_cooldown(ip)
            return False, "验证码错误次数过多，请稍后再试"

    # 校验验证码（不区分大小写）
    if captcha_code.upper() != code.upper():
        # 记录失败
        if ip:
            _increment_fail_count(ip, captcha_id)
        return False, "验证码错误或已过期"

    # 校验成功，清除验证码
    _invalidate_captcha(captcha_id)
    return True, "ok"


def _get_stored_code(captcha_id: str) -> Optional[str]:
    """获取存储的验证码。Redis 优先，内存兜底。"""
    r = _get_redis()
    if r is not None:
        try:
            stored = r.get(_redis_key(captcha_id))
            if stored is not None:
                return stored.decode("utf-8")
        except Exception as exc:
            logger.warning("captcha redis get failed: %s", exc)

    # 内存兜底
    rec = _CAPTCHA_STORE.get(captcha_id)
    if rec is None:
        return None
    code, expire_at = rec
    if time.time() > expire_at:
        _CAPTCHA_STORE.pop(captcha_id, None)
        return None
    return code


def _invalidate_captcha(captcha_id: str) -> None:
    """清除验证码。"""
    _CAPTCHA_STORE.pop(captcha_id, None)
    r = _get_redis()
    if r is not None:
        try:
            r.delete(_redis_key(captcha_id))
        except Exception:
            pass


def _get_fail_count(ip: str, captcha_id: str) -> int:
    """获取失败计数。"""
    key = f"{ip}:{captcha_id}"
    r = _get_redis()
    if r is not None:
        try:
            count = r.get(_redis_fail_key(ip, captcha_id))
            if count is not None:
                return int(count)
        except Exception:
            pass

    # 内存兜底
    rec = _CAPTCHA_FAIL_STORE.get(key)
    if rec is None:
        return 0
    count, expire_at = rec
    if time.time() > expire_at:
        _CAPTCHA_FAIL_STORE.pop(key, None)
        return 0
    return count


def _increment_fail_count(ip: str, captcha_id: str) -> None:
    """递增失败计数。"""
    key = f"{ip}:{captcha_id}"
    r = _get_redis()
    if r is not None:
        try:
            redis_key = _redis_fail_key(ip, captcha_id)
            n = r.incr(redis_key)
            if n == 1:
                r.expire(redis_key, CAPTCHA_TTL)
            return
        except Exception:
            pass

    # 内存兜底
    rec = _CAPTCHA_FAIL_STORE.get(key)
    if rec is None:
        _CAPTCHA_FAIL_STORE[key] = (1, time.time() + CAPTCHA_TTL)
    else:
        count, expire_at = rec
        _CAPTCHA_FAIL_STORE[key] = (count + 1, expire_at)


def _set_ip_cooldown(ip: str) -> None:
    """设置 IP 冷却期（60s）。"""
    expire_at = time.time() + CAPTCHA_FAIL_COOLDOWN
    _CAPTCHA_IP_COOLDOWN[ip] = expire_at

    r = _get_redis()
    if r is not None:
        try:
            r.setex(_redis_ip_cooldown_key(ip), CAPTCHA_FAIL_COOLDOWN, "1")
        except Exception:
            pass


def _is_ip_cooldown(ip: str) -> bool:
    """检查 IP 是否在冷却期。"""
    r = _get_redis()
    if r is not None:
        try:
            if r.exists(_redis_ip_cooldown_key(ip)):
                return True
        except Exception:
            pass

    # 内存兜底
    expire_at = _CAPTCHA_IP_COOLDOWN.get(ip)
    if expire_at is None:
        return False
    if time.time() > expire_at:
        _CAPTCHA_IP_COOLDOWN.pop(ip, None)
        return False
    return True


__all__ = [
    "generate_captcha",
    "verify_captcha",
    "CAPTCHA_CHARS",
    "CAPTCHA_LENGTH",
    "CAPTCHA_TTL",
]
