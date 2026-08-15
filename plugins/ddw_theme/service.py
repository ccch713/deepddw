"""DDW 主题系统核心服务"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugins.ddw_theme.models import (
    ColorScheme,
    ExportFormat,
    Scope,
    Theme,
    ThemePreset,
    ThemeSwitchRequest,
)

logger = logging.getLogger(__name__)

_PRESETS_DIR = Path(__file__).resolve().parent / "presets"

# ---------------------------------------------------------------------------
# Built-in presets
# ---------------------------------------------------------------------------

_NATIVE_PRESET = ThemePreset(
    preset_id="native",
    theme_name="原生风格",
    is_default=False,
    css_file="",
)

_DARK_PRESET = ThemePreset(
    preset_id="dark",
    theme_name="暗色风格",
    is_default=False,
    css_file="",
)

_NATIVE_THEME = Theme(
    theme_id="native",
    name="原生风格",
    description="DDW 平台默认原生主题",
    icon_set="default",
    color_scheme=ColorScheme(),
    css_variables={
        "--primary-color": "#1890ff",
        "--success-color": "#52c41a",
        "--warning-color": "#faad14",
        "--error-color": "#f5222d",
        "--bg-base": "#f0f2f5",
        "--bg-container": "#ffffff",
        "--text-primary": "#262626",
        "--text-secondary": "#8c8c8c",
        "--border-base": "#d9d9d9",
        "--border-radius-base": "4px",
        "--font-size-base": "14px",
    },
)

_DARK_THEME = Theme(
    theme_id="dark",
    name="暗色风格",
    description="深色护眼主题",
    icon_set="default",
    color_scheme=ColorScheme(
        primary="#177ddc",
        success="#49aa19",
        warning="#d89614",
        error="#a61d24",
        info="#177ddc",
        bg_base="#141414",
        bg_container="#1f1f1f",
        bg_elevated="#262626",
        text_primary="#ffffffd9",
        text_secondary="#ffffff73",
        text_disabled="#ffffff40",
        border_base="#434343",
    ),
    css_variables={
        "--primary-color": "#177ddc",
        "--success-color": "#49aa19",
        "--warning-color": "#d89614",
        "--error-color": "#a61d24",
        "--bg-base": "#141414",
        "--bg-container": "#1f1f1f",
        "--bg-elevated": "#262626",
        "--text-primary": "#ffffffd9",
        "--text-secondary": "#ffffff73",
        "--text-disabled": "#ffffff40",
        "--border-base": "#434343",
        "--border-radius-base": "4px",
        "--font-size-base": "14px",
    },
)


def _load_weaver_e9_theme() -> Theme:
    """Load weaver-e9 theme from the bundled JSON preset."""
    preset_path = _PRESETS_DIR / "weaver-e9.json"
    with open(preset_path, encoding="utf-8") as f:
        data = json.load(f)
    t = data["theme"]
    return Theme(
        theme_id=t["theme_id"],
        name=t["name"],
        description=t.get("description", ""),
        icon_set=t.get("icon_set", "weaver"),
        color_scheme=ColorScheme(**t.get("color_scheme", {})),
        css_variables=t.get("css_variables", {}),
    )


class ThemeService:
    """主题 CRUD + 预设管理 + 切换 + CSS 变量注入 + 导出/导入"""

    def __init__(self) -> None:
        # In-memory theme store: theme_id -> Theme
        self._themes: Dict[str, Theme] = {}
        # In-memory switch preferences: (scope, entity_id) -> theme_id
        self._preferences: Dict[tuple, str] = {}
        # Built-in presets
        self._presets: Dict[str, ThemePreset] = {}

        self._init_presets()

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def _init_presets(self) -> None:
        weaver_theme = _load_weaver_e9_theme()
        self._themes[weaver_theme.theme_id] = weaver_theme
        self._themes[_NATIVE_THEME.theme_id] = _NATIVE_THEME
        self._themes[_DARK_THEME.theme_id] = _DARK_THEME

        weaver_preset = ThemePreset(
            preset_id="weaver-e9",
            theme_name="泛微E9风格",
            is_default=True,
            css_file=str(_PRESETS_DIR / "weaver-e9.json"),
        )
        self._presets = {
            "weaver-e9": weaver_preset,
            "native": _NATIVE_PRESET,
            "dark": _DARK_PRESET,
        }

    # ------------------------------------------------------------------
    # Theme CRUD
    # ------------------------------------------------------------------

    def list_themes(self) -> List[Theme]:
        return list(self._themes.values())

    def get_theme(self, theme_id: str) -> Optional[Theme]:
        return self._themes.get(theme_id)

    def create_theme(self, theme: Theme) -> Theme:
        if theme.theme_id in self._themes:
            raise ValueError(f"Theme '{theme.theme_id}' already exists")
        self._themes[theme.theme_id] = theme
        return theme

    def update_theme(self, theme_id: str, updates: Dict[str, Any]) -> Theme:
        theme = self._themes.get(theme_id)
        if theme is None:
            raise KeyError(f"Theme '{theme_id}' not found")
        data = theme.model_dump()
        data.update(updates)
        updated = Theme(**data)
        self._themes[theme_id] = updated
        return updated

    def delete_theme(self, theme_id: str) -> bool:
        if theme_id not in self._themes:
            raise KeyError(f"Theme '{theme_id}' not found")
        del self._themes[theme_id]
        return True

    # ------------------------------------------------------------------
    # Preset management
    # ------------------------------------------------------------------

    def list_presets(self) -> List[ThemePreset]:
        return list(self._presets.values())

    def get_preset(self, preset_id: str) -> Optional[ThemePreset]:
        return self._presets.get(preset_id)

    # ------------------------------------------------------------------
    # One-click switch
    # ------------------------------------------------------------------

    def switch_theme(self, req: ThemeSwitchRequest) -> Dict[str, Any]:
        if req.target_theme_id not in self._themes:
            raise KeyError(f"Theme '{req.target_theme_id}' not found")

        if req.scope == Scope.GLOBAL:
            key = ("global", "__global__")
        elif req.scope == Scope.DEPARTMENT:
            if not req.department_id:
                raise ValueError("department_id required for department scope")
            key = ("department", req.department_id)
        else:
            uid = req.user_id or "current"
            key = ("user", uid)

        self._preferences[key] = req.target_theme_id
        return {
            "scope": req.scope.value,
            "theme_id": req.target_theme_id,
            "key": key,
        }

    def get_preference(self, scope: Scope, entity_id: str = "__global__") -> Optional[str]:
        return self._preferences.get((scope.value, entity_id))

    # ------------------------------------------------------------------
    # CSS variable injection
    # ------------------------------------------------------------------

    @staticmethod
    def generate_css_variables(theme: Theme) -> str:
        """Generate a `:root { --var: value; ... }` CSS block."""
        lines = [":root {"]
        for key, value in theme.css_variables.items():
            lines.append(f"  {key}: {value};")
        lines.append("}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def export_theme(self, theme_id: str, fmt: ExportFormat, include_custom: bool = True) -> Dict[str, Any]:
        theme = self._themes.get(theme_id)
        if theme is None:
            raise KeyError(f"Theme '{theme_id}' not found")

        if fmt == ExportFormat.CSS:
            return {"format": "css", "content": self.generate_css_variables(theme)}

        data = theme.model_dump()
        if not include_custom:
            data["css_variables"] = {}
        return {"format": "json", "content": data}

    def import_theme(self, data: Dict[str, Any]) -> Theme:
        theme = Theme(**data)
        self._themes[theme.theme_id] = theme
        return theme


__all__ = ["ThemeService"]
