"""DDW ESG Knowledge Base Plugin - Document management, search, and RAG."""

try:
    from .routes import router
except ImportError:
    from routes import router  # type: ignore[no-redef]

__all__ = ["router", "register"]


TOOL_ANNOTATIONS: dict[str, dict] = {
    "search_knowledge": {'readOnly': True},
    "import_document": {'readOnly': False},
    "rag_query": {'readOnly': True},
}

def register(app) -> None:
    """Register the plugin router with the FastAPI app."""
    app.include_router(router)
