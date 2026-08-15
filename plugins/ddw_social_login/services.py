"""OAuth 流程 + 账号解析/注册 + 绑定/解绑。"""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from cachetools import TTLCache
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api.auth import _write_login_audit
from core.auth.jwt import create_access_token
from core.database.models import Tenant, User, UserBinding
from core.database.session import session_scope

from .config_manager import (
    PROVIDER_DISPLAY_NAMES,
    PROVIDER_MAP,
    PROVIDER_PHONE_PREFIX,
    ConfigManager,
)

logger = logging.getLogger(__name__)

# ---- State 缓存（CSRF 防护，用 cachetools 替代 redis）----
_state_cache: TTLCache = TTLCache(maxsize=4096, ttl=300)


def _generate_callback_url(base_url: str, provider: str) -> str:
    """生成 OAuth 回调 URL。"""
    return f"{base_url}/api/v1/plugins/ddw-social-login/callback/{provider}"


# ================================================================
# 授权入口
# ================================================================


async def build_auth_redirect(
    provider: str,
    config_manager: ConfigManager,
    base_url: str,
    next: str = "/pal.html",
) -> str:
    """生成第三方授权页 URL（同步 senweaver 调用通过 to_thread 包装）。"""
    auth_config = config_manager.get_channel_config(provider)
    if not auth_config:
        raise HTTPException(status_code=400, detail={"code": "CHANNEL_NOT_CONFIGURED", "message": f"通道 {provider} 未配置"})

    # 更新回调 URL（如果管理员没填）
    if not auth_config.redirect_uri:
        auth_config.redirect_uri = _generate_callback_url(base_url, provider)

    state = str(secrets.token_urlsafe(32))
    _state_cache[state] = {
        "provider": provider,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "next": next,  # 登录后跳转页
    }

    source_cls = PROVIDER_MAP[provider]
    from senweaver_oauth import AuthRequest

    auth_request = AuthRequest.build(source_cls, auth_config)

    # senweaver-oauth 的 authorize() 是同步的，用 to_thread 包装
    auth_url = await asyncio.to_thread(auth_request.authorize, state)
    return auth_url


# ================================================================


