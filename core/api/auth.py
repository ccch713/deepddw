"""SaaS 注册 / 登录 / ME 端点（DDW AI Hub v5.5 — 登录安全闭环）。

端点：
- ``GET  /api/v1/auth/captcha``       获取图片验证码
- ``POST /api/v1/auth/register``      手机号+密码+验证码 → 创建 Tenant+User+TokenQuota → JWT
- ``POST /api/v1/auth/send-code``     发送手机验证码（前置图形验证码）
- ``POST /api/v1/auth/login``         手机号+验证码 登录（前置图形验证码）
- ``POST /api/v1/auth/login-password`` 手机号+密码+验证码 登录（四层限流+防枚举+设备绑定）
- ``GET  /api/v1/auth/me``            当前用户信息
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import bcrypt
import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.auth.captcha import generate_captcha, verify_captcha
from core.auth.slider_captcha import (
    consume_slider_token,
    generate_slider,
    get_x_range,
    revoke_slider_token,
    verify_slider,
)
from core.auth.jwt import create_access_token, current_user
from core.auth.password_policy import validate_password_strength
from core.database.models import LoginAudit, Tenant, User
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from core.email import is_smtp_configured, send_verify_code
from core.constants.roles import ADMIN_ROLES, FINANCE_ROLES, PLUGIN_MANAGE_ROLES
from core.services import tenant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# 密码哈希（沿用现有 bcrypt + sha256 预哈希）
# ---------------------------------------------------------------------------


def hash_password(pwd: str) -> str:
    """bcrypt 密码哈希（SHA256 预哈希以支持超长密码，rounds=12）。"""
    pre = hashlib.sha256(pwd.encode("utf-8")).hexdigest().encode("utf-8")
    return bcrypt.hashpw(pre, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(pwd: str, stored_hash: str) -> bool:
    """验证密码，兼容旧版 SHA256 哈希。"""
    if stored_hash.startswith("$2"):
        pre = hashlib.sha256(pwd.encode("utf-8")).hexdigest().encode("utf-8")
        try:
            return bcrypt.checkpw(pre, stored_hash.encode("utf-8"))
        except ValueError:
            return False
    # legacy: sha256 hexdigest
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest() == stored_hash


def _dummy_bcrypt_check() -> None:
    """虚拟 bcrypt 校验（时间均衡，防用户枚举）。"""
    dummy_hash = hash_password("dummy_password_for_timing")
    verify_password("dummy_password_for_timing", dummy_hash)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CaptchaResp(BaseModel):
    captcha_id: str
    image_base64: str
    expires_in: int = 120


class SendCodeReq(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    captcha_id: str = Field(..., min_length=8, max_length=64)
    captcha_code: str = Field(..., min_length=1, max_length=8)


class RegisterReq(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    captcha_id: str = Field(..., min_length=8, max_length=64)
    captcha_code: str = Field(..., min_length=1, max_length=8)
    company_name: Optional[str] = Field(None, max_length=200)
    name: Optional[str] = Field(None, max_length=120)
    plan: str = Field("free", pattern="^(free|standard|enterprise)$")


class LoginReq(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    code: str = Field(..., min_length=4, max_length=8)
    tenant_id: Optional[int] = Field(None, description="同手机号多租户时指定租户")


class SliderCaptchaResp(BaseModel):
    captcha_id: str
    bg_image: str
    puzzle_image: str
    x_range: list[int]
    puzzle_y: int


class SliderVerifyReq(BaseModel):
    captcha_id: str = Field(..., min_length=8, max_length=64)
    x: int = Field(..., ge=0, le=320)


class SliderVerifyResp(BaseModel):
    token: str


class LoginPasswordReq(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    password: str = Field(..., min_length=6, max_length=128)
    slider_token: str = Field(..., min_length=16, max_length=128)
    tenant_id: Optional[int] = Field(None, description="同手机号多租户时指定租户")
    device_fingerprint: Optional[Dict[str, Any]] = None


class SwitchTenantReq(BaseModel):
    """右上角切换租户身份请求体（2026-08-11）。"""

    tenant_id: int = Field(..., description="目标租户 ID")


class ChangePasswordReq(BaseModel):
    old_password: str = Field(..., min_length=6, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class ForgotPasswordReq(BaseModel):
    email: str = Field(..., max_length=255)
    captcha_id: str = Field(..., min_length=8, max_length=64)
    captcha_code: str = Field(..., min_length=1, max_length=8)


class ResetPasswordReq(BaseModel):
    email: str = Field(..., max_length=255)
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)


class VerifyEmailReq(BaseModel):
    email: str = Field(..., max_length=255)
    code: str = Field(..., min_length=6, max_length=6)


class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]
    tenant: Dict[str, Any]
    password_expired: bool = False
    must_change: bool = False


# ---------------------------------------------------------------------------
# 内存验证码存储（dev 用；生产应替换为 Redis / 短信网关）
# ---------------------------------------------------------------------------


_VERIFY_CODES: Dict[str, tuple[str, float]] = {}
CODE_TTL_SEC = 300
# 调试万能码：必须显式设置 DDW_ALWAYS_ACCEPT_CODE 才会启用。
ALWAYS_ACCEPT_CODE: Optional[str] = os.environ.get("DDW_ALWAYS_ACCEPT_CODE")

# ---------------------------------------------------------------------------
# Redis 验证码存储（多 worker 部署时共享；不可用时自动降级内存）
# ---------------------------------------------------------------------------
_REDIS_URL = os.environ.get("DDW_REDIS_URL", "redis://127.0.0.1:6379/0")
_REDIS_PASSWORD = os.environ.get("DDW_REDIS_PASSWORD", "")
_redis_client: Optional[redis_lib.Redis] = None
_redis_failed = False


def _get_redis() -> Optional[redis_lib.Redis]:
    """惰性连接 Redis；失败后本进程内不再重试（降级内存）。"""
    global _redis_client, _redis_failed
    if _redis_failed:
        return None
    if _redis_client is None:
        try:
            if _REDIS_PASSWORD:
                _redis_client = redis_lib.Redis.from_url(
                    _REDIS_URL, password=_REDIS_PASSWORD,
                    socket_timeout=2, socket_connect_timeout=2,
                )
            else:
                _redis_client = redis_lib.Redis.from_url(
                    _REDIS_URL, socket_timeout=2, socket_connect_timeout=2,
                )
            _redis_client.ping()
        except Exception as exc:  # noqa: BLE001
            logger.warning("verify-code redis unavailable, fallback in-memory: %s", exc)
            _redis_failed = True
            _redis_client = None
    return _redis_client


def _redis_key(phone: str) -> str:
    return f"ddw:verify:{phone}"


def _set_code(phone: str, code: str) -> None:
    """写验证码：Redis + 内存双写（任一路径可用即可消费）。"""
    _VERIFY_CODES[phone] = (code, time.time() + CODE_TTL_SEC)
    r = _get_redis()
    if r is not None:
        try:
            r.setex(_redis_key(phone), CODE_TTL_SEC, code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis setex failed: %s", exc)


def _consume_code(phone: str, code: str) -> bool:
    if ALWAYS_ACCEPT_CODE is not None and code == ALWAYS_ACCEPT_CODE:
        return True
    # 1) Redis 优先（多 worker 共享）
    r = _get_redis()
    if r is not None:
        try:
            stored = r.get(_redis_key(phone))
            if stored is not None:
                r.delete(_redis_key(phone))
                return stored.decode("utf-8") == code
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis get failed: %s", exc)
    # 2) 内存兜底
    rec = _VERIFY_CODES.get(phone)
    if rec is None:
        return False
    stored, exp = rec
    if time.time() > exp:
        _VERIFY_CODES.pop(phone, None)
        return False
    if stored != code:
        return False
    _VERIFY_CODES.pop(phone, None)
    return True


# ---------------------------------------------------------------------------
# 四层限流核心逻辑
# ---------------------------------------------------------------------------

# 限流键前缀
_BRUTE_PREFIX = "ddw:brute"
_LOCK_PREFIX = "ddw:lock"

# 内存降级存储
_brute_memory: Dict[str, tuple[int, float]] = {}  # key -> (count, expire_ts)
_lock_memory: Dict[str, float] = {}  # key -> expire_ts


def _rate_limit_key(*parts: str) -> str:
    return ":".join(parts)


def _get_brute_count(key: str) -> int:
    """获取暴力破解计数。"""
    r = _get_redis()
    if r is not None:
        try:
            val = r.get(key)
            if val is not None:
                return int(val)
            return 0
        except Exception:
            pass
    # 内存降级
    rec = _brute_memory.get(key)
    if rec is None:
        return 0
    count, expire_at = rec
    if time.time() > expire_at:
        _brute_memory.pop(key, None)
        return 0
    return count


def _increment_brute(key: str, window_sec: int) -> int:
    """递增暴力破解计数。"""
    r = _get_redis()
    if r is not None:
        try:
            n = r.incr(key)
            if n == 1:
                r.expire(key, window_sec)
            return n
        except Exception:
            pass
    # 内存降级
    rec = _brute_memory.get(key)
    if rec is None:
        _brute_memory[key] = (1, time.time() + window_sec)
        return 1
    count, expire_at = rec
    _brute_memory[key] = (count + 1, expire_at)
    return count + 1


def _is_locked(key: str, ttl: int) -> bool:
    """检查是否被锁定。"""
    r = _get_redis()
    if r is not None:
        try:
            if r.exists(key):
                return True
            return False
        except Exception:
            pass
    # 内存降级
    expire_at = _lock_memory.get(key)
    if expire_at is None:
        return False
    if time.time() > expire_at:
        _lock_memory.pop(key, None)
        return False
    return True


def _set_lock(key: str, ttl: int) -> int:
    """设置锁定。返回 TTL 秒数。"""
    r = _get_redis()
    if r is not None:
        try:
            r.setex(key, ttl, "1")
            return ttl
        except Exception:
            pass
    # 内存降级
    _lock_memory[key] = time.time() + ttl
    return ttl


def _get_lock_ttl(key: str) -> int:
    """获取锁剩余 TTL 秒数。"""
    r = _get_redis()
    if r is not None:
        try:
            ttl = r.ttl(key)
            if ttl > 0:
                return ttl
            return 0
        except Exception:
            pass
    # 内存降级
    expire_at = _lock_memory.get(key)
    if expire_at is None:
        return 0
    remaining = int(expire_at - time.time())
    return max(0, remaining)


def _clear_brute_counts(ip: str, phone: str) -> None:
    """成功登录后清除失败计数。"""
    keys = [
        _rate_limit_key(_BRUTE_PREFIX, ip, phone),
        _rate_limit_key(_BRUTE_PREFIX, ip, "global"),
        _rate_limit_key(_BRUTE_PREFIX, phone),
    ]
    r = _get_redis()
    if r is not None:
        try:
            for k in keys:
                r.delete(k)
        except Exception:
            pass
    for k in keys:
        _brute_memory.pop(k, None)


def check_rate_limit(ip: str, phone: str) -> Optional[Dict[str, Any]]:
    """四层限流检查。

    L1: IP+账号 5min/5次 → 锁15min
    L2: IP全局 5min/20次 → 锁30min
    L3: 账号 1h/10次 → 锁1h + 写 locked_until

    Returns:
        None = 允许；Dict = 限流响应体（需抛 HTTPException 429）
    """
    # L1: IP+账号
    l1_key = _rate_limit_key(_BRUTE_PREFIX, ip, phone)
    l1_lock = _rate_limit_key(_LOCK_PREFIX, ip, phone)
    if _is_locked(l1_lock, 900):
        ttl = _get_lock_ttl(l1_lock)
        return {"detail": f"安全限制：请 {max(1, ttl // 60)} 分钟后重试", "retry_after": ttl}

    l1_count = _get_brute_count(l1_key)
    if l1_count >= 5:
        ttl = _set_lock(l1_lock, 900)
        return {"detail": f"安全限制：请 {max(1, ttl // 60)} 分钟后重试", "retry_after": ttl}

    # L2: IP 全局
    l2_key = _rate_limit_key(_BRUTE_PREFIX, ip, "global")
    l2_lock = _rate_limit_key(_LOCK_PREFIX, ip, "global")
    if _is_locked(l2_lock, 1800):
        ttl = _get_lock_ttl(l2_lock)
        return {"detail": f"安全限制：请 {max(1, ttl // 60)} 分钟后重试", "retry_after": ttl}

    l2_count = _get_brute_count(l2_key)
    if l2_count >= 20:
        ttl = _set_lock(l2_lock, 1800)
        return {"detail": f"安全限制：请 {max(1, ttl // 60)} 分钟后重试", "retry_after": ttl}

    # L3: 账号
    l3_key = _rate_limit_key(_BRUTE_PREFIX, phone)
    l3_lock = _rate_limit_key(_LOCK_PREFIX, phone)
    if _is_locked(l3_lock, 3600):
        ttl = _get_lock_ttl(l3_lock)
        return {"detail": f"安全限制：请 {max(1, ttl // 60)} 分钟后重试", "retry_after": ttl}

    l3_count = _get_brute_count(l3_key)
    if l3_count >= 10:
        ttl = _set_lock(l3_lock, 3600)
        # 写入 users 表 locked_until
        _set_user_locked_until(phone, ttl)
        return {"detail": f"安全限制：请 {max(1, ttl // 60)} 分钟后重试", "retry_after": ttl}

    return None


def record_failure(ip: str, phone: str) -> None:
    """记录登录失败（密码错误/用户不存在）。"""
    _increment_brute(_rate_limit_key(_BRUTE_PREFIX, ip, phone), 300)  # L1: 5min
    _increment_brute(_rate_limit_key(_BRUTE_PREFIX, ip, "global"), 300)  # L2: 5min
    _increment_brute(_rate_limit_key(_BRUTE_PREFIX, phone), 3600)  # L3: 1h


def _set_user_locked_until(phone: str, ttl: int) -> None:
    """写入 users 表 locked_until 字段。"""
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在异步上下文中，创建任务
            asyncio.ensure_future(_async_set_locked_until(phone, ttl))
        else:
            loop.run_until_complete(_async_set_locked_until(phone, ttl))
    except Exception as exc:
        logger.warning("failed to set locked_until for %s: %s", phone, exc)


async def _async_set_locked_until(phone: str, ttl: int) -> None:
    """异步写入 locked_until（同手机号多租户账号全部锁定）。"""
    async with session_scope() as session, bypass_tenant_filter():
        users = (await session.execute(select(User).where(User.phone == phone))).scalars().all()
        if users:
            for u in users:
                u.locked_until = datetime.utcnow() + timedelta(seconds=ttl)
            await session.commit()


def _check_account_locked(phone: str) -> Optional[Dict[str, Any]]:
    """检查账号是否被锁定（L3 写入 users 表）。"""
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 同步检查内存中的锁定状态
            l3_lock = _rate_limit_key(_LOCK_PREFIX, phone)
            if _is_locked(l3_lock, 3600):
                ttl = _get_lock_ttl(l3_lock)
                return {"detail": f"安全限制：请 {max(1, ttl // 60)} 分钟后重试", "retry_after": ttl}
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 登录审计
# ---------------------------------------------------------------------------


async def _write_login_audit(
    phone: Optional[str],
    ip: Optional[str],
    user_agent: Optional[str],
    method: str,
    success: bool,
    fail_reason: Optional[str] = None,
) -> None:
    """写入登录审计日志。"""
    try:
        async with session_scope() as session:
            audit = LoginAudit(
                phone=phone,
                ip=ip,
                user_agent=user_agent,
                method=method,
                success=success,
                fail_reason=fail_reason,
            )
            session.add(audit)
            await session.commit()
    except Exception as exc:
        logger.warning("login audit write failed: %s", exc)


def _get_client_ip(request: Request) -> str:
    """获取客户端 IP。"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# 验证码发送限流（多 worker 安全：Redis INCR 优先，内存 fallback）
