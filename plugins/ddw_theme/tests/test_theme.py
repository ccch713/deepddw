"""ddw-theme 插件测试"""
from __future__ import annotations

import pytest

from plugins.ddw_theme import PLUGIN_NAME, VERSION
from plugins.ddw_theme.models import (
    ExportFormat,
    Scope,
    Theme,
    ThemeSwitchRequest,
)
from plugins.ddw_theme.service import ThemeService


@pytest.fixture
def svc() -> ThemeService:
    return ThemeService()


# ------------------------------------------------------------------
# 1. 元数据
# ------------------------------------------------------------------

def test_plugin_metadata():
    assert PLUGIN_NAME == "ddw-theme"
    assert VERSION == "0.1.0"


# ------------------------------------------------------------------
# 2. 预设管理
# ------------------------------------------------------------------

def test_presets_loaded(svc: ThemeService):
    presets = svc.list_presets()
    ids = {p.preset_id for p in presets}
    assert {"weaver-e9", "native", "dark"} <= ids


def test_default_preset_is_weaver(svc: ThemeService):
    default = [p for p in svc.list_presets() if p.is_default]
    assert len(default) == 1
    assert default[0].preset_id == "weaver-e9"


# ------------------------------------------------------------------
# 3. 主题 CRUD
# ------------------------------------------------------------------

def test_list_themes_has_builtins(svc: ThemeService):
    ids = {t.theme_id for t in svc.list_themes()}
    assert {"weaver-e9", "native", "dark"} <= ids


def test_create_and_get_theme(svc: ThemeService):
    t = Theme(theme_id="custom-1", name="Custom", description="test")
    svc.create_theme(t)
    fetched = svc.get_theme("custom-1")
    assert fetched is not None
    assert fetched.name == "Custom"


def test_create_duplicate_raises(svc: ThemeService):
    t = Theme(theme_id="native", name="Dup")
    with pytest.raises(ValueError, match="already exists"):
        svc.create_theme(t)


def test_update_theme(svc: ThemeService):
    svc.update_theme("native", {"name": "Updated Native"})
    assert svc.get_theme("native").name == "Updated Native"


def test_update_nonexistent_raises(svc: ThemeService):
    with pytest.raises(KeyError, match="not found"):
        svc.update_theme("no-such-id", {"name": "x"})


def test_delete_theme(svc: ThemeService):
    svc.create_theme(Theme(theme_id="tmp", name="Tmp"))
    svc.delete_theme("tmp")
    assert svc.get_theme("tmp") is None


def test_delete_nonexistent_raises(svc: ThemeService):
    with pytest.raises(KeyError, match="not found"):
        svc.delete_theme("no-such-id")


# ------------------------------------------------------------------
# 4. 一键切换
# ------------------------------------------------------------------

def test_switch_user_scope(svc: ThemeService):
    req = ThemeSwitchRequest(target_theme_id="dark", scope=Scope.USER, user_id="u1")
    result = svc.switch_theme(req)
    assert result["theme_id"] == "dark"
    assert svc.get_preference(Scope.USER, "u1") == "dark"


def test_switch_global_scope(svc: ThemeService):
    req = ThemeSwitchRequest(target_theme_id="weaver-e9", scope=Scope.GLOBAL)
    svc.switch_theme(req)
    assert svc.get_preference(Scope.GLOBAL, "__global__") == "weaver-e9"


def test_switch_department_scope(svc: ThemeService):
    req = ThemeSwitchRequest(
        target_theme_id="native", scope=Scope.DEPARTMENT, department_id="d1"
    )
    svc.switch_theme(req)
    assert svc.get_preference(Scope.DEPARTMENT, "d1") == "native"


def test_switch_department_missing_id_raises(svc: ThemeService):
    req = ThemeSwitchRequest(target_theme_id="dark", scope=Scope.DEPARTMENT)
    with pytest.raises(ValueError, match="department_id required"):
        svc.switch_theme(req)


def test_switch_nonexistent_theme_raises(svc: ThemeService):
    req = ThemeSwitchRequest(target_theme_id="ghost", scope=Scope.USER)
    with pytest.raises(KeyError, match="not found"):
        svc.switch_theme(req)


# ------------------------------------------------------------------
# 5. CSS 变量生成
# ------------------------------------------------------------------

def test_generate_css_variables(svc: ThemeService):
    theme = svc.get_theme("weaver-e9")
    css = svc.generate_css_variables(theme)
    assert css.startswith(":root {")
    assert "--primary-color: #2b579a;" in css
    assert css.strip().endswith("}")


def test_generate_css_variables_dark(svc: ThemeService):
    theme = svc.get_theme("dark")
    css = svc.generate_css_variables(theme)
    assert "--bg-base: #141414;" in css


# ------------------------------------------------------------------
# 6. 主题导出
# ------------------------------------------------------------------

def test_export_json(svc: ThemeService):
    result = svc.export_theme("weaver-e9", ExportFormat.JSON)
    assert result["format"] == "json"
    assert result["content"]["theme_id"] == "weaver-e9"
    assert "--primary-color" in result["content"]["css_variables"]


def test_export_json_no_custom(svc: ThemeService):
    result = svc.export_theme("weaver-e9", ExportFormat.JSON, include_custom=False)
    assert result["content"]["css_variables"] == {}


def test_export_css(svc: ThemeService):
    result = svc.export_theme("native", ExportFormat.CSS)
    assert result["format"] == "css"
    assert ":root {" in result["content"]


def test_export_nonexistent_raises(svc: ThemeService):
    with pytest.raises(KeyError, match="not found"):
        svc.export_theme("ghost", ExportFormat.JSON)


# ------------------------------------------------------------------
# 7. 主题导入
# ------------------------------------------------------------------

def test_import_theme(svc: ThemeService):
    data = {
        "theme_id": "imported",
        "name": "Imported Theme",
        "description": "from outside",
        "css_variables": {"--primary-color": "#ff0000"},
    }
    theme = svc.import_theme(data)
    assert theme.theme_id == "imported"
    assert svc.get_theme("imported").css_variables["--primary-color"] == "#ff0000"
