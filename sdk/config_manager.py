"""Plugin config manager (PRD §18.8).

Reads the ``config:`` section of ``manifest.yaml`` and merges it
with overrides from the database (``installed_plugins.config``
JSON column, updated through the admin API).
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ConfigManager:
    """Read-only view over a plugin's effective config."""

    def __init__(self, plugin_name: str, defaults: Optional[Dict[str, Any]] = None) -> None:
        self.plugin_name = plugin_name
        self._defaults = dict(defaults or {})
        self._overrides: Dict[str, Any] = {}

    def update(self, overrides: Dict[str, Any]) -> None:
        self._overrides.update(overrides)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        if key in self._defaults:
            return self._defaults[key]
        return default

    def as_dict(self) -> Dict[str, Any]:
        merged = copy.deepcopy(self._defaults)
        merged.update(self._overrides)
        return merged
