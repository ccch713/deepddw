"""deepDDW 插件运行时（开源裁剪版）。

核心能力：
- ``PluginRuntime.load_many``：启动批量加载（扫描 plugins/*/manifest.yaml）
- ``PluginRuntime.load_one``：单插件加载（安装即生效 / 热启）
- ``PluginRuntime.unload_entry`` / ``reload_one``：停用入口 / 滚动重挂
- ``PluginRegistry``：已加载插件索引（manifest/instance/router/state/error）
- 审计：每次操作写 ``data/plugin_runtime_audit.jsonl``（JSONL 追加）+ logger

开源版差异（相对商业仓 6.0）：
- 无 license 授权体系：``resolve_license_gate`` 恒为放行（插件目录只含白名单组件，
  manifest ``license`` 仅作元数据展示，不再作为加载门禁）
- ``status: locked`` 插件在启动与热装两个路径都被拒绝（保留红线语义）
- 平台保留名（``_template`` / ``embedded_llm``）不参与加载
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 平台保留名：不允许热装/热启
SKIP_NAMES = frozenset({"_template", "embedded_llm"})

# 审计文件（JSONL 追加；路径可用 deployment.yaml plugins.audit_path 覆盖）
AUDIT_FILE_DEFAULT = "./data/plugin_runtime_audit.jsonl"


# ---------------------------------------------------------------------------
# 授权门控（开源版恒放行；保留接口供外部调用方兼容）
# ---------------------------------------------------------------------------


def resolve_license_gate(settings: Any) -> Dict[str, Any]:
    """解析当前授权门控（deepDDW 开源版：无授权体系，恒放行）。

    返回与商业版同形：``{production: False, authorized_plugins: None, license_present: False}``，
    语义 = 全部插件可加载（插件目录本身只含白名单组件）。
    """
    return {
        "production": False,
        "authorized_plugins": None,
        "license_present": False,
    }


# ---------------------------------------------------------------------------
# manifest 读取与红线判定
# ---------------------------------------------------------------------------


def _load_manifest(manifest_path: Path) -> Optional[Dict[str, Any]]:
    import yaml

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "plugin %s: manifest unreadable: %s", manifest_path.parent.name, e
        )
        return None


def _is_locked(manifest: Dict[str, Any]) -> bool:
    return str(manifest.get("status", "") or "").strip().lower() == "locked"


def _check_authorized(
    plugin_name: str,
    manifest: Dict[str, Any],
    authorized_plugins: Optional[List[str]],
    production: bool,
) -> tuple:
    """授权过滤（与启动路径同源）：free 恒加载；commercial 需在授权清单。"""
    tier = str(manifest.get("license", "free") or "free").strip().lower()
    if tier != "commercial":
        return True, ""
    if authorized_plugins is None or "*" in authorized_plugins:
        return True, ""
    normalized_name = plugin_name.replace("_", "-")
    normalized_auth = {p.replace("_", "-") for p in authorized_plugins}
    if normalized_name in normalized_auth:
        return True, ""
    reason = (
        "not licensed (license: commercial)"
        if production
        else "not in license entitlements"
    )
    return False, reason


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------


class PluginRegistry:
    """已加载插件索引。"""

    def __init__(self) -> None:
        self._plugins: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, record: Dict[str, Any]) -> None:
        self._plugins[name] = record

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self._plugins.get(name)

    def set_state(self, name: str, state: str, error: Optional[str] = None) -> None:
        rec = self._plugins.get(name)
        if rec is not None:
            rec["state"] = state
            if error is not None:
                rec["error"] = error

    def snapshot(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "state": rec.get("state"),
                "version": (rec.get("manifest") or {}).get("version"),
                "license": (rec.get("manifest") or {}).get("license"),
                "loaded_at": rec.get("loaded_at"),
                "error": rec.get("error"),
                "pending_restart": bool(rec.get("pending_restart")),
            }
            for name, rec in sorted(self._plugins.items())
        ]


# ---------------------------------------------------------------------------
# 运行时
# ---------------------------------------------------------------------------


class PluginRuntime:
    """插件运行时：单插件加载 / 停用 / 重挂 + 审计。"""

    def __init__(
        self,
        app: Any = None,
        plugin_root: Optional[str | Path] = None,
        audit_path: Optional[str | Path] = None,
        settings: Any = None,
    ) -> None:
        self.app = app
        self.plugin_root = Path(plugin_root) if plugin_root else None
        self.settings = settings  # 注入的 settings（与加载方同源）
        self.audit_path = Path(audit_path) if audit_path else Path(AUDIT_FILE_DEFAULT)
        self.registry = PluginRegistry()
        # 授权门控缓存：启动时由 load_many 设置；热装时每次重算（保证最新）
        self._gate: Dict[str, Any] = {
            "production": False,
            "authorized_plugins": None,
            "license_present": False,
        }

    # ---- 审计 ----

    def _audit(
        self,
        action: str,
        plugin: str,
        operator: str,
        ok: bool,
        detail: str = "",
    ) -> None:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "action": action,
            "plugin": plugin,
            "operator": operator,
            "ok": ok,
            "detail": detail,
        }
        logger.info(
            "plugin runtime %s %s operator=%s ok=%s %s",
            action, plugin, operator, ok, detail,
        )
        try:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("plugin audit write failed: %s", e)

    # ---- 授权门控 ----

    def _refresh_gate(self) -> Dict[str, Any]:
        """重算授权门控（热装时保证最新授权状态）。

        settings 来源：构造时注入的（与加载方同源）优先，否则 core.config 单例。
        """
        if self.settings is None:
            from core.config import get_settings

            self.settings = get_settings()
        self._gate = resolve_license_gate(self.settings)
        return self._gate

    # ---- 加载 ----

    def load_one(
        self,
        plugin_name: str,
        *,
        operator: str = "system",
        refresh_gate: bool = True,
    ) -> Optional[Any]:
        """加载单个插件（红线：locked 拒绝、授权过滤同路径、保留名拒绝）。

        Returns:
            插件实例；失败返回 None（registry 记录 error + 审计）。
        """
        if plugin_name in SKIP_NAMES:
            self._audit("load", plugin_name, operator, False, "reserved name")
            return None
        if refresh_gate:
            self._refresh_gate()
        if self.plugin_root is None:
            if self.settings is None:
                from core.config import get_settings

                self.settings = get_settings()
            self.plugin_root = self.settings.plugin_root
        manifest_path = self.plugin_root / plugin_name / "manifest.yaml"
        if not manifest_path.exists():
            self._audit("load", plugin_name, operator, False, "manifest not found")
            return None
        manifest = _load_manifest(manifest_path)
        if manifest is None:
            self._audit("load", plugin_name, operator, False, "manifest unreadable")
            return None
        # 红线③：locked 拒绝
        if _is_locked(manifest):
            logger.warning("skip plugin %s: locked（仅入库不部署）", plugin_name)
            self._audit("load", plugin_name, operator, False, "locked")
            return None
        # 红线②：授权过滤同路径（先授权后加载）
        allowed, reason = _check_authorized(
            plugin_name,
            manifest,
            self._gate.get("authorized_plugins"),
            self._gate.get("production"),
        )
        if not allowed:
            logger.warning("skip plugin %s: %s", plugin_name, reason)
            self._audit("load", plugin_name, operator, False, reason)
            return None

        try:
            mod = importlib.import_module(f"plugins.{plugin_name}.plugin")
            cls = getattr(mod, "Plugin", None)
            if cls is None:
                raise ValueError("no Plugin class in plugin.py")
            instance = cls(
                app=self.app,
                config=manifest.get("config", {}),
                manifest=manifest,
            )
            router: Any = None
            if hasattr(instance, "register"):
                instance.register()
                router = getattr(instance, "router", None) or getattr(
                    instance, "_router", None
                )
            self.registry.register(
                plugin_name,
                {
                    "name": plugin_name,
                    "manifest": manifest,
                    "module": mod,
                    "instance": instance,
                    "router": router,
                    "state": "loaded",
                    "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "error": None,
                    "pending_restart": False,
                },
            )
            logger.info(
                "loaded plugin %s v%s", plugin_name, manifest.get("version", "?")
            )
            self._audit(
                "load", plugin_name, operator, True, f"v{manifest.get('version', '?')}"
            )
            return instance
        except Exception as e:  # noqa: BLE001  # 失败隔离：只影响该插件
            logger.warning("plugin %s load failed: %s", plugin_name, e)
            self.registry.set_state(plugin_name, "error", str(e))
            self._audit("load", plugin_name, operator, False, str(e))
            return None

    def load_many(self) -> Dict[str, Any]:
        """启动批量加载（等价原 load_plugins 循环，行为不变）。"""
        self._refresh_gate()
        loaded: Dict[str, Any] = {}
        if self.plugin_root is None:
            if self.settings is None:
                from core.config import get_settings

                self.settings = get_settings()
            self.plugin_root = self.settings.plugin_root
        if not self.plugin_root.exists():
            logger.warning("plugin root not found: %s", self.plugin_root)
            return loaded
        for manifest_path in sorted(self.plugin_root.glob("*/manifest.yaml")):
            name = manifest_path.parent.name
            if name in SKIP_NAMES:
                # 平台保留名：启动也不加载（与原有逻辑一致），不审计
                continue
            instance = self.load_one(name, refresh_gate=False)
            if instance is not None:
                loaded[name] = instance
        return loaded

    # ---- 停用 / 重挂 / 更新 ----

    def unload_entry(self, plugin_name: str, *, operator: str = "system") -> bool:
        """停用入口（不做路由卸载）：registry 标记 disabled。

        Returns:
            True=已停用；False=插件未在 registry（未加载）。
        """
        rec = self.registry.get(plugin_name)
        if rec is None:
            self._audit("unload", plugin_name, operator, False, "not loaded")
            return False
        self.registry.set_state(plugin_name, "disabled")
        self._audit(
            "unload", plugin_name, operator, True,
            "entry disabled (router kept; restart to fully remove)",
        )
        return True

    def reload_one(self, plugin_name: str, *, operator: str = "system") -> bool:
        """滚动重挂：停用入口 → 重新加载（更新策略）。

        模块级单例插件（如 ddw_memory）热替换不彻底：若该插件此前已加载
        （模块已在 sys.modules），重载后自动标记 ``pending_restart``，
        管理端据此提示"需重启彻底生效"（诚实边界）。
        """
        had_previous = self.registry.get(plugin_name) is not None
        self.unload_entry(plugin_name, operator=operator)
        instance = self.load_one(plugin_name, operator=operator)
        if instance is not None and had_previous:
            self.mark_pending_restart(plugin_name)
        return instance is not None

    def mark_pending_restart(self, plugin_name: str) -> None:
        """标记插件更新需重启彻底生效（模块级单例场景）。"""
        rec = self.registry.get(plugin_name)
        if rec is not None:
            rec["pending_restart"] = True
            logger.warning(
                "plugin %s marked pending_restart (module-level singleton) "
                "— restart required to fully apply update",
                plugin_name,
            )

    def snapshot(self) -> List[Dict[str, Any]]:
        return self.registry.snapshot()


__all__ = [
    "SKIP_NAMES",
    "AUDIT_FILE_DEFAULT",
    "resolve_license_gate",
    "PluginRegistry",
    "PluginRuntime",
]
