"""org_relay 配置（lazy getter 模式，同 core.config.get_tls_config）。

来源优先级：环境变量 > config/deployment.yaml ``org_relay:`` 段 > 默认值。
默认**关闭**；``server_base_url`` 无任何预置外部默认——它指向且仅指向
本实例自己的端点（由部署者显式配置，或按请求 Host 推导）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def get_org_relay_config() -> Dict[str, Any]:
    """合并后的 org_relay 配置（每次调用即时读取，支持热改配置重启生效）。"""
    try:
        from core.config import get_settings

        section = get_settings().raw.get("org_relay") or {}
        if not isinstance(section, dict):
            section = {}
    except Exception:  # noqa: BLE001
        section = {}

    tokens_env = [t.strip() for t in _env("DDW_ORG_RELAY_PRODUCT_TOKENS").split(",") if t.strip()]
    tokens_yaml = [t for t in (section.get("product_tokens") or []) if isinstance(t, str) and t]

    return {
        "enabled": _env_bool("DDW_ORG_RELAY_ENABLED", bool(section.get("enabled", False))),
        "product_tokens": tokens_env or tokens_yaml,
        "server_base_url": _env("DDW_ORG_RELAY_SERVER_BASE_URL", str(section.get("server_base_url", ""))),
        "rate_limit_per_token": _env_int("DDW_ORG_RELAY_RATE_LIMIT", int(section.get("rate_limit_per_token", 10))),
        "rate_limit_window_seconds": _env_int(
            "DDW_ORG_RELAY_RATE_WINDOW", int(section.get("rate_limit_window_seconds", 60))
        ),
        "bindcode_ttl_min": _env_int("DDW_ORG_RELAY_TTL_MIN", int(section.get("bindcode_ttl_min", 15))),
        "bindcode_max_uses": _env_int("DDW_ORG_RELAY_MAX_USES", int(section.get("bindcode_max_uses", 50))),
    }


def org_relay_enabled() -> bool:
    return get_org_relay_config()["enabled"]


def product_tokens() -> List[str]:
    return list(get_org_relay_config()["product_tokens"])
