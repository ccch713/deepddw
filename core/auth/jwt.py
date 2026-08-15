"""JWT 签发 / 校验（DDW AI Hub v5.4 — 模块 B 配套）。

支持 HS256（默认，对齐 deployment.yaml）；如需 RS256，传入 private/public key。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import get_settings
from core.constants.roles import ADMIN_ROLES

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(
    user_id: int,
    tenant_id: int,
    role: str = "member",
    extra: Optional[Dict[str, Any]] = None,
    expires_minutes: Optional[int] = None,
    agent_id: Optional[int] = None,
) -> str:
    settings = get_settings()
    now = int(time.time())
    exp = now + (expires_minutes or settings.jwt_expires_minutes) * 60
    # 数字员工使用 agent:{id} 格式，人类用户使用 {user_id} 格式
    sub = f"agent:{agent_id}" if role == "digital_agent" and agent_id else str(user_id)
    payload: Dict[str, Any] = {
        "sub": sub,
        "uid": user_id,
        "tid": tenant_id,
        "role": role,
        "iat": now,
        "nbf": now,
        "exp": exp,
        "jti": uuid.uuid4().hex,
        "iss": settings.jwt.get("issuer", "ddw-ai-hub"),
    }
    # 数字员工额外字段
    if role == "digital_agent" and agent_id:
        payload["agent_id"] = agent_id
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


_ALLOWED_JWT_ALGORITHMS = ("HS256", "HS384", "HS512")


def decode_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    try:
        # Extract header to block alg=none before pyjwt processes it
        unverified_header = jwt.get_unverified_header(token)
        if unverified_header.get("alg", "").lower() == "none":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token: algorithm 'none' is not allowed")
        if unverified_header.get("alg") not in _ALLOWED_JWT_ALGORITHMS:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token: unsupported algorithm")

        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {e}")


# ---------------------------------------------------------------------------
# FastAPI 依赖
# ---------------------------------------------------------------------------


async def current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Dict[str, Any]:
    """从 Authorization: Bearer <token> 中提取当前用户，绑定到 request.state。"""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    payload = decode_token(credentials.credentials)
    role = payload.get("role", "member")
    sub = payload.get("sub", "")

    # 数字员工：sub 格式为 "agent:{id}"
    if role == "digital_agent" and isinstance(sub, str) and sub.startswith("agent:"):
        agent_id = int(sub.split(":", 1)[1])
        user_ctx = {
            "user_id": int(payload.get("uid", 0)),
            "tenant_id": int(payload["tid"]),
            "role": role,
            "agent_id": agent_id,
            "is_digital_agent": True,
            "raw": payload,
        }
    else:
        user_ctx = {
            "user_id": int(payload.get("uid") or sub),
            "tenant_id": int(payload["tid"]),
            "role": role,
            "is_digital_agent": False,
            "raw": payload,
        }
    request.state.user = user_ctx
    return user_ctx


async def current_admin(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    if user.get("role") not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return user


__all__ = ["bearer_scheme", "create_access_token", "current_admin", "current_user", "decode_token"]
