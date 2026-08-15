VERSION = "0.1.0"
PLUGIN_NAME = "ddw-metric-dict"

TOOL_ANNOTATIONS: dict[str, dict] = {
    "create": {"readOnly": False},
    "list_all": {"readOnly": True},
    "detail": {"readOnly": True},
    "route": {"readOnly": True},
    "adjudicate_endpoint": {"readOnly": True},
}

__all__ = ["VERSION", "PLUGIN_NAME", "TOOL_ANNOTATIONS"]
