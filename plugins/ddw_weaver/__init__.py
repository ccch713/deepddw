VERSION = "0.1.0"
PLUGIN_NAME = "ddw-weaver"

TOOL_ANNOTATIONS: dict[str, dict] = {
    "import_csv": {"readOnly": False},
    "import_api": {"readOnly": False},
    "list_tasks": {"readOnly": True},
    "list_departments": {"readOnly": True},
    "map_department": {"readOnly": False},
    "list_users": {"readOnly": True},
    "save_portal_config": {"readOnly": False},
    "list_portal_configs": {"readOnly": True},
}

__all__ = ["VERSION", "PLUGIN_NAME", "TOOL_ANNOTATIONS"]
