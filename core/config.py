"""deepDDW 核心配置（开源裁剪版）。

加载 ``config/deployment.yaml``，合并环境变量覆盖。
与 v6.0 的字段保持兼容（mode / server / databases / llm_gateway / auth / events），
但已删除商业配置块：SaaS 定价、泛微 OA SSO、license broker、billing、JWT 账号体系。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 默认配置（如果 deployment.yaml 缺失）
# ---------------------------------------------------------------------------

DEFAULTS: Dict[str, Any] = {
    "mode": "standalone",
    "server": {
        "host": "0.0.0.0",
        "port": 8500,
        "workers": 1,
        "debug": True,
        "secret_key": "dev-secret-change-me",
    },
    "databases": {
        "main": {"engine": "sqlite", "path": "./data/ddw_main.db", "pool_size": 5, "echo": False},
    },
    "llm_gateway": {
        "default_provider": "deepseek",
        "providers": {
            "deepseek": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "${DDW_DEEPSEEK_API_KEY}",
                "default_model": "deepseek-chat",
                "timeout": 30,
            },
            "ollama": {
                "base_url": "http://localhost:11434",
                "default_model": "qwen2.5:7b",
                "timeout": 60,
            },
        },
    },
    "auth": {
        # 静态访问 Token（P0-1 门禁）：环境变量 DDW_ACCESS_TOKEN 优先；
        # 此处留空 → token_gate 使用开发默认值并告警（生产必须显式配置）
        "access_token": "",
    },
    "security": {
        # P0-4：局域网免密默认关闭（公网误部署不暴露）；需要时显式开启
        "lan_bypass": False,
        # 可信反代白名单（IP/CIDR）：仅直连 peer 在此列表时才信任
        # X-Forwarded-For / X-Real-IP（防伪造头绕过门禁）
        "trusted_proxies": [],
    },
    "events": {"backend": "inprocess"},
    "plugins": {"root_dir": "./plugins", "sandbox_timeout": 30},
    "logging": {"level": "INFO", "path": "./data/logs"},
}


def _resolve_env(value: Any) -> Any:
    """递归替换 ``${VAR}`` 占位符为环境变量。"""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        var = value[2:-1]
        return os.environ.get(var, value)
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


@dataclass
class Settings:
    """全局配置（注入到 FastAPI app.state.settings）。"""

    raw: Dict[str, Any] = field(default_factory=dict)
    deployment_yaml_path: Optional[Path] = None

    @classmethod
    def load(cls, deployment_yaml: Optional[Path] = None) -> "Settings":
        merged: Dict[str, Any] = dict(DEFAULTS)
        if deployment_yaml is None:
            candidate = Path(__file__).resolve().parent.parent / \
                             "config" / "deployment.yaml"
            if candidate.exists():
                deployment_yaml = candidate
        if deployment_yaml and Path(deployment_yaml).exists():
            try:
                with open(deployment_yaml, "r", encoding="utf-8") as f:
                    on_disk = yaml.safe_load(f) or {}
                _deep_merge(merged, on_disk)
                logger.info("loaded deployment.yaml from %s", deployment_yaml)
            except Exception as e:  # noqa: BLE001
                logger.warning("failed to load deployment.yaml: %s, using defaults", e)
        merged = _resolve_env(merged)
        return cls(raw=merged, deployment_yaml_path=deployment_yaml)

    # ---------- 便捷属性 ----------
    @property
    def mode(self) -> str:
        return self.raw.get("mode", "standalone")

    @property
    def env(self) -> str:
        """部署环境（DDW_ENV）：production / development / demo / test。"""
        return os.environ.get("DDW_ENV", "development")

    @property
    def server(self) -> Dict[str, Any]:
        return self.raw.get("server", {})

    @property
    def databases(self) -> Dict[str, Any]:
        return self.raw.get("databases", {})

    def db_configs(self) -> Dict[str, DatabaseInstanceConfig]:
        """各数据库实例的 typed 配置（factory 等消费方用）。"""
        raw = self.raw.get("databases", {}) or {}
        return {
            name: DatabaseInstanceConfig.from_raw(cfg)
            for name, cfg in raw.items()
        }

    @property
    def main_db_url(self) -> str:
        cfg = self.databases.get("main", {})
        if cfg.get("engine") == "sqlite":
            path = cfg.get("path", "./data/ddw_main.db")
            return f"sqlite+aiosqlite:///{path}"
        # postgresql
        return cfg.get("url", "postgresql+asyncpg://localhost/ddw")

    @property
    def llm(self) -> Dict[str, Any]:
        return self.raw.get("llm_gateway", {})

    @property
    def access_token(self) -> str:
        """静态访问 Token（P0-1 门禁）。"""
        v = self.raw.get("auth", {}).get("access_token", "")
        return v if isinstance(v, str) and v.strip() else ""

    @property
    def plugin_root(self) -> Path:
        p = self.raw.get("plugins", {}).get("root_dir", "./plugins")
        return Path(p).resolve()


def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """in-place 深合并 b → a。"""
    for k, v in b.items():
        if k in a and isinstance(a[k], dict) and isinstance(v, dict):
            _deep_merge(a[k], v)
        else:
            a[k] = v
    return a


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """全局单例 Settings。"""
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings


def reload_settings() -> Settings:
    """重载（测试用）。"""
    global _settings
    _settings = Settings.load()
    return _settings


def get_deployment() -> "DeploymentProxy":
    """返回一个带 llm 属性的对象，供 llm_gateway 模块使用。"""
    return DeploymentProxy(get_settings())


@dataclass
class DatabaseInstanceConfig:
    """数据库实例配置（typed；消除 core/database/factory.py ImportError）。

    ``from_raw`` 从 deployment.yaml 的 databases.<name> dict 构造。
    """

    engine: str = "sqlite"
    path: str = "./data/ddw_main.db"
    url: str = ""
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False

    @classmethod
    def from_raw(cls, raw: Optional[Dict[str, Any]]) -> "DatabaseInstanceConfig":
        raw = raw or {}
        return cls(
            engine=str(raw.get("engine", "sqlite")),
            path=str(raw.get("path", "./data/ddw_main.db")),
            url=str(raw.get("url", "")),
            pool_size=int(raw.get("pool_size", 5)),
            max_overflow=int(raw.get("max_overflow", 10)),
            echo=bool(raw.get("echo", False)),
        )


class LLMRouteRule:
    """LLM 路由规则（llm_gateway 依赖）。"""

    def __init__(self, name: str = "", provider: str = "", model: str = "", cost_per_call: float = 0.0, **_: Any) -> None:
        self.name = name
        self.provider = provider
        self.model = model
        self.cost_per_call = cost_per_call


class _LLMProxy:
    """让 llm 配置 dict 可通过属性访问（routing_rules / default_provider / fallback_chain）。"""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self._raw = raw

    @property
    def default_provider(self) -> str:
        return self._raw.get("default_provider", "deepseek")

    @property
    def fallback_chain(self) -> list:
        return self._raw.get("fallback_chain", ["deepseek", "ollama"])

    @property
    def routing_rules(self) -> list:
        rules = self._raw.get("routing_rules", [])
        return [LLMRouteRule(**r) if isinstance(r, dict) else r for r in rules]

    @property
    def providers(self) -> Dict[str, Any]:
        return self._raw.get("providers", {})


class DeploymentProxy:
    """包裹 Settings，让 llm 属性返回可属性访问的代理对象（供 llm_gateway 使用）。"""

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._llm = _LLMProxy(settings.raw.get("llm_gateway", {}))

    @property
    def llm(self) -> _LLMProxy:
        return self._llm

    @property
    def databases(self) -> Dict[str, DatabaseInstanceConfig]:
        return self._settings.db_configs()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._settings, name)


__all__ = [
    "Settings", "get_settings", "reload_settings", "get_deployment",
    "LLMRouteRule", "DatabaseInstanceConfig",
]
