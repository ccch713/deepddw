"""FastAPI dependency injection for Principal (knowledge base ACL context).

Provides:
- set_principal_context / get_principal_context for testing (ContextVar pattern)
- get_principal as FastAPI Depends for production use
"""
from __future__ import annotations

import contextvars
from typing import Optional

from fastapi import Request

from .acl import Principal

# ---------------------------------------------------------------------------
# ContextVar for test / override
# ---------------------------------------------------------------------------

_principal_var: contextvars.ContextVar[Optional[Principal]] = contextvars.ContextVar(
    "ddw_kb_principal", default=None
)


def set_principal_context(p: Optional[Principal]) -> contextvars.Token:
    """Set the current principal context (for testing). Returns a reset token."""
    return _principal_var.set(p)


def get_principal_context() -> Optional[Principal]:
    """Get the current principal from ContextVar, or None if not set."""
    return _principal_var.get()


def reset_principal_context(token: contextvars.Token) -> None:
    """Reset principal context using a previously returned token."""
    _principal_var.reset(token)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_principal(request: Request) -> Principal:
    """Resolve Principal from ContextVar (test override) or request headers.

    Production: extract from core.auth.jwt.decode_token or request.state.user.
    Fallback: read X-User-Id / X-User-Role / X-Dept-Id / X-Tenant-Id headers.
    """
    # 1. Test override via ContextVar
    ctx = get_principal_context()
    if ctx is not None:
        return ctx

    # 2. Try request.state.user (set by TenantContextMiddleware)
    user_ctx = getattr(getattr(request, "state", None), "user", None)
    if user_ctx and isinstance(user_ctx, dict) and user_ctx.get("user_id"):
        return Principal(
            user_id=int(user_ctx["user_id"]),
            tenant_id=int(user_ctx.get("tenant_id", 0)),
            role=user_ctx.get("role", "member"),
            department_id=user_ctx.get("department_id"),
        )

    # 3. Try core.auth.jwt.decode_token (direct JWT parsing, no Depends)
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            from core.auth.jwt import decode_token
            payload = decode_token(token)
            role = payload.get("role", "member")
            return Principal(
                user_id=int(payload.get("uid") or payload.get("sub", 0)),
                tenant_id=int(payload.get("tid", 0)),
                role=role,
                department_id=payload.get("department_id"),
            )
    except Exception:  # noqa: BLE001
        pass

    # 4. Fallback: request headers
    user_id = request.headers.get("X-User-Id")
    if user_id is None:
        from fastapi import HTTPException

        raise HTTPException(401, "Missing authentication: no user context available")

    return Principal(
        user_id=int(user_id),
        tenant_id=int(request.headers.get("X-Tenant-Id", "0")),
        role=request.headers.get("X-User-Role", "member"),
        department_id=(
            int(v) if (v := request.headers.get("X-Dept-Id")) else None
        ),
    )