def _extract_client_ip(request: Request) -> Optional[str]:
    """提取客户端 IP。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ================================================================
# 回调处理
# ================================================================


async def handle_callback(
    provider: str,
    code: str,
    state: str,
    request: Request,
    config_manager: ConfigManager,
) -> Dict[str, Any]:
    """处理 OAuth 回调：校验 state → 换 token → 查/注册用户 → 签发 JWT。

    返回: {"access_token": str, "user": dict, "tenant": dict}
    """
    # 1. 校验 state（一次性）
    cached = _state_cache.pop(state, None)
    if not cached:
        raise HTTPException(status_code=401, detail={"code": "INVALID_STATE", "message": "无效的 state 参数"})

    # 2. 获取配置
    auth_config = config_manager.get_channel_config(provider)
    if not auth_config:
        raise HTTPException(status_code=400, detail={"code": "CHANNEL_NOT_CONFIGURED", "message": f"通道 {provider} 未配置"})
    if not auth_config.redirect_uri:
        auth_config.redirect_uri = _generate_callback_url(str(request.base_url).rstrip("/"), provider)

    # 3. 调 senweaver 拿用户信息（同步 → to_thread）
    source_cls = PROVIDER_MAP[provider]
    from senweaver_oauth import AuthRequest

    auth_request = AuthRequest.build(source_cls, auth_config)
    callback_params = {"code": code, "state": state}

    response = await asyncio.to_thread(auth_request.login, callback_params)
    if not response or response.code != 200 or not response.data:
        error_msg = response.message if response else "OAuth 登录失败"
        raise HTTPException(status_code=401, detail={"code": "OAUTH_LOGIN_FAILED", "message": error_msg})

    social_user = response.data
    openid = social_user.uuid

    # 4. 查绑定 → 解析用户
    async with session_scope() as session:
        user, is_new = await _resolve_or_create_user(
            session=session,
            provider=provider,
            social_user=social_user,
            openid=openid,
            auto_register=config_manager.auto_register,
            default_tenant_id=config_manager.default_tenant_id,
            default_role=getattr(config_manager, 'default_role', 'member'),
        )

        if user.status != "active":
            raise HTTPException(status_code=403, detail={"code": "ACCOUNT_DISABLED", "message": "账号已禁用"})

        # 5. 签发 JWT
        token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role,
        )

        # 6. 审计
        client_ip = _extract_client_ip(request)
        ua = request.headers.get("user-agent")
        try:
            await _write_login_audit(
                phone=user.phone,
                ip=client_ip,
                user_agent=ua,
                method=f"social_{provider}",
                success=True,
            )
        except Exception as exc:
            logger.warning("写入登录审计失败: %s", exc)

        # 7. 查询租户信息
        tenant_result = await session.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        tenant = tenant_result.scalar_one_or_none()

        user_dict = {
            "id": user.id,
            "name": user.name,
            "phone": user.phone,
            "role": user.role,
            "status": user.status,
        }
        tenant_dict = {
            "id": tenant.id if tenant else user.tenant_id,
            "name": tenant.name if tenant else "",
        }

    return {
        "access_token": token,
        "user": user_dict,
        "tenant": tenant_dict,
    }


async def _resolve_or_create_user(
    session: AsyncSession,
    provider: str,
    social_user: Any,
    openid: str,
    auto_register: bool,
    default_tenant_id: int,
    default_role: str = "member",
) -> Tuple[User, bool]:
    """解析已有绑定或自动注册新用户。返回 (User, is_new)。"""
    # 查 UserBinding
    result = await session.execute(
        select(UserBinding).where(
            UserBinding.provider == provider,
            UserBinding.provider_uid == openid,
            UserBinding.is_active.is_(True),
        )
    )
    bindings = list(result.scalars().all())

    if bindings:
        # 多租户冲突检测
        user_ids = list({b.user_id for b in bindings})
        if len(user_ids) > 1:
            raise HTTPException(
                status_code=409,
                detail={"code": "MULTI_TENANT", "message": "该账号绑定了多个租户，请指定 tenant_id"},
            )
        user_result = await session.execute(select(User).where(User.id == user_ids[0]))
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "绑定用户不存在"})
        return user, False

    # 未找到绑定
    if not auto_register:
        raise HTTPException(
            status_code=401,
            detail={"code": "ACCOUNT_NOT_FOUND", "message": "未找到绑定账号且未开启自动注册"},
        )

    # 自动注册
    user = await _auto_register(session, provider, social_user, default_tenant_id, default_role)
    return user, True


async def _auto_register(
    session: AsyncSession,
    provider: str,
    social_user: Any,
    default_tenant_id: int,
    default_role: str = "member",
) -> User:
    """扫码首次登录自动注册。"""
    from core.api.auth import hash_password

    prefix = PROVIDER_PHONE_PREFIX.get(provider, "so")
    placeholder_phone = f"{prefix}_{social_user.uuid[:16]}"
    random_password = secrets.token_urlsafe(16)
    password_hash = hash_password(random_password)

    user = User(
        phone=placeholder_phone,
        password_hash=password_hash,
        name=social_user.nickname or f"{PROVIDER_DISPLAY_NAMES.get(provider, '社交')}用户",
        role=default_role,  # 从配置读取，问渠为 student
        status="active",
        tenant_id=default_tenant_id,
    )
    session.add(user)
    await session.flush()  # 拿到 user.id

    binding = UserBinding(
        user_id=user.id,
        tenant_id=user.tenant_id,
        provider=provider,
        provider_uid=social_user.uuid,
        provider_name=social_user.nickname,
        binding_type="login",
        is_primary=True,
        is_active=True,
    )
    session.add(binding)
    await session.flush()
    return user


# ================================================================
# 绑定 / 解绑
# ================================================================


async def bind_provider(
    user_id: int,
    tenant_id: int,
    provider: str,
    code: str,
    state: str,
    config_manager: ConfigManager,
) -> Dict[str, Any]:
    """已登录用户绑定第三方账号。"""
    auth_config = config_manager.get_channel_config(provider)
    if not auth_config:
        raise HTTPException(status_code=400, detail={"code": "CHANNEL_NOT_CONFIGURED", "message": f"通道 {provider} 未配置"})

    # 校验 state（一次性）
    cached = _state_cache.pop(state, None)
    if not cached:
        raise HTTPException(status_code=401, detail={"code": "INVALID_STATE", "message": "无效的 state 参数"})

    # 调 senweaver 拿用户信息
    source_cls = PROVIDER_MAP[provider]
    from senweaver_oauth import AuthRequest

    auth_request = AuthRequest.build(source_cls, auth_config)
    response = await asyncio.to_thread(auth_request.login, {"code": code, "state": state})
    if not response or response.code != 200 or not response.data:
        error_msg = response.message if response else "OAuth 登录失败"
        raise HTTPException(status_code=401, detail={"code": "OAUTH_LOGIN_FAILED", "message": error_msg})

    social_user = response.data

    async with session_scope() as session:
        # 检查是否已绑定
        result = await session.execute(
            select(UserBinding).where(
                UserBinding.user_id == user_id,
                UserBinding.provider == provider,
                UserBinding.is_active.is_(True),
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail={"code": "ALREADY_BOUND", "message": f"已绑定 {PROVIDER_DISPLAY_NAMES.get(provider, provider)}"})

        binding = UserBinding(
            user_id=user_id,
            tenant_id=tenant_id,
            provider=provider,
            provider_uid=social_user.uuid,
            provider_name=social_user.nickname,
            binding_type="login",
            is_primary=False,
            is_active=True,
        )
        session.add(binding)
        await session.commit()

    return {"ok": True, "provider": provider}


async def unbind_provider(
    user_id: int,
    provider: str,
) -> Dict[str, Any]:
    """已登录用户解绑第三方账号（软删除：is_active=False）。"""
    async with session_scope() as session:
        result = await session.execute(
            select(UserBinding).where(
                UserBinding.user_id == user_id,
                UserBinding.provider == provider,
                UserBinding.is_active.is_(True),
            )
        )
        binding = result.scalar_one_or_none()
        if not binding:
            raise HTTPException(status_code=404, detail={"code": "NOT_BOUND", "message": f"未绑定 {PROVIDER_DISPLAY_NAMES.get(provider, provider)}"})
        binding.is_active = False
        await session.commit()

    return {"ok": True}


async def list_bindings(
    user_id: int,
) -> list:
    """查询当前用户的绑定列表。"""
    async with session_scope() as session:
        result = await session.execute(
            select(UserBinding).where(
                UserBinding.user_id == user_id,
                UserBinding.is_active.is_(True),
            )
        )
        bindings = list(result.scalars().all())
    return [
        {
            "provider": b.provider,
            "provider_name": b.provider_name,
            "bound_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in bindings
    ]