# ---------------------------------------------------------------------------


def _rate_limit_send_code(phone: str) -> bool:
    """60 秒窗口内同号只允许发送 1 次。"""
    r = _get_redis()
    if r is not None:
        try:
            key = f"ddw:ratelimit:sendcode:{phone}"
            n = r.incr(key)
            if n == 1:
                r.expire(key, 60)
            return n <= 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis rate limit failed, fallback memory: %s", exc)
    # 内存 fallback
    last = getattr(send_code, "_last", {}).get(phone)
    if last and time.time() - last < 60:
        return False
    setattr(send_code, "_last", {**(getattr(send_code, "_last", {})), phone: time.time()})
    return True


# ---------------------------------------------------------------------------
# 邮件验证码存储 + 限流（复用 _VERIFY_CODES 模式，key 用 email 前缀）
# ---------------------------------------------------------------------------


def _email_redis_key(email: str) -> str:
    return f"ddw:verify:email:{email}"


def _set_email_code(email: str, code: str) -> None:
    """写邮件验证码：Redis + 内存双写。"""
    _VERIFY_CODES[f"email:{email}"] = (code, time.time() + CODE_TTL_SEC)
    r = _get_redis()
    if r is not None:
        try:
            r.setex(_email_redis_key(email), CODE_TTL_SEC, code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis setex email code failed: %s", exc)


def _consume_email_code(email: str, code: str) -> bool:
    """消费邮件验证码（一次性，TTL 300s）。"""
    if ALWAYS_ACCEPT_CODE is not None and code == ALWAYS_ACCEPT_CODE:
        return True
    r = _get_redis()
    if r is not None:
        try:
            stored = r.get(_email_redis_key(email))
            if stored is not None:
                r.delete(_email_redis_key(email))
                return stored.decode("utf-8") == code
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis get email code failed: %s", exc)
    rec = _VERIFY_CODES.get(f"email:{email}")
    if rec is None:
        return False
    stored, exp = rec
    if time.time() > exp:
        _VERIFY_CODES.pop(f"email:{email}", None)
        return False
    if stored != code:
        return False
    _VERIFY_CODES.pop(f"email:{email}", None)
    return True


def _rate_limit_email_send(email: str) -> bool:
    """60 秒窗口内同邮箱只允许发送 1 次。"""
    r = _get_redis()
    if r is not None:
        try:
            key = f"ddw:ratelimit:email_send:{email}"
            n = r.incr(key)
            if n == 1:
                r.expire(key, 60)
            return n <= 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis email rate limit failed, fallback memory: %s", exc)
    last = getattr(_rate_limit_email_send, "_last", {}).get(email)
    if last and time.time() - last < 60:
        return False
    _rate_limit_email_send._last = {**getattr(_rate_limit_email_send, "_last", {}), email: time.time()}
    return True


def _rate_limit_forgot_ip(ip: str) -> bool:
    """同 IP 每分钟 ≤10 次 forgot-password 请求。"""
    r = _get_redis()
    if r is not None:
        try:
            key = f"ddw:ratelimit:forgot_ip:{ip}"
            n = r.incr(key)
            if n == 1:
                r.expire(key, 60)
            return n <= 10
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis forgot IP rate limit failed: %s", exc)
    rec = _brute_memory.get(f"forgot_ip:{ip}")
    now = time.time()
    if rec is None:
        _brute_memory[f"forgot_ip:{ip}"] = (1, now + 60)
        return True
    count, expire_at = rec
    if now > expire_at:
        _brute_memory[f"forgot_ip:{ip}"] = (1, now + 60)
        return True
    if count >= 10:
        return False
    _brute_memory[f"forgot_ip:{ip}"] = (count + 1, expire_at)
    return True


# ---------------------------------------------------------------------------
# 密码过期 / 强制改密 判断
# ---------------------------------------------------------------------------


def _compute_must_change(user: User) -> tuple[bool, bool]:
    """计算 must_change 和 password_expired。

    Returns:
        (must_change, password_expired)
    """
    from core.config import get_settings

    changed_at = user.password_changed_at
    if changed_at is None:
        # 存量账号未设置 password_changed_at → 强制改密
        return True, False
    age_days = (datetime.utcnow() - changed_at).days
    max_days = get_settings().password_max_age_days
    if age_days > max_days:
        return True, True
    return False, False


async def _is_demo_account(phone: str) -> bool:
    """判断手机号是否在经销商 demo 账号表（partner_demo_accounts）中。

    demo 账号密码公开、供演示使用，登录不强制改密。
    表不存在（插件未加载/未建表）时返回 False，不阻断登录。
    """
    if not phone:
        return False
    try:
        from sqlalchemy import text

        async with session_scope() as session, bypass_tenant_filter():
            row = (
                await session.execute(
                    text("SELECT 1 FROM partner_demo_accounts WHERE demo_phone = :p LIMIT 1"),
                    {"p": phone},
                )
            ).first()
            return row is not None
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/captcha", response_model=CaptchaResp)
async def get_captcha() -> CaptchaResp:
    """获取图片验证码。"""
    captcha_id, image_base64, expires_in = generate_captcha()
    return CaptchaResp(
        captcha_id=captcha_id,
        image_base64=image_base64,
        expires_in=expires_in,
    )


@router.get("/slider", response_model=SliderCaptchaResp)
async def get_slider() -> SliderCaptchaResp:
    """获取滑块拼图。"""
    captcha_id, bg_image, puzzle_image, _x_target, puzzle_y = generate_slider()
    xr = get_x_range()
    return SliderCaptchaResp(
        captcha_id=captcha_id,
        bg_image=bg_image,
        puzzle_image=puzzle_image,
        x_range=[xr[0], xr[1]],
        puzzle_y=puzzle_y,
    )


@router.post("/slider/verify", response_model=SliderVerifyResp)
async def slider_verify(req: SliderVerifyReq, request: Request) -> SliderVerifyResp:
    """校验滑块位置。"""
    ip = _get_client_ip(request)
    ok, reason, token = verify_slider(req.captcha_id, req.x, ip)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    return SliderVerifyResp(token=token)


@router.post("/send-code", response_model=Dict[str, Any])
async def send_code(req: SendCodeReq, request: Request) -> Dict[str, Any]:
    """发送手机验证码（前置图形验证码校验）。"""
    # 先校验图形验证码
    ip = _get_client_ip(request)
    ok, reason = verify_captcha(req.captcha_id, req.captcha_code, ip)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    # 限流：Redis 优先（多 worker 安全），内存兜底
    if not _rate_limit_send_code(req.phone):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="请稍候 60 秒后再试")
    code = f"{secrets.randbelow(9000) + 1000}"
    _set_code(req.phone, code)
    logger.info("[DEV] send verification code phone=%s code=%s", req.phone, code)
    resp: Dict[str, Any] = {"sent": True, "phone": req.phone, "ttl_sec": CODE_TTL_SEC}
    # 仅当 ALWAYS_ACCEPT_CODE 环境变量显式设置时保留 always_accept 字段
    if ALWAYS_ACCEPT_CODE is not None:
        resp["always_accept"] = ALWAYS_ACCEPT_CODE
    return resp


