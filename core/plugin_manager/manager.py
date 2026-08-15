"""Plugin manager (PRD §10).

Responsibilities:

* **Discover** plugins by scanning ``plugins/*/manifest.yaml``
* **Register** them with the platform (route, events, permissions)
* **Track** install state in the ``installed_plugins`` DB table
* **Enable / disable / uninstall** at runtime

The actual loading of plugin code is split out into
:mod:`core.plugin_manager.sandbox` (Phase 2) and the legacy
inline loader used for trusted plugins.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.events.event_bus import Event, get_event_bus
from core.plugin_manager.dependency_resolver import (
    DependencyResolver,
    ResolutionError,
)

logger = logging.getLogger(__name__)

PLUGINS_ROOT = Path(__file__).resolve().parent.parent.parent / "plugins"


@dataclass
class PluginManifest:
    """Parsed manifest.yaml (PRD §10.2)."""

    name: str
    version: str
    engine: str = ">=0.1.0"
    description: str = ""
    dependencies: Dict[str, Any] = field(default_factory=dict)
    permissions: List[str] = field(default_factory=list)
    isolation: str = "inline"  # inline | process
    events_produces: List[str] = field(default_factory=list)
    events_consumes: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    trial: Dict[str, Any] = field(default_factory=dict)
    ecosystem: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, data: Dict[str, Any]) -> "PluginManifest":
        events = data.get("events") or {}
        return cls(
            name=data["name"],
            version=data["version"],
            engine=data.get("engine", ">=0.1.0"),
            description=data.get("description", ""),
            dependencies=data.get("dependencies", {}),
            permissions=list(data.get("permissions", [])),
            isolation=data.get("isolation", "inline"),
            events_produces=list(events.get("produces", [])),
            events_consumes=list(events.get("consumes", [])),
            config=dict(data.get("config", {})),
            trial=dict(data.get("trial", {})),
            ecosystem=dict(data.get("ecosystem", {})),
            raw=data,
        )


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    enabled: bool = True
    module: Optional[Any] = None
    error: Optional[str] = None


class PluginManager:
    """In-process plugin registry."""

    def __init__(self, plugins_root: Optional[Path] = None) -> None:
        self.plugins_root = plugins_root or PLUGINS_ROOT
        self._plugins: Dict[str, LoadedPlugin] = {}
        self._resolver = DependencyResolver()

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def discover(self) -> List[PluginManifest]:
        manifests: List[PluginManifest] = []
        for child in sorted(self.plugins_root.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            manifest_path = child / "manifest.yaml"
            if not manifest_path.exists():
                continue
            try:
                data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
                manifests.append(PluginManifest.from_yaml(data))
            except Exception as exc:  # noqa: BLE001
                logger.warning("failed to load %s: %s", manifest_path, exc)
        return manifests

    # ------------------------------------------------------------------ #
    # Register / load / unload
    # ------------------------------------------------------------------ #

    async def register_all(self) -> Dict[str, str]:
        """Register every discovered plugin (no code load)."""

        results: Dict[str, str] = {}
        for manifest in self.discover():
            try:
                self._resolver.add(manifest.name, manifest.version, manifest.dependencies.get("plugins", {}))
                self._plugins[manifest.name] = LoadedPlugin(manifest=manifest, enabled=True)
                results[manifest.name] = "registered"
            except ResolutionError as exc:
                results[manifest.name] = f"dep_error: {exc}"
        # Verify dependency graph once.
        try:
            self._resolver.resolve()
        except ResolutionError as exc:
            logger.warning("dependency resolution issue: %s", exc)
        return results

    async def load_module(self, name: str) -> LoadedPlugin:
        """Import the plugin's ``__init__`` and keep a reference."""

        plugin = self._plugins.get(name)
        if plugin is None:
            raise KeyError(f"Plugin '{name}' not registered")
        if plugin.module is not None:
            return plugin
        try:
            module = importlib.import_module(f"plugins.{name}")
            plugin.module = module
            await get_event_bus().publish(Event(topic="plugin.loaded", payload={"name": name}))
        except Exception as exc:  # noqa: BLE001
            plugin.error = str(exc)
            logger.exception("failed to load plugin %s: %s", name, exc)
            raise
        return plugin

    async def enable(self, name: str) -> None:
        plugin = self._plugins.get(name)
        if plugin is None:
            raise KeyError(f"Plugin '{name}' not registered")
        plugin.enabled = True
        await get_event_bus().publish(Event(topic="plugin.enabled", payload={"name": name}))

    async def disable(self, name: str) -> None:
        plugin = self._plugins.get(name)
        if plugin is None:
            raise KeyError(f"Plugin '{name}' not registered")
        plugin.enabled = False
        await get_event_bus().publish(Event(topic="plugin.disabled", payload={"name": name}))

    async def uninstall(self, name: str) -> None:
        if name not in self._plugins:
            return
        del self._plugins[name]
        await get_event_bus().publish(Event(topic="plugin.uninstalled", payload={"name": name}))

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    def list(self) -> List[PluginManifest]:
        return [p.manifest for p in self._plugins.values()]

    def get(self, name: str) -> Optional[LoadedPlugin]:
        return self._plugins.get(name)

    def is_enabled(self, name: str) -> bool:
        p = self._plugins.get(name)
        return p is not None and p.enabled


# --------------------------------------------------------------------------- #
# Singleton
# --------------------------------------------------------------------------- #


_pm: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    global _pm
    if _pm is None:
        _pm = PluginManager()
    return _pm
