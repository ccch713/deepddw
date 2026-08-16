"""P0-2（multidevice）：网关级限流与过载保护。

- 内存滑动窗口：按 Token（X-DDW-Token / Bearer）与客户端 IP 双维度；
- 标准库实现（time + dict），零新依赖；
- 超限 429 + Retry-After；全局过载（总容量）503；
- 配置驱动：deployment.yaml security.rate_limit.* + env，默认 fail-closed；
- /health 与 OPTIONS 放行（不计数）；LLM 429 重试语义不变。
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from core.config import get_settings

logger = logging.getLogger(__name__)

# 默认值（单设备日常零误伤；20 设备场景可按配置放宽）
_DEFAULTS = {
    "per_token": 60,       # req/min/token
    "per_ip": 120,         # req/min/ip
    "global": 300,         # req/min 全网关总容量（超过 → 503 过载）
    "window_seconds": 60,
    "enabled": True,
}


def _rate_limit_config() -> Dict[str, Any]:
    """读取限流配置：deployment.yaml security.rate_limit.* > env > 默认。"""
    cfg = dict(_DEFAULTS)
    try:
        raw = get_settings().raw.get("security", {}).get("rate_limit", {}) or {}
        for k in cfg:
            if k in raw:
                cfg[k] = raw[k]
    except Exception:  # noqa: BLE001
        pass
    # env 覆盖：DDW_RATE_LIMIT_PER_TOKEN / PER_IP / GLOBAL / ENABLED
    env_map = {
        "DDW_RATE_LIMIT_PER_TOKEN": "per_token",
        "DDW_RATE_LIMIT_PER_IP": "per_ip",
        "DDW_RATE_LIMIT_GLOBAL": "global",
        "DDW_RATE_LIMIT_ENABLED": "enabled",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key)
        if val is None:
            continue
        if cfg_key == "enabled":
            cfg[cfg_key] = val.lower() in ("1", "true", "yes", "on")
        else:
            try:
                cfg[cfg_key] = int(val)
            except ValueError:
                logger.warning("invalid %s=%r, ignored", env_key, val)
    return cfg


class RateLimitMiddleware(BaseHTTPMiddleware):
    """滑动窗口限流（双维度 + 全局过载保护）。"""

    # 类级桶：跨实例共享（app 单例 + 测试可清）；
    # {bucket_key: deque[timestamps]}
    _buckets: Dict[str, Deque[float]] = defaultdict(deque)

    def __init__(  # noqa: ANN001
        self, app, config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(app)
        self._cfg_override = config

    @property
    def _cfg(self) -> Dict[str, Any]:
        """动态读取配置（支持热更新 / 测试 patch）。"""
        return self._cfg_override or _rate_limit_config()

    # ------------------------------------------------------------------ #
    # 核心
    # ------------------------------------------------------------------ #

    def _window_key(self, request: Request) -> tuple[str, str]:
        """取限流维度：token 维度 + ip 维度。"""
        token = request.headers.get("X-DDW-Token") or ""
        auth = request.headers.get("Authorization", "")
        if not token and auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        if not token:
            token = "anonymous"
        ip = request.client.host if request.client else "unknown"
        # 可信反代下信任 XFF（与 token_gate 一致的严格语义）
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            ip = xff.split(",")[0].strip() or ip
        return token, ip

    def _check(self, bucket_key: str, limit: int, now: float) -> bool:
        """滑动窗口内计数是否超限；未超限则记录一次。"""
        dq = type(self)._buckets[bucket_key]
        window = self._cfg["window_seconds"]
        # 清理窗口外的时间戳（惰性）
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True

    async def dispatch(self, request: Request, call_next) -> Any:  # noqa: ANN001
        if not self._cfg.get("enabled", True):
            return await call_next(request)
        path = request.url.path
        # 放行：健康检查 / OPTIONS 预检（不计数）
        if path == "/health" or request.method == "OPTIONS":
            return await call_next(request)

        now = time.time()
        token, ip = self._window_key(request)
        cfg = self._cfg
        # 1) 全局过载 → 503（先于单维度判断，优先保护网关）
        if not self._check("global", cfg["global"], now):
            global_bucket = type(self)._buckets["global"]
            first = global_bucket[0] if global_bucket else now
            retry = max(1, int(cfg["window_seconds"] - (now - first)))
            return JSONResponse(
                status_code=503,
                content={
                    "code": 503,
                    "message": (
                        "网关繁忙（过载保护）：请稍后重试。Retry-After 秒后恢复。"
                    ),
                    "retry_after": retry,
                },
                headers={"Retry-After": str(retry)},
            )
        # 2) 单 Token 维度
        if not self._check(f"token:{token}", cfg["per_token"], now):
            retry = max(1, int(cfg["window_seconds"]))
            return JSONResponse(
                status_code=429,
                content={
                    "code": 429,
                    "message": "请求过于频繁（限流）：请稍后重试。",
                    "retry_after": retry,
                },
                headers={"Retry-After": str(retry)},
            )
        # 3) 单 IP 维度
        if not self._check(f"ip:{ip}", cfg["per_ip"], now):
            retry = max(1, int(cfg["window_seconds"]))
            return JSONResponse(
                status_code=429,
                content={
                    "code": 429,
                    "message": "请求过于频繁（IP 限流）：请稍后重试。",
                    "retry_after": retry,
                },
                headers={"Retry-After": str(retry)},
            )
        return await call_next(request)