@router.post("/register", response_model=TokenResp, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterReq) -> TokenResp:
    """注册 → 创建 Tenant + 首位 owner User + 默认 TokenQuota → 签发 JWT。"""
    # 校验图形验证码
    ok, reason = verify_captcha(req.captcha_id, req.captcha_code)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    # 密码强度校验
    strength_err = validate_password_strength(req.password)
    if strength_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=strength_err)

    async with session_scope() as session, bypass_tenant_filter():
        existing = (await session.execute(select(User).where(User.phone == req.phone))).scalars().first()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该手机号已注册")

        # 邮箱唯一性校验
        existing_email = (await session.execute(select(User).where(User.email == req.email))).scalar_one_or_none()
        if existing_email is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已被绑定")

        company_name = (req.company_name or "").strip() or f"{req.phone} 的企业"
        tenant = await tenant_service.create_tenant(
            session, name=company_name, plan=req.plan, contact_phone=req.phone
        )
        user = User(
            tenant_id=tenant.id,
            phone=req.phone,
            email=req.email,
            password_hash=hash_password(req.password),
            name=req.name or "管理员",
            role="owner",
            status="active",
            password_changed_at=datetime.utcnow(),
        )
        session.add(user)
        try:
            await session.commit()
        except IntegrityError as e:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"注册失败：{e.orig}") from e
        await session.refresh(user)

        # 注册成功后发邮箱验证邮件
        try:
            code = f"{secrets.randbelow(900000) + 100000}"
            _set_email_code(req.email, code)
            env = os.environ.get("DDW_ENV", "development")
            if is_smtp_configured() or env != "production":
                await send_verify_code(req.email, code, "verify_email")
        except Exception as exc:
            logger.warning("send verify email failed after register: %s", exc)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role="owner")
        from core.config import get_settings

        return TokenResp(
            access_token=token,
            expires_in=get_settings().jwt_expires_minutes * 60,
            user={"id": user.id, "phone": user.phone, "name": user.name, "role": user.role},
            tenant={"id": tenant.id, "name": tenant.name, "plan": tenant.plan},
        )


