"""deepDDW 全局网关 Token 门禁（P0-1 修复）。

开源版无账号体系（PRD）：只保留静态访问 Token 门禁。
所有受保护端点（含 MCP 全部端点）必须携带：

    Authorization: Bearer <token>
或
    X-DDW-Token: <token>

无效 / 缺失 → 401。Token 由部署方配置：

- 环境变量 ``DDW_ACCESS_TOKEN``（生产推荐）
- 或 ``config/deployment.yaml`` 的 ``auth.access_token``

⚠️ 未配置 Token 时**拒绝启动**（抛 RuntimeError）——绝不使用公开默认值，
避免门禁形同虚设（对抗验收 P2-3 修复）。

⚠️ Token 建议使用纯 ASCII 字符（HTTP header 传输中文/非 ASCII 可能
被客户端编码破坏导致 401，对抗验收 P2-4 提示）。

本模块同时提供 ASGI 门禁包装器（用于 streamable-http 的 Starlette Route）
与 FastAPI 依赖（用于经典端点 /api/v1/mcp/jsonrpc|sse|info 与网关 API）。
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

_ACCESS_TOKEN_ATTR = "access_token"

WWW_AUTHENTICATE = 'Bearer realm="deepddw"'


class AccessTokenNotConfiguredError(RuntimeError):
    """未配置访问 Token（启动期抛错，拒绝以不安全方式运行）。"""


def get_access_token() -> str:
    """解析当前生效的静态访问 Token（环境变量 > deployment.yaml）。

    未配置 → 抛 :class:`AccessTokenNotConfiguredError`（拒绝启动/拒绝服务）。
    """
    env = os.environ.get("DDW_ACCESS_TOKEN")
    if env:
        return env
    try:
        from core.config import get_settings

        cfg = get_settings().raw.get("auth", {}).get(_ACCESS_TOKEN_ATTR)
        if isinstance(cfg, str) and cfg.strip():
            return cfg.strip()
    except Exception as exc:  # noqa: BLE001  # 配置解析失败不阻断鉴权模块
        logger.warning("token_gate: read config failed: %s", exc)
    raise AccessTokenNotConfiguredError(
        "DDW_ACCESS_TOKEN 未配置（或 config/deployment.yaml auth.access_token 为空）。"
        "deepDDW 拒绝以未设 Token 的方式启动/服务——请显式配置后重试。"
        "参考 .env.example / README。"
    )


def verify_token(token: str) -> bool:
    """常量时间比较校验 Token。"""
    expected = get_access_token()
    if not token or not expected:
        return False
    return hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))


def extract_token(headers: Dict[str, str]) -> Optional[str]:
    """从请求头提取 Token（Authorization: Bearer 优先，其次 X-DDW-Token）。"""
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    token = headers.get("x-ddw-token", "").strip()
    return token or None


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="missing or invalid access token",
        headers={"WWW-Authenticate": WWW_AUTHENTICATE},
    )


# ---------------------------------------------------------------------------
# FastAPI 依赖（经典 MCP 端点 + 网关 API）
# ---------------------------------------------------------------------------


def require_access_token(request: Request) -> Dict[str, Any]:
    """FastAPI 依赖：校验静态访问 Token，失败 → 401。

    返回 claims dict（兼容原有 current_user 的调用方签名）：
    ``{"sub": "token", "token": <token>, "tenant_id": 0,
    "user_id": 0, "role": "superadmin"}``
    —— deepDDW 单用户模型：token 持有者即平台管理员（无账号/租户体系）。
    """
    headers = {k.lower(): v for k, v in request.headers.items()}
    token = extract_token(headers)
    if token is None or not verify_token(token):
        raise unauthorized()
    return {
        "sub": "token",
        "token": token,
        "tenant_id": 0,
        "user_id": 0,
        "role": "superadmin",
    }


# ---------------------------------------------------------------------------
# ASGI 门禁包装器（streamable-http 的 Starlette Route）
# ---------------------------------------------------------------------------


class TokenGateASGI:
    """把任意 ASGI 应用包上 Token 门禁；未授权直接回 401，不再往下分发。"""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers") or []
        }
        token = extract_token(headers)
        if token is None or not verify_token(token):
            await _send_json_401(send)
            return
        await self.app(scope, receive, send)


async def _send_json_401(send: Any) -> None:
    body = (
        b'{"detail":"missing or invalid access token"}'
    )
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", WWW_AUTHENTICATE.encode("latin-1")),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


__all__ = [
    "get_access_token",
    "verify_token",
    "extract_token",
    "require_access_token",
    "TokenGateASGI",
    "unauthorized",
]
