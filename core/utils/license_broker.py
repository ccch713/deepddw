"""跨机授权广播 Broker（P4：双网卡授权代理）。

架构：主从 + 拉取 + TTL 缓存。
- 权威节点（主系统）：持有权威 license_state.json，暴露
  ``GET /api/v1/license/broker/state``（令牌 + HMAC 签名 + 时间戳校验）。
- 业务节点（复制容器/边缘节点）：配置 ``license.broker.url`` + 令牌，
  懒拉取权威 state 覆盖本机（TTL 内不重复拉取；Broker 不可达时回退本地缓存）。

安全：
- 节点身份：预共享令牌 ``DDW_LICENSE_BROKER_TOKEN``（env 优先，
  其次 settings ``license.broker.token``），请求头 ``X-DDW-Broker-Token``。
- 防重放/防伪造：请求头时间戳 ``X-DDW-Broker-Ts``（±300s 新鲜度）
  + ``X-DDW-Broker-Sig`` = HMAC-SHA256(token, f"{ts}:{path}")。
- state 传输沿用 ``DDW_LICENSE_STATE_KEY`` 的 HMAC（节点拉取后本机校验）。
- 失败方向：校验失败 / 超 TTL 不可达 → 调用方按 fail-closed 处理。

双网卡适配：``license.broker.url`` 可指向授权网卡地址，业务流量走业务网卡，
代码层只是一个可配置 URL。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, Optional

from core.utils.license_state import (
    get_supersede_status,
    load_license_state,
    replace_state,
)

logger = logging.getLogger(__name__)

# 请求头常量
HEADER_TOKEN = "X-DDW-Broker-Token"
HEADER_TS = "X-DDW-Broker-Ts"
HEADER_SIG = "X-DDW-Broker-Sig"

# 时间戳新鲜度窗口（秒）：防重放
TS_FRESHNESS_SECONDS = 300
# 默认拉取 TTL（秒）
DEFAULT_TTL_SECONDS = 300
# 默认请求超时（秒）
DEFAULT_TIMEOUT_SECONDS = 5

BROKER_TOKEN_ENV = "DDW_LICENSE_BROKER_TOKEN"
BROKER_STATE_PATH = "/api/v1/license/broker/state"


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def _broker_config() -> Dict[str, Any]:
    """返回 broker 配置；未启用返回空 dict。"""
    from core.config import get_settings

    try:
        cfg = get_settings().license_broker
    except Exception:  # noqa: BLE001
        return {}
    if not cfg or not cfg.get("enabled"):
        return {}
    return cfg


def _broker_token() -> str:
    """令牌解析：env 优先，其次 settings。"""
    env_token = os.environ.get(BROKER_TOKEN_ENV, "").strip()
    if env_token:
        return env_token
    cfg = _broker_config()
    return str(cfg.get("token", "") or "").strip()


# ---------------------------------------------------------------------------
# 服务端：请求校验
# ---------------------------------------------------------------------------


def _compute_signature(token: str, ts: str, path: str) -> str:
    return hmac.new(
        token.encode("utf-8"), f"{ts}:{path}".encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_broker_request(
    token: str,
    ts: str,
    signature: str,
    path: str,
    *,
    now: Optional[float] = None,
) -> bool:
    """校验 Broker 请求：令牌匹配 + 时间戳新鲜 + HMAC 签名正确。"""
    expected_token = _broker_token()
    if not expected_token or not token:
        return False
    if not hmac.compare_digest(expected_token, token):
        return False
    try:
        ts_f = float(ts)
    except (ValueError, TypeError):
        return False
    now_f = now if now is not None else time.time()
    if abs(now_f - ts_f) > TS_FRESHNESS_SECONDS:
        return False
    expected_sig = _compute_signature(token, ts, path)
    return hmac.compare_digest(expected_sig, signature or "")


def get_authoritative_state() -> Dict[str, Any]:
    """返回本机（权威节点）license_state 完整字典。"""
    return load_license_state()


def state_version(state: Dict[str, Any]) -> str:
    """state 的版本指纹（内容 hash 前 16 位），供节点比对。"""
    import json

    payload = json.dumps(state, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 客户端：拉取 + TTL 缓存 + 覆盖本机
# ---------------------------------------------------------------------------

# 进程内 TTL 缓存
_cache_state: Dict[str, Any] = {}
_cache_ts: float = 0.0
_cache_version: str = ""


def _reset_cache() -> None:
    """清空缓存（测试用）。"""
    global _cache_state, _cache_ts, _cache_version
    _cache_state = {}
    _cache_ts = 0.0
    _cache_version = ""


def pull_authoritative_state(
    *,
    force: bool = False,
    transport=None,
) -> Dict[str, Any]:
    """从 Broker 拉取权威 state（TTL 内返回缓存；失败回退缓存/空）。

    Args:
        force: 忽略 TTL 强制拉取。
        transport: 注入 httpx 传输（测试用）；默认走真实网络。

    Returns:
        权威 state dict；未启用/失败返回 {}（调用方按 fail-closed 处理）。
    """
    global _cache_state, _cache_ts, _cache_version
    cfg = _broker_config()
    if not cfg:
        return {}
    ttl = int(cfg.get("ttl_seconds", DEFAULT_TTL_SECONDS))
    now = time.time()
    if not force and _cache_ts and (now - _cache_ts) < ttl:
        return dict(_cache_state)

    token = _broker_token()
    if not token:
        logger.warning(
            "license broker: %s not configured — cannot pull", BROKER_TOKEN_ENV
        )
        return dict(_cache_state)

    base_url = str(cfg.get("url", "") or "").rstrip("/")
    if not base_url:
        logger.warning("license broker: license.broker.url not configured")
        return dict(_cache_state)
    url = base_url + BROKER_STATE_PATH
    ts = str(int(now))
    sig = _compute_signature(token, ts, BROKER_STATE_PATH)
    headers = {HEADER_TOKEN: token, HEADER_TS: ts, HEADER_SIG: sig}

    try:
        import httpx

        with httpx.Client(
            timeout=float(cfg.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
            transport=transport,
        ) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data") or payload
            state = data.get("state") or {}
    except Exception as e:  # noqa: BLE001  # Broker 不可达/异常 → 回退缓存
        logger.warning(
            "license broker pull failed: %s — falling back to cached state", e
        )
        return dict(_cache_state)

    if not isinstance(state, dict):
        logger.warning("license broker returned malformed state")
        return dict(_cache_state)

    _cache_state = dict(state)
    _cache_ts = time.time()
    _cache_version = state_version(state)
    logger.info(
        "license broker pulled authoritative state (version=%s)", _cache_version
    )
    return dict(_cache_state)


def sync_from_broker(force: bool = False, transport=None) -> bool:
    """拉取 Broker 权威 state 并覆盖本机 license_state.json。

    Returns:
        True=本机 state 已更新为权威值（或本就一致）；False=未同步（未启用/
        拉取失败/无变化判断由本机比对决定）。

    幂等：权威 state 与本机一致时不写盘。权威节点自身（url 指向自己）拉到的
    state 即本机 state → 自然无写入。
    """
    pulled = pull_authoritative_state(force=force, transport=transport)
    if not pulled:
        return False
    local = load_license_state()
    if state_version(pulled) == state_version(local):
        return True  # 已一致
    replace_state(pulled)
    logger.warning(
        "license broker: local state superseded by authoritative state "
        "(active=%s superseded_by=%s)",
        pulled.get("active_license_key"),
        pulled.get("superseded_by"),
    )
    return True


def broker_health() -> Dict[str, Any]:
    """Broker 状态摘要（供 /license/info 附带）。"""
    cfg = _broker_config()
    if not cfg:
        return {"enabled": False}
    return {
        "enabled": True,
        "url": str(cfg.get("url", "") or ""),
        "ttl_seconds": int(cfg.get("ttl_seconds", DEFAULT_TTL_SECONDS)),
        "cached": bool(_cache_ts),
        "superseded": bool(get_supersede_status().get("superseded")),
        "token_configured": bool(_broker_token()),
    }




def state_response_headers() -> dict:
    """数据同步捎带响应头（模板统一入口）：本机 state 版本 + superseded 状态。

    所有数据同步拦截点用此 helper 生成响应头（成功路径挂到注入的
    ``response.headers``；403 路径由 ``JSONResponse(headers=...)`` 携带）。
    """
    state = load_license_state()
    return {
        "X-DDW-License-State-Version": state_version(state),
        "X-DDW-License-Superseded": str(bool(state.get("superseded_by"))).lower(),
    }


__all__ = [
    "HEADER_TOKEN",
    "HEADER_TS",
    "HEADER_SIG",
    "BROKER_TOKEN_ENV",
    "BROKER_STATE_PATH",
    "TS_FRESHNESS_SECONDS",
    "verify_broker_request",
    "get_authoritative_state",
    "state_version",
    "pull_authoritative_state",
    "sync_from_broker",
    "state_response_headers",
    "broker_health",
    "_reset_cache",
]
