"""DDW ESG Payment Plugin — order management, promotions, and payment gateway."""
from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/plugins/ddw-esg-payment", tags=["ddw-esg-payment"])


def _load_submodules() -> None:
    """Load sibling modules via importlib to avoid relative import issues."""
    import sys

    base = "ddw_esg_payment"
    # Register this package under its bare name so `from ddw_esg_payment.x import ...` works
    if base not in sys.modules:
        sys.modules[base] = sys.modules[__name__]

    # Ensure plugin dir is on sys.path (for direct `import routes` fallback)
    _dir = Path(__file__).resolve().parent
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

    for name in ("models", "promo", "payment_gateway", "routes"):
        full = f"{base}.{name}"
        if full not in sys.modules:
            from importlib import util as _util

            spec = _util.spec_from_file_location(full, _dir / f"{name}.py")
            if spec and spec.loader:
                mod = _util.module_from_spec(spec)
                sys.modules[full] = mod
                spec.loader.exec_module(mod)


_load_submodules()

# Now import routes and register handlers
from ddw_esg_payment.routes import register_routes  # noqa: E402

register_routes(router)


TOOL_ANNOTATIONS: dict[str, dict] = {
    "create_order": {'readOnly': False},
    "query_order": {'readOnly': True},
    "apply_promo": {'readOnly': False},
}

def register(app):
    app.include_router(router)
