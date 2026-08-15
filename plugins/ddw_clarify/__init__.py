"""DDW 对话反问澄清层 plugin."""

import sys as _sys
from pathlib import Path as _P

_plug_dir = str(_P(__file__).parent)
if _plug_dir not in _sys.path:
    _sys.path.insert(0, _plug_dir)

PLUGIN_NAME = "ddw-clarify"
VERSION = "1.0.0"

TOOL_ANNOTATIONS: dict[str, dict] = {
    "detect": {"readOnly": False},
    "respond": {"readOnly": False},
    "list_rules": {"readOnly": True},
    "health": {"readOnly": True},
}

__all__ = ["PLUGIN_NAME", "VERSION", "TOOL_ANNOTATIONS"]
