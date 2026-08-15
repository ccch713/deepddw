"""Conftest: prevent pytest from importing the hyphenated parent package."""
import sys
from pathlib import Path

# The plugin directory name has hyphens, so Python can't import it as a package.
# We pre-load modules via importlib.util so pytest never tries a normal import.
_PLUGIN_DIR = Path(__file__).resolve().parent.parent  # ddw-esg-payment/

def _load_module(name: str, file_path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# Pre-register modules so relative imports in __init__.py don't break
_load_module("ddw_esg_payment.models", _PLUGIN_DIR / "models.py")
_load_module("ddw_esg_payment.promo", _PLUGIN_DIR / "promo.py")
_load_module("ddw_esg_payment.payment_gateway", _PLUGIN_DIR / "payment_gateway.py")
_load_module("ddw_esg_payment.routes", _PLUGIN_DIR / "routes.py")
_load_module("ddw_esg_payment", _PLUGIN_DIR / "__init__.py")