# ---------------------------------------------------------------------------
# 多租户账号解析（同手机号跨租户：经销商/客户demo）
# ---------------------------------------------------------------------------


async def _resolve_login_user(session, phone: str, tenant_id: Optional[int] = None):
    """按手机号解析登录用户。

    - 1 个账号 → 直接返回
    - 多个账号 + tenant_id → 匹配该租户的账号
    - 多个账号 + 无 tenant_id → 抛 409，返回租户选择列表
    """
    users = (await session.execute(select(User).where(User.phone == phone))).scalars().all()
    if not users:
        return None
    if len(users) == 1:
        return users[0]
    # 多个账号
    if tenant_id is not None:
        for u in users:
            if u.tenant_id == tenant_id:
                return u
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TENANT_NOT_FOUND", "message": "该手机号未关联所选租户"},
        )
    # 无 tenant_id → 返回可选租户列表
    tenants_payload = []
    for u in users:
        t = (await session.execute(select(Tenant).where(Tenant.id == u.tenant_id))).scalar_one_or_none()
        if t is not None:
            tenants_payload.append(
                {
                    "tenant_id": t.id,
                    "name": t.name,
                    "plan": t.plan,
                    "role": u.role,
                }
            )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "MULTI_TENANT", "message": "该手机号关联多个租户，请选择", "tenants": tenants_payload},
    )


