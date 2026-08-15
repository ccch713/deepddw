"""ddw_memory — 企业四层持久化记忆引擎。

员工级(L2) / 岗位级(L3) / 部门级(L4) / 企业级(L5) 可裁剪记忆，
SOP 模板管理，自动对话捕获，记忆迁移与离职清除。
"""

import sys as _sys
from pathlib import Path as _P

_plug_dir = str(_P(__file__).parent)
if _plug_dir not in _sys.path:
    _sys.path.insert(0, _plug_dir)

PLUGIN_NAME = "ddw-memory"
VERSION = "2.0.0"

TOOL_ANNOTATIONS: dict[str, dict] = {
    "health": {"readOnly": True},
    "create_memory": {"readOnly": False},
    "list_memories": {"readOnly": True},
    "get_memory": {"readOnly": True},
    "update_memory": {"readOnly": False},
    "delete_memory": {"readOnly": False},
    "search_memories": {"readOnly": True},
    "capture_session_summary": {"readOnly": False},
    "list_pending_captures": {"readOnly": True},
    "approve_capture": {"readOnly": False},
    "reject_capture": {"readOnly": False},
    "get_capture_config": {"readOnly": True},
    "update_capture_config": {"readOnly": False},
    "create_sop_template": {"readOnly": False},
    "list_sop_templates": {"readOnly": True},
    "get_sop_template": {"readOnly": True},
    "update_sop_template": {"readOnly": False},
    "query_position_knowledge": {"readOnly": True},
    "migrate_memories": {"readOnly": False},
    "cleanup_soft_delete": {"readOnly": False},
    "cleanup_physical_delete": {"readOnly": False},
    "get_layer_config": {"readOnly": True},
    "set_layer_config": {"readOnly": False},
    "get_stats": {"readOnly": True},
}

__all__ = ["PLUGIN_NAME", "TOOL_ANNOTATIONS", "VERSION"]
