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
) -> str:
    settings = get_settings()
    now = int(time.time())
    exp = now + (expires_minutes or settings.jwt_expires_minutes) * 60
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "uid": user_id,
        "tid": tenant_id,
        "role": role,
        "iat": now,
        "nbf": now,
        "exp": exp,
        "jti": uuid.uuid4().hex,
        "iss": settings.jwt.get("issuer", "ddw-ai-hub"),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    try:
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
    user_ctx = {
        "user_id": int(payload.get("uid") or payload["sub"]),
        "tenant_id": int(payload["tid"]),
        "role": payload.get("role", "member"),
        "raw": payload,
    }
    request.state.user = user_ctx
    return user_ctx


async def current_admin(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    if user.get("role") not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return user


__all__ = ["bearer_scheme", "create_access_token", "current_admin", "current_user", "decode_token"]
