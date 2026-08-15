"""DDW 企业知识库引擎（Flat KB MVP）。"""

PLUGIN_NAME = "ddw_ent_knowledge"
VERSION = "1.0.0"

TOOL_ANNOTATIONS: dict[str, dict] = {
    "upload_document": {"readOnly": False},
    "list_documents": {"readOnly": True},
    "delete_document": {"readOnly": False},
    "search": {"readOnly": True},
    "chat": {"readOnly": True},
    "health": {"readOnly": True},
}

__all__ = ["PLUGIN_NAME", "VERSION", "TOOL_ANNOTATIONS"]