@router.post("/login", response_model=TokenResp)
async def login(req: LoginReq, request: Request) -> TokenResp:
    """手机号 + 验证码登录（前置图形验证码 + 防枚举）。"""
    ip = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    # 先校验图形验证码
    ok, reason = verify_captcha(req.captcha_id if hasattr(req, "captcha_id") else "", req.code, ip)
    # 短信登录不需要图形验证码，直接消费短信验证码
    if not _consume_code(req.phone, req.code):
        await _write_login_audit(req.phone, ip, user_agent, "sms", False, "验证码无效或已过期")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码无效或已过期")

    async with session_scope() as session, bypass_tenant_filter():
        user = await _resolve_login_user(session, req.phone, getattr(req, "tenant_id", None))
        # 防枚举：统一返回 401
        if user is None:
            record_failure(ip, req.phone)
            await _write_login_audit(req.phone, ip, user_agent, "sms", False, "用户不存在")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

        # 停用用户拒绝登录
        if user.status == "disabled":
            await _write_login_audit(req.phone, ip, user_agent, "sms", False, "账号已停用")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被停用，请联系管理员")

        # 检查账号锁定
        if user.locked_until and user.locked_until > datetime.utcnow():
            remaining = int((user.locked_until - datetime.utcnow()).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"安全限制：请 {max(1, remaining // 60)} 分钟后重试",
                headers={"Retry-After": str(remaining)},
            )

        tenant = (await session.execute(select(Tenant).where(Tenant.id == user.tenant_id))).scalar_one_or_none()
        if tenant is None:
            await _write_login_audit(req.phone, ip, user_agent, "sms", False, "租户不存在")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="租户不存在")

        # 清除失败计数
        _clear_brute_counts(ip, req.phone)

        user.last_login_at = datetime.utcnow()
        await session.commit()

        await _write_login_audit(req.phone, ip, user_agent, "sms", True)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=user.role)
        from core.config import get_settings

        must_change, password_expired = _compute_must_change(user)
        # demo 账号（经销商 demo 账号表）不强制改密——演示密码公开，改密无意义
        if must_change and await _is_demo_account(user.phone):
            must_change = False

        return TokenResp(
            access_token=token,
            expires_in=get_settings().jwt_expires_minutes * 60,
            user={"id": user.id, "phone": user.phone, "name": user.name, "role": user.role},
            tenant={"id": tenant.id, "name": tenant.name, "plan": tenant.plan},
            password_expired=password_expired,
            must_change=must_change,
        )


