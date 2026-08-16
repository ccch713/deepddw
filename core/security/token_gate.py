"""deepDDW 全局网关 Token 门禁（P0-1 修复 + 体验优化 v2）。

开源版无账号体系（PRD）：默认只保留静态访问 Token 门禁。
所有受保护端点（含 MCP 全部端点）必须携带：

    Authorization: Bearer <token>
或
    X-DDW-Token: <token>

无效 / 缺失 → 401。Token 由部署方配置：

- 环境变量 ``DDW_ACCESS_TOKEN``（生产推荐；支持短码，如 ``ddw-7f3k``）
- 或 ``config/deployment.yaml`` 的 ``auth.access_token``

⚠️ 未配置 Token 时**拒绝启动**（抛 RuntimeError）——绝不使用公开默认值，
避免门禁形同虚设（对抗验收 P2-3 修复）。

⚠️ Token 建议使用纯 ASCII 字符（HTTP header 传输中文/非 ASCII 可能
被客户端编码破坏导致 401，对抗验收 P2-4 提示）。

🔓 局域网免密模式（体验优化 A，2026-08-16）：
- 默认开启（``DDW_LAN_BYPASS=1`` 或 config security.lan_bypass=true）：
  来自内网（127.0.0.1 / 10.x / 172.16-31.x / 192.168.x）的请求**免 Token 放行**，
  覆盖 PWA 启动页、MCP、网关 API——手机在家连 WiFi 直接可用，零配置。
- 外网/跨网访问仍要求 Token（保护公网暴露面）。
- 关闭：``DDW_LAN_BYPASS=0`` 时恢复"一律要求 Token"（适合公网部署）。

本模块同时提供 ASGI 门禁包装器（用于 streamable-http 的 Starlette Route）
与 FastAPI 依赖（用于经典端点 /api/v1/mcp/jsonrpc|sse|info 与网关 API）。
"""

from __future__ import annotations

import hmac
import ipaddress
import logging
import os
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

_ACCESS_TOKEN_ATTR = "access_token"

WWW_AUTHENTICATE = 'Bearer realm="deepddw"'


class AccessTokenNotConfiguredError(RuntimeError):
    """未配置访问 Token（启动期抛错，拒绝以不安全方式运行）。"""


def lan_bypass_enabled() -> bool:
    """局域网免密开关：env > config ``security.lan_bypass`` > 默认关。

    P0-4：默认关闭——公网误部署不因默认值暴露；需要局域网免密时显式开启。
    """
    env = os.environ.get("DDW_LAN_BYPASS")
    if env is not None:
        return env.strip().lower() not in ("0", "false", "no", "off")
    try:
        from core.config import get_settings

        v = get_settings().raw.get("security", {}).get("lan_bypass")
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() not in ("0", "false", "no", "off")
    except Exception:  # noqa: BLE001
        pass
    return False  # 默认关（安全优先；显式开启才生效）


# P0-4：严格三网段（RFC 1918）+ 回环；不用 is_private 广义判定（避免
# 100.64/10 CGNAT、厂商内网段等被误判为 LAN 放行）
_LAN_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
)


def is_lan_client(host: Optional[str]) -> bool:
    """判断客户端 IP 是否属于内网/回环地址（严格三网段 + 回环）。"""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    return any(ip in net for net in _LAN_NETWORKS)


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


def _trusted_proxies() -> list:
    """可信反代白名单（env DDW_TRUSTED_PROXIES > config security.trusted_proxies）。"""
    env = os.environ.get("DDW_TRUSTED_PROXIES")
    if env:
        return [
            c.strip() for c in env.split(",") if c.strip()
        ]
    try:
        from core.config import get_settings

        return list(get_settings().raw.get("security", {}).get("trusted_proxies", []) or [])
    except Exception:  # noqa: BLE001
        return []


def _peer_is_trusted_proxy(peer_host: Optional[str]) -> bool:
    """直连 peer 是否在可信反代白名单（IP 或 CIDR）。"""
    if not peer_host:
        return False
    try:
        peer = ipaddress.ip_address(peer_host.split("%")[0])
    except ValueError:
        return False
    for item in _trusted_proxies():
        try:
            net = ipaddress.ip_network(item, strict=False)
            if peer in net:
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request) -> Optional[str]:
    """取客户端真实 IP。

    P0-4：仅当直连 peer 在 trusted_proxies 白名单时才信任
    ``X-Forwarded-For`` / ``X-Real-IP``（防伪造头绕过 LAN/Token 判定）；
    否则一律用 ``request.client.host``。
    """
    peer = request.client.host if request.client else None
    if _peer_is_trusted_proxy(peer):
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            first = fwd.split(",")[0].strip()
            if first:
                return first
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()
    return peer


def _authorized(token: Optional[str], host: Optional[str]) -> bool:
    """综合判定：LAN 免密 或 Token 有效。"""
    if lan_bypass_enabled() and is_lan_client(host):
        return True
    return token is not None and verify_token(token)


# ---------------------------------------------------------------------------
# FastAPI 依赖（经典 MCP 端点 + 网关 API）
# ---------------------------------------------------------------------------


def require_access_token(request: Request) -> Dict[str, Any]:
    """FastAPI 依赖：LAN 免密或 Token 校验，失败 → 401。

    返回 claims dict（兼容原有 current_user 的调用方签名）：
    ``{"sub": "token", "token": <token>, "tenant_id": 0,
    "user_id": 0, "role": "superadmin"}``
    —— deepDDW 单用户模型：token 持有者即平台管理员（无账号/租户体系）。
    """
    headers = {k.lower(): v for k, v in request.headers.items()}
    token = extract_token(headers)
    host = client_ip(request)
    if not _authorized(token, host):
        raise unauthorized()
    return {
        "sub": "token",
        "token": token or "lan-bypass",
        "tenant_id": 0,
        "user_id": 0,
        "role": "superadmin",
    }


# ---------------------------------------------------------------------------
# ASGI 门禁包装器（streamable-http 的 Starlette Route）
# ---------------------------------------------------------------------------


class TokenGateASGI:
    """把任意 ASGI 应用包上 Token 门禁；LAN 免密或 Token 有效放行，否则 401。"""

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
        # ASGI scope 无 request 对象：从 scope 取 client
        client = scope.get("client")
        host = client[0] if client else None
        if not _authorized(token, host):
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
    "lan_bypass_enabled",
    "is_lan_client",
    "client_ip",
]
