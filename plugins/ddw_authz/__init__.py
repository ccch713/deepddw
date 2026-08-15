"""DDW 权限审计插件 — 用户/部门/角色 RBAC 权限管理 + 操作审计日志。"""

import sys as _sys
from pathlib import Path as _P

_plug_dir = str(_P(__file__).parent)
if _plug_dir not in _sys.path:
    _sys.path.insert(0, _plug_dir)

PLUGIN_NAME = "ddw-authz"
VERSION = "1.0.0"

TOOL_ANNOTATIONS: dict[str, dict] = {
    "health": {"readOnly": True},
    "create_user": {"readOnly": False},
    "list_users": {"readOnly": True},
    "get_user": {"readOnly": True},
    "update_user": {"readOnly": False},
    "delete_user": {"readOnly": False},
    "create_department": {"readOnly": False},
    "list_departments": {"readOnly": True},
    "department_tree": {"readOnly": True},
    "create_role": {"readOnly": False},
    "list_roles": {"readOnly": True},
    "check_permission": {"readOnly": False},
    "get_audit_logs": {"readOnly": True},
}

__all__ = ["PLUGIN_NAME", "VERSION", "TOOL_ANNOTATIONS"]