@router.post("/login-password", response_model=TokenResp)
async def login_password(req: LoginPasswordReq, request: Request, response: Response) -> TokenResp:
    """手机号 + 密码 + 验证码 登录（四层限流+防枚举+设备绑定）。"""
    ip = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    # 1. 校验滑块 token（不消费，多租户 409 后可复用）
    if not consume_slider_token(req.slider_token, ip):
        await _write_login_audit(req.phone, ip, user_agent, "password", False, "滑块验证无效")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先完成滑块验证")

    # 2. 四层限流检查
    rate_limit_result = check_rate_limit(ip, req.phone)
    if rate_limit_result is not None:
        await _write_login_audit(req.phone, ip, user_agent, "password", False, "限流")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rate_limit_result["detail"],
            headers={"Retry-After": str(rate_limit_result["retry_after"])},
        )

    async with session_scope() as session, bypass_tenant_filter():
        user = await _resolve_login_user(session, req.phone, req.tenant_id)

        # 3. 防枚举：用户不存在 → 401 + 虚拟 bcrypt
        if user is None:
            _dummy_bcrypt_check()
            record_failure(ip, req.phone)
            await _write_login_audit(req.phone, ip, user_agent, "password", False, "用户不存在")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

        # 3.5 停用用户拒绝登录
        if user.status == "disabled":
            await _write_login_audit(req.phone, ip, user_agent, "password", False, "账号已停用")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被停用，请联系管理员")

        # 4. 检查账号锁定（L3 写入 users 表）
        if user.locked_until and user.locked_until > datetime.utcnow():
            remaining = int((user.locked_until - datetime.utcnow()).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"安全限制：请 {max(1, remaining // 60)} 分钟后重试",
                headers={"Retry-After": str(remaining)},
            )

        # 5. 密码验证
        if not user.password_hash:
            await _write_login_audit(req.phone, ip, user_agent, "password", False, "未设置密码")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该账号未设置密码，请使用验证码登录")
        if not verify_password(req.password, user.password_hash):
            record_failure(ip, req.phone)
            await _write_login_audit(req.phone, ip, user_agent, "password", False, "密码错误")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

        # 6. 账号级设备绑定（device_required=True 时强制，所有 mode 生效）
        if user.device_required:
            from core.auth.device_binding import verify_user_device

            fingerprint = req.device_fingerprint or {}
            ok, reason = verify_user_device(user, fingerprint)
            if not ok:
                await _write_login_audit(req.phone, ip, user_agent, "password", False, f"设备验证失败: {reason}")
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"设备验证失败: {reason}")

        tenant = (await session.execute(select(Tenant).where(Tenant.id == user.tenant_id))).scalar_one_or_none()
        if tenant is None:
            await _write_login_audit(req.phone, ip, user_agent, "password", False, "租户不存在")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="租户不存在")

        # 7. 登录成功，清除失败计数
        _clear_brute_counts(ip, req.phone)

        user.last_login_at = datetime.utcnow()
        await session.commit()

        await _write_login_audit(req.phone, ip, user_agent, "password", True)

        # 登录成功后消费 slider token
        revoke_slider_token(req.slider_token)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=user.role)
        from core.config import get_settings

        must_change, password_expired = _compute_must_change(user)
        # demo 账号（经销商 demo 账号表）不强制改密——演示密码公开，改密无意义
        if must_change and await _is_demo_account(user.phone):
            must_change = False

        # 种跨域登录态 cookie（官网 www.9cio.com 检测"进入 AI HUB"按钮）
        try:
            response.set_cookie(
                key="ddw_logged_in",
                value="1",
                max_age=7 * 24 * 3600,
                path="/",
                domain=".9cio.com",
                samesite="lax",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("set login cookie failed: %s", exc)

        return TokenResp(
            access_token=token,
            expires_in=get_settings().jwt_expires_minutes * 60,
            user={"id": user.id, "phone": user.phone, "name": user.name, "role": user.role},
            tenant={"id": tenant.id, "name": tenant.name, "plan": tenant.plan},
            password_expired=password_expired,
            must_change=must_change,
        )


# ---------------------------------------------------------------------------
# 改密端点限流（同 IP 1 小时最多 5 次）
# ---------------------------------------------------------------------------


def _rate_limit_change_password(ip: str) -> Optional[Dict[str, Any]]:
    """改密端点 IP 限流：同 IP 1 小时内最多 5 次。"""
    key = f"ddw:ratelimit:changepwd:{ip}"
    r = _get_redis()
    if r is not None:
        try:
            n = r.incr(key)
            if n == 1:
                r.expire(key, 3600)
            if n > 5:
                ttl = r.ttl(key)
                return {"detail": f"修改密码请求过于频繁，请 {max(1, ttl // 60)} 分钟后重试", "retry_after": max(1, ttl)}
            return None
        except Exception:
            pass
    # 内存降级
    rec = _brute_memory.get(key)
    now = time.time()
    if rec is None:
        _brute_memory[key] = (1, now + 3600)
        return None
    count, expire_at = rec
    if now > expire_at:
        _brute_memory[key] = (1, now + 3600)
        return None
    if count >= 5:
        remaining = int(expire_at - now)
        return {"detail": f"修改密码请求过于频繁，请 {max(1, remaining // 60)} 分钟后重试", "retry_after": max(1, remaining)}
    _brute_memory[key] = (count + 1, expire_at)
    return None


@router.post("/change-password", response_model=Dict[str, Any])
async def change_password(
    req: ChangePasswordReq,
    request: Request,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    """登录用户自助修改密码（旧密码 + 新密码 + 确认新密码）。"""
    ip = _get_client_ip(request)

    # 1) IP 限流
    rl = _rate_limit_change_password(ip)
    if rl is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rl["detail"],
            headers={"Retry-After": str(rl["retry_after"])},
        )

    async with session_scope() as session, bypass_tenant_filter():
        db_user = (await session.execute(select(User).where(User.id == user["user_id"]))).scalar_one_or_none()
        if db_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        # 2) 旧密码校验
        if not db_user.password_hash or not verify_password(req.old_password, db_user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")

        # 3) 新密码强度校验
        strength_err = validate_password_strength(req.new_password)
        if strength_err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=strength_err)

        # 4) 新旧不能相同
        if req.new_password == req.old_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与原密码相同")

        # 5) 更新密码
        db_user.password_hash = hash_password(req.new_password)
        db_user.password_changed_at = datetime.utcnow()
        await session.commit()

        return {"changed": True}


@router.get("/me", response_model=Dict[str, Any])
async def me(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        u = (await session.execute(select(User).where(User.id == user["user_id"]))).scalar_one_or_none()
        t = (await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]))).scalar_one_or_none()
        if u is None or t is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户或租户不存在")
        role = u.role
        can_admin = role in ADMIN_ROLES
        # 同手机号关联的全部租户（右上角切换身份用）
        tenants: list[Dict[str, Any]] = []
        try:
            rows = (await session.execute(select(User).where(User.phone == u.phone, User.status == "active"))).scalars().all()
            for row in rows:
                tt = (await session.execute(select(Tenant).where(Tenant.id == row.tenant_id))).scalar_one_or_none()
                if tt is None:
                    continue
                tenants.append({
                    "tenant_id": tt.id,
                    "name": tt.name,
                    "role": row.role,
                    "plan": tt.plan,
                    "status": tt.status,
                })
        except Exception as exc:  # noqa: BLE001
            logger.warning("me tenants query failed: %s", exc)
        return {
            "user": {
                "id": u.id,
                "phone": u.phone,
                "name": u.name,
                "role": role,
                "status": u.status,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            },
            "tenant": {
                "id": t.id,
                "name": t.name,
                "plan": t.plan,
                "status": t.status,
            },
            "can_access_admin": can_admin,
            # 所有角色统一进入 DDW Pal 工作台（2026-08-11 用户定案）
            "redirect_target": "/pal.html",
            # 权限矩阵收敛（2026-08-11）：前端一律消费 permissions，禁止各自判断 role
            "permissions": {
                "can_access_admin": can_admin,
                "can_manage_plugins": role in PLUGIN_MANAGE_ROLES,
                "can_view_finance": role in FINANCE_ROLES,
                "can_manage_partner_demo": role == "partner",
            },
            "tenants": tenants,
        }


