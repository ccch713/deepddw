"""DDW ESG Assessment Plugin - ESG assessment engine with scoring, skip logic, and benchmarking."""

from fastapi import APIRouter

try:
    from .routes import router
except ImportError:
    from routes import router  # type: ignore[no-redef]

__all__ = ["register", "router"]

# Sub-router mounted under the plugin prefix
plugin_router = APIRouter(prefix="/api/v1/plugins/ddw-esg-assessment", tags=["ddw-esg-assessment"])
plugin_router.include_router(router)


TOOL_ANNOTATIONS: dict[str, dict] = {
    "run_assessment": {'readOnly': False},
    "get_results": {'readOnly': True},
    "list_benchmarks": {'readOnly': True},
}

def register(app):
    """Register this plugin's routes with the FastAPI application."""
    app.include_router(plugin_router)
