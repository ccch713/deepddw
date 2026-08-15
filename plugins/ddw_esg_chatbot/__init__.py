"""DDW ESG Chatbot Plugin - ESG AI customer service with RAG, conversation management, and human escalation."""

import sys
from pathlib import Path

# Ensure plugin dir is importable (routes.py uses absolute sibling imports)
_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from fastapi import APIRouter

try:
    from .routes import router
except ImportError:
    from routes import router  # type: ignore[no-redef]

__all__ = ["register", "router"]

# Sub-router mounted under the plugin prefix
plugin_router = APIRouter(prefix="/api/v1/plugins/ddw-esg-chatbot", tags=["ddw-esg-chatbot"])
plugin_router.include_router(router)


TOOL_ANNOTATIONS: dict[str, dict] = {
    "chat": {'readOnly': True},
    "escalate": {'readOnly': False},
}

def register(app):
    """Register this plugin's routes with the FastAPI application."""
    app.include_router(plugin_router)
