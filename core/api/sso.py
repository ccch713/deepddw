"""泛微OA SSO API 端点（DDW AI Hub v5.5）。

端点：
- ``GET  /api/v1/sso/cas/login``          CAS登录重定向
- ``GET  /api/v1/sso/cas/callback``       CAS ticket验证回调
- ``GET  /api/v1/sso/oauth2/login``       OAuth2登录重定向
- ``GET  /api/v1/sso/oauth2/callback``    OAuth2 code换token回调
- ``GET  /api/v1/sso/logout``             SSO退出
- ``GET  /api/v1/sso/status``             SSO配置状态查询
- ``POST /api/v1/sso/embed/token``        OA嵌入页面专用token签发（iframe场景）

OA嵌入集成方案：
1. 在泛微OA「认证应用管理」中注册DDW应用
2. 在OA门户「统一认证中心」元素中添加DDW应用图标
3. 用户点击DDW图标 → OA自动携带认证信息跳转到DDW
4. DDW验证认证信息 → 签发本地JWT → 前端加载对应页面

也支持iframe嵌入：
1. 在OA中通过iframe嵌入DDW页面
2. DDW检测到无认证时重定向到OA CAS登录
3. 登录成功后回调DDW，前端渲染对应页面
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from core.auth.jwt import create_access_token
from core.auth.weaver_sso import (
    WeaverSSOError,
    create_cas_client,
    create_oauth2_client,
)
from core.config import get_settings
from core.database.models import Tenant, User
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sso", tags=["weaver-sso"])


# ---------------------------------------------------------------------------
# 内部状态存储（生产应使用Redis）
# ---------------------------------------------------------------------------

_oauth_states: Dict[str, float] = {}  # state -> timestamp
STATE_TTL_SEC = 300

# SSO用户在User.phone字段的前缀，避免与真实手机号冲突
SSO_PHONE_PREFIX = "oa_"


# ---------------------------------------------------------------------------
# 配置读取
# ---------------------------------------------------------------------------


def _get_sso_config() -> Dict[str, Any]:
    """获取SSO配置。"""
    settings = get_settings()
    config = settings.raw.get("weaver_sso", {})
    if not config.get("enabled", False):
        raise HTTPException(status_code=503, detail="泛微OA SSO未启用")
    return config


def _get_cas_client(config: Dict[str, Any]):
    """创建CAS客户端。"""
    cas_config = config.get("cas", {})
    if not cas_config.get("enabled", False):
        raise HTTPException(status_code=503, detail="CAS认证未启用")
    return create_cas_client(cas_config)


def _get_oauth2_client(config: Dict[str, Any]):
    """创建OAuth2客户端。"""
    oauth_config = config.get("oauth2", {})
    if not oauth_config.get("enabled", False):
        raise HTTPException(status_code=503, detail="OAuth2认证未启用")
    return create_oauth2_client(oauth_config)


# ---------------------------------------------------------------------------
# 用户查找/创建
# ---------------------------------------------------------------------------


async def _find_or_create_user(user_info: Dict[str, Any]) -> Dict[str, Any]:
    """根据OA用户信息查找或创建DDW本地用户。

    账号映射：OA loginid → DDW phone (oa_{loginid})
    自动注册：OA用户首次SSO登录时自动创建DDW账号
    """
    loginid = user_info.get("username") or user_info.get("loginid") or ""
    if not loginid:
        raise HTTPException(status_code=400, detail="OA用户信息中未找到用户名")

    config = _get_sso_config()
    auto_register = config.get("auto_register", True)
    default_tenant_id = config.get("default_tenant_id", 1)

    # 用 oa_ 前缀 + loginid 作为 phone 字段（唯一标识）
    phone = f"{SSO_PHONE_PREFIX}{loginid}"

    async with session_scope() as session, bypass_tenant_filter():
        # 查找已有用户
        result = await session.execute(select(User).where(User.phone == phone))
        user = result.scalar_one_or_none()

        if user is None:
            if not auto_register:
                raise HTTPException(
                    status_code=403,
                    detail=f"用户 {loginid} 未在DDW中注册，且未开启自动注册",
                )
            # 自动创建用户
            real_name = (
                user_info.get("lastname")
                or user_info.get("displayName")
                or user_info.get("name")
                or loginid
            )

            # 确保租户存在
            tenant_result = await session.execute(
                select(Tenant).where(Tenant.id == default_tenant_id)
            )
            tenant = tenant_result.scalar_one_or_none()
            if tenant is None:
                tenant = Tenant(
                    id=default_tenant_id,
                    name="泛微OA同步",
                    plan="standard",
                    status="active",
                )
                session.add(tenant)
                await session.flush()

            user = User(
                tenant_id=default_tenant_id,
                phone=phone,
                name=real_name,
                role="member",
                status="active",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info("SSO自动注册用户: %s → phone=%s (来自泛微OA)", loginid, phone)

        return {
            "user_id": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role,
            "phone": user.phone,
            "name": user.name or loginid,
        }


def _build_frontend_redirect(user_data: Dict[str, Any], token: str, target: str = "/") -> str:
    """构建前端重定向URL，携带token信息。

    使用URL hash传递token，避免token出现在服务器日志中。
    """
    return f"{target}#token={token}&uid={user_data['user_id']}"


# ---------------------------------------------------------------------------
# CAS 认证端点
# ---------------------------------------------------------------------------


@router.get("/cas/login")
async def cas_login(request: Request, redirect: str = "/"):
    """CAS登录入口。

    前端调用此接口 → 后端返回302重定向到OA CAS登录页。
    用户在OA登录成功后 → OA重定向回 /api/v1/sso/cas/callback
    """
    config = _get_sso_config()
    cas_client = _get_cas_client(config)

    # 将redirect目标编码到state参数中
    state = f"{secrets.token_hex(8)}:{redirect}"

    login_url = cas_client.get_login_url(state=state)
    logger.info("CAS登录重定向: redirect=%s", redirect)
    return RedirectResponse(url=login_url, status_code=302)


@router.get("/cas/callback")
async def cas_callback(
    request: Request,
    ticket: str = Query(..., description="OA CAS ticket"),
    state: str = Query("", description="状态参数，包含redirect目标"),
):
    """CAS ticket验证回调。

    OA登录成功后重定向到此端点，携带ticket参数。
    后端用ticket向OA验证 → 获取用户信息 → 签发DDW JWT → 重定向到前端。
    """
    config = _get_sso_config()
    cas_client = _get_cas_client(config)

    # 验证ticket
    try:
        user_info = await cas_client.validate_ticket(ticket)
    except WeaverSSOError as e:
        logger.error("CAS ticket验证失败: %s", e)
        raise HTTPException(status_code=401, detail=f"CAS认证失败: {e}")

    logger.info("CAS认证成功: user=%s", user_info.get("username"))

    # 查找或创建用户
    user_data = await _find_or_create_user(user_info)

    # 签发DDW JWT
    token = create_access_token(
        user_id=user_data["user_id"],
        tenant_id=user_data["tenant_id"],
        role=user_data["role"],
        extra={"source": "weaver_cas"},
    )

    # 解析redirect目标
    redirect = "/"
    if ":" in state:
        _, redirect = state.split(":", 1)

    # 重定向到前端，携带token
    frontend_url = _build_frontend_redirect(user_data, token, redirect)
    return RedirectResponse(url=frontend_url, status_code=302)


# ---------------------------------------------------------------------------
# OAuth2 认证端点
# ---------------------------------------------------------------------------


@router.get("/oauth2/login")
async def oauth2_login(request: Request, redirect: str = "/"):
    """OAuth2登录入口。

    前端调用此接口 → 后端返回302重定向到OA OAuth2授权页。
    """
    config = _get_sso_config()
    oauth_client = _get_oauth2_client(config)

    state = secrets.token_hex(16)
    _oauth_states[state] = time.time()

    authorize_url = oauth_client.get_authorize_url(state=state)
    logger.info("OAuth2登录重定向: redirect=%s", redirect)
    return RedirectResponse(url=authorize_url, status_code=302)


@router.get("/oauth2/callback")
async def oauth2_callback(
    request: Request,
    code: str = Query(..., description="OA OAuth2授权码"),
    state: str = Query("", description="防CSRF状态参数"),
):
    """OAuth2 code换token回调。

    OA授权成功后重定向到此端点，携带code参数。
    后端用code换token → 获取用户信息 → 签发DDW JWT → 重定向到前端。
    """
    # 验证state
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="无效的state参数，可能已过期")
    del _oauth_states[state]

    config = _get_sso_config()
    oauth_client = _get_oauth2_client(config)

    # 用code换token
    try:
        token_result = await oauth_client.exchange_code(code)
    except WeaverSSOError as e:
        logger.error("OAuth2 token获取失败: %s", e)
        raise HTTPException(status_code=401, detail=f"OAuth2认证失败: {e}")

    access_token = token_result.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="OAuth2响应中未包含access_token")

    # 获取用户信息
    try:
        user_info = await oauth_client.get_user_info(access_token)
    except WeaverSSOError as e:
        logger.error("OAuth2用户信息获取失败: %s", e)
        raise HTTPException(status_code=401, detail=f"OAuth2用户信息获取失败: {e}")

    logger.info("OAuth2认证成功: user=%s", user_info.get("username") or user_info.get("loginid"))

    # 查找或创建用户
    user_data = await _find_or_create_user(user_info)

    # 签发DDW JWT
    ddw_token = create_access_token(
        user_id=user_data["user_id"],
        tenant_id=user_data["tenant_id"],
        role=user_data["role"],
        extra={"source": "weaver_oauth2"},
    )

    # 重定向到前端
    frontend_url = _build_frontend_redirect(user_data, ddw_token, "/")
    return RedirectResponse(url=frontend_url, status_code=302)


# ---------------------------------------------------------------------------
# 通用端点
# ---------------------------------------------------------------------------


@router.get("/logout")
async def sso_logout(redirect: str = "/"):
    """SSO退出。

    先退出OA认证会话，再跳转回DDW。
    """
    config = _get_sso_config()
    protocol = config.get("active_protocol", "cas")

    if protocol == "cas":
        cas_config = config.get("cas", {})
        cas_client = create_cas_client(cas_config)
        oa_logout_url = cas_client.get_logout_url(redirect_url=redirect)
    else:
        oauth_config = config.get("oauth2", {})
        oauth_client = create_oauth2_client(oauth_config)
        oa_logout_url = oauth_client.get_logout_url(redirect_url=redirect)

    return RedirectResponse(url=oa_logout_url, status_code=302)


@router.get("/status")
async def sso_status():
    """查询SSO配置状态（不暴露密钥）。"""
    settings = get_settings()
    config = settings.raw.get("weaver_sso", {})

    if not config.get("enabled", False):
        return {"enabled": False, "message": "泛微OA SSO未启用"}

    cas_config = config.get("cas", {})
    oauth_config = config.get("oauth2", {})

    return {
        "enabled": True,
        "active_protocol": config.get("active_protocol", "cas"),
        "auto_register": config.get("auto_register", True),
        "cas": {
            "enabled": cas_config.get("enabled", False),
            "oa_url": cas_config.get("oa_url", ""),
            "appid": cas_config.get("appid", ""),
        },
        "oauth2": {
            "enabled": oauth_config.get("enabled", False),
            "oa_url": oauth_config.get("oa_url", ""),
            "client_id": oauth_config.get("client_id", ""),
        },
    }


# ---------------------------------------------------------------------------
# OA嵌入专用token签发
# ---------------------------------------------------------------------------


class EmbedTokenReq(BaseModel):
    """OA嵌入页面专用token签发请求。"""
    oa_user_id: str
    oa_username: str
    target_page: str = "/"
    timestamp: int
    sign: str


@router.post("/embed/token")
async def embed_token(req: EmbedTokenReq):
    """OA嵌入页面专用token签发。

    当DDW页面通过iframe嵌入OA时，OA可以通过此接口签发DDW token。
    需要OA端配合传递签名信息防伪造。

    签名算法：HMAC-SHA256(oa_user_id + oa_username + timestamp, shared_secret)
    """
    config = _get_sso_config()
    shared_secret = config.get("embed_shared_secret", "")

    if not shared_secret:
        raise HTTPException(status_code=503, detail="嵌入模式未配置shared_secret")

    # 验证签名
    expected_sign = hmac.new(
        shared_secret.encode(),
        f"{req.oa_user_id}{req.oa_username}{req.timestamp}".encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(req.sign, expected_sign):
        raise HTTPException(status_code=403, detail="签名验证失败")

    # 检查时间戳（5分钟有效）
    if abs(time.time() - req.timestamp) > 300:
        raise HTTPException(status_code=403, detail="签名已过期")

    # 查找或创建用户
    user_info = {"username": req.oa_username, "loginid": req.oa_username, "source": "weaver_embed"}
    user_data = await _find_or_create_user(user_info)

    # 签发JWT
    token = create_access_token(
        user_id=user_data["user_id"],
        tenant_id=user_data["tenant_id"],
        role=user_data["role"],
        extra={"source": "weaver_embed"},
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 720 * 60,
        "user": user_data,
        "target_page": req.target_page,
    }