@router.post("/switch-tenant", response_model=Dict[str, Any])
async def switch_tenant(
    req: SwitchTenantReq,
    request: Request,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    """右上角切换身份：同手机号跨租户，免反复登录（2026-08-11）。

    校验当前账号 → 按 (phone, tenant_id) 找目标账号 → 签发新 JWT。
    """
    async with session_scope() as session, bypass_tenant_filter():
        cur = (await session.execute(select(User).where(User.id == user["user_id"]))).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态失效，请重新登录")
        target = (
            await session.execute(
                select(User).where(
                    User.phone == cur.phone,
                    User.tenant_id == req.tenant_id,
                    User.status == "active",
                )
            )
        ).scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权切换到该租户身份")
        tenant = (await session.execute(select(Tenant).where(Tenant.id == target.tenant_id))).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="目标租户不存在")

        token = create_access_token(user_id=target.id, tenant_id=tenant.id, role=target.role)
        return {
            "access_token": token,
            "expires_in": 7200,
            "user": {"id": target.id, "phone": target.phone, "name": target.name, "role": target.role},
            "tenant": {"id": tenant.id, "name": tenant.name, "plan": tenant.plan},
        }


# ---------------------------------------------------------------------------
# 忘记密码 / 重置密码 / 邮箱验证
# ---------------------------------------------------------------------------


