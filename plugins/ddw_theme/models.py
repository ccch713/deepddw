"""DDW 主题系统 Pydantic 模型"""
from __future__ import annotations

from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field


class Scope(str, Enum):
    GLOBAL = "global"
    DEPARTMENT = "department"
    USER = "user"


class ExportFormat(str, Enum):
    JSON = "json"
    CSS = "css"


class ColorScheme(BaseModel):
    primary: str = "#1890ff"
    success: str = "#52c41a"
    warning: str = "#faad14"
    error: str = "#f5222d"
    info: str = "#1890ff"
    bg_base: str = "#f0f2f5"
    bg_container: str = "#ffffff"
    bg_elevated: str = "#ffffff"
    text_primary: str = "#262626"
    text_secondary: str = "#8c8c8c"
    text_disabled: str = "#bfbfbf"
    border_base: str = "#d9d9d9"


class Theme(BaseModel):
    theme_id: str
    name: str
    description: str = ""
    css_variables: Dict[str, str] = Field(default_factory=dict)
    icon_set: str = "default"
    color_scheme: ColorScheme = Field(default_factory=ColorScheme)


class ThemePreset(BaseModel):
    preset_id: str
    theme_name: str  # weaver-e9 / native / dark
    is_default: bool = False
    css_file: str = ""


class ThemeSwitchRequest(BaseModel):
    target_theme_id: str
    scope: Scope = Scope.USER
    department_id: Optional[str] = None
    user_id: Optional[str] = None


class ThemeExport(BaseModel):
    format: ExportFormat = ExportFormat.JSON
    include_custom_vars: bool = True


__all__ = [
    "Scope",
    "ExportFormat",
    "ColorScheme",
    "Theme",
    "ThemePreset",
    "ThemeSwitchRequest",
    "ThemeExport",
]
