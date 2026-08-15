"""DDW 企业微信 OAuth 免登集成插件 — OAuth免登 + JIT建号 + 部门同步 + 消息通道。"""

import sys as _sys
from pathlib import Path as _P

_plug_dir = str(_P(__file__).parent)
if _plug_dir not in _sys.path:
    _sys.path.insert(0, _plug_dir)

PLUGIN_NAME = "ddw-wecom"
VERSION = "1.0.0"

TOOL_ANNOTATIONS: dict[str, dict] = {
    "health": {"readOnly": True},
    "oauth_authorize": {"readOnly": True},
    "oauth_callback": {"readOnly": False},
    "sync_departments": {"readOnly": False},
    "list_departments": {"readOnly": True},
    "list_users": {"readOnly": True},
    "get_user": {"readOnly": True},
    "bind_identity": {"readOnly": False},
    "send_message": {"readOnly": False},
    "list_messages": {"readOnly": True},
}

__all__ = ["PLUGIN_NAME", "VERSION", "TOOL_ANNOTATIONS"]