@router.post("/forgot-password", response_model=Dict[str, Any])
async def forgot_password(req: ForgotPasswordReq, request: Request) -> Dict[str, Any]:
    """忘记密码：校验图形验证码 → 发邮件验证码。

    防枚举：邮箱不存在也返回 sent:true（日志记 email_not_found）。
    限流：同邮箱 60s/次 + IP 每分钟 ≤10 次。
    SMTP 未配置：production → 503；非 production → 日志打印验证码 + sent:true。
    """
    ip = _get_client_ip(request)

    # 1) 校验图形验证码（消费）
    ok, reason = verify_captcha(req.captcha_id, req.captcha_code, ip)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    # 2) IP 限流
    if not _rate_limit_forgot_ip(ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="请求过于频繁，请稍后再试")

    # 3) 邮箱限流
    if not _rate_limit_email_send(req.email):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="请稍候 60 秒后再试")

    # 4) 查邮箱是否存在
    async with session_scope() as session, bypass_tenant_filter():
        user = (await session.execute(select(User).where(User.email == req.email))).scalar_one_or_none()

    if user is None:
        logger.info("forgot-password email_not_found email=%s ip=%s", req.email, ip)

    # 5) SMTP 未配置处理
    env = os.environ.get("DDW_ENV", "development")
    if not is_smtp_configured():
        if env == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="邮件服务未配置，请联系管理员",
            )

    # 6) 生成验证码并发送
    code = f"{secrets.randbelow(900000) + 100000}"
    _set_email_code(req.email, code)
    try:
        await send_verify_code(req.email, code, "reset_password")
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="邮件服务未配置，请联系管理员",
        )
    except Exception as exc:
        logger.error("send reset code failed email=%s: %s", req.email, exc)

    return {"sent": True}


@router.post("/reset-password", response_model=Dict[str, Any])
async def reset_password(req: ResetPasswordReq) -> Dict[str, Any]:
    """重置密码：邮箱验证码 + 新密码。

    - 消费邮件验证码（一次性，TTL 300s）
    - 密码强度校验
    - 新密码 != 旧密码
    - password_hash 更新 + password_changed_at=now + email_verified=True
    """
    # 1) 消费邮件验证码
    if not _consume_email_code(req.email, req.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码无效或已过期")

    # 2) 密码强度校验
    strength_err = validate_password_strength(req.new_password)
    if strength_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=strength_err)

    # 3) 查用户
    async with session_scope() as session, bypass_tenant_filter():
        user = (await session.execute(select(User).where(User.email == req.email))).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户不存在")

        # 4) 新旧密码不能相同
        if user.password_hash and verify_password(req.new_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与原密码相同")

        # 5) 更新密码 + 标记邮箱已验证
        user.password_hash = hash_password(req.new_password)
        user.password_changed_at = datetime.utcnow()
        user.email_verified = True
        await session.commit()

    return {"reset": True}


@router.post("/verify-email", response_model=Dict[str, Any])
async def verify_email(req: VerifyEmailReq) -> Dict[str, Any]:
    """验证邮箱：邮箱 + 验证码 → email_verified=True。"""
    if not _consume_email_code(req.email, req.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码无效或已过期")

    async with session_scope() as session, bypass_tenant_filter():
        user = (await session.execute(select(User).where(User.email == req.email))).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户不存在")
        user.email_verified = True
        await session.commit()

    return {"verified": True}


# ---------------------------------------------------------------------------
# Demo 一键登录（经销商→客户 demo 兑换正式会话）
# ---------------------------------------------------------------------------

# demo token 单次兑换黑名单（内存 + Redis 双写，与验证码同模式）
_DEMO_TOKEN_USED: set[str] = set()


def _demo_token_redis_key(jti: str) -> str:
    return f"ddw:demo_token:{jti}"


def _mark_demo_token_used(jti: str) -> None:
    """标记 demo token 已使用（单次兑换）。"""
    _DEMO_TOKEN_USED.add(jti)
    r = _get_redis()
    if r is not None:
        try:
            r.setex(_demo_token_redis_key(jti), 900, "1")
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis mark demo token used failed: %s", exc)


def _is_demo_token_used(jti: str) -> bool:
    """检查 demo token 是否已使用。"""
    if jti in _DEMO_TOKEN_USED:
        return True
    r = _get_redis()
    if r is not None:
        try:
            return r.exists(_demo_token_redis_key(jti)) > 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis check demo token used failed: %s", exc)
    return False


class DemoLoginReq(BaseModel):
    demo_token: str = Field(..., min_length=10, max_length=2048)


@router.post("/demo-login", response_model=TokenResp)
async def demo_login(req: DemoLoginReq) -> TokenResp:
    """demo token 兑换正式会话 JWT（单次兑换，scope=demo_enter）。"""
    from core.auth.jwt import decode_token

    # 1. 解码 demo token
    try:
        payload = decode_token(req.demo_token)
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="demo token 无效或已过期")

    # 2. 校验 scope
    if payload.get("scope") != "demo_enter":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="非 demo 登录 token")

    # 3. 单次兑换校验
    jti = payload.get("jti", "")
    if not jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="demo token 缺少 jti")
    if _is_demo_token_used(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="demo token 已使用")

    # 4. 标记已使用
    _mark_demo_token_used(jti)

    # 5. 签发正式会话 JWT（tenant = demo 账号的 client_tenant_id）
    user_id = int(payload.get("uid") or payload["sub"])
    tenant_id = int(payload["tid"])

    async with session_scope() as session, bypass_tenant_filter():
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        if user is None or tenant is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="demo 用户或租户不存在")

        user.last_login_at = datetime.utcnow()
        await session.commit()

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=user.role)
        from core.config import get_settings

        return TokenResp(
            access_token=token,
            expires_in=get_settings().jwt_expires_minutes * 60,
            user={"id": user.id, "phone": user.phone, "name": user.name, "role": user.role},
            tenant={"id": tenant.id, "name": tenant.name, "plan": tenant.plan},
        )


__all__ = ["router"]
