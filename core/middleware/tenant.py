"""租户中间件：从 JWT 解析 tenant_id 并写入 :data:`core.database.tenant_filter` contextvar。

同时：
- 注入 :func:`tenant_scope` 到请求生命周期
- 绑定 user 到 ``request.state.user``
- 支持数字员工 token（sub 格式为 "agent:{id}"）
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from core.constants.roles import Role
from core.database.tenant_filter import reset_tenant_context, set_tenant_context

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """从 ``Authorization: Bearer <jwt>`` 解析 tenant_id，绑定到请求作用域。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        token: Optional[object] = None
        # FastAPI 安全依赖会先解析；这里只做"轻量预解析"用于日志
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                from core.auth.jwt import decode_token

                payload = decode_token(auth.split(" ", 1)[1].strip())
                tid = int(payload.get("tid") or 0)
                if tid:
                    token = set_tenant_context(tid)
                    role = payload.get("role", Role.MEMBER)
                    sub = payload.get("sub", "")

                    # 数字员工：sub 格式为 "agent:{id}"
                    if role == "digital_agent" and isinstance(sub, str) and sub.startswith("agent:"):
                        agent_id = int(sub.split(":", 1)[1])
                        request.state.user = {
                            "user_id": int(payload.get("uid", 0)),
                            "tenant_id": tid,
                            "role": role,
                            "agent_id": agent_id,
                            "is_digital_agent": True,
                            "raw": payload,
                        }
                    else:
                        request.state.user = {
                            "user_id": int(payload.get("uid") or sub or 0),
                            "tenant_id": tid,
                            "role": role,
                            "is_digital_agent": False,
                            "raw": payload,
                        }
            except Exception:  # noqa: BLE001
                # 解析失败不阻断（依赖层会再校验）
                token = None
        try:
            response = await call_next(request)
            return response
        finally:
            if token is not None:
                try:
                    reset_tenant_context(token)
                except Exception:  # noqa: BLE001
                    pass


__all__ = ["TenantContextMiddleware"]
