"""DDW 界面主题系统插件"""
VERSION = "0.1.0"
PLUGIN_NAME = "ddw-theme"

TOOL_ANNOTATIONS: dict[str, dict] = {
    "list_themes": {"readOnly": True},
    "create_theme": {"readOnly": False},
    "get_theme": {"readOnly": True},
    "update_theme": {"readOnly": False},
    "delete_theme": {"readOnly": False},
    "list_presets": {"readOnly": True},
    "switch_theme": {"readOnly": False},
    "get_css": {"readOnly": True},
    "export_theme": {"readOnly": True},
    "import_theme": {"readOnly": False},
}

__all__ = ["VERSION", "PLUGIN_NAME", "TOOL_ANNOTATIONS"]
