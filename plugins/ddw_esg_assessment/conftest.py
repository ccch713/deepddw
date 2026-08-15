"""Root conftest.py — set up sys.path for ddw-esg-assessment plugin tests.

The plugin directory uses hyphens (ddw-esg-assessment) which Python cannot
import as a package name.  This conftest adds the plugin root to sys.path so
that absolute imports work, and creates a sys.modules alias so that
``from ddw_esg_assessment import register`` resolves correctly.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys

# Ensure the plugin root is on sys.path so 'routes', 'models', etc. resolve
_plugin_root = os.path.dirname(os.path.abspath(__file__))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

# Remove the parent plugins/ directory to avoid importing sibling plugins
_parent = os.path.dirname(_plugin_root)
if _parent in sys.path:
    sys.path.remove(_parent)

# Prevent pytest from collecting __init__.py as a test module.
# The hyphenated directory name breaks relative imports when pytest
# tries to import __init__.py as a standalone file.
collect_ignore = ["__init__.py"]


def _create_alias():
    """Create sys.modules alias: ddw_esg_assessment → ddw-esg-assessment."""
    alias = "ddw_esg_assessment"
    if alias in sys.modules:
        return

    init_path = os.path.join(_plugin_root, "__init__.py")
    spec = importlib.util.spec_from_file_location(
        alias, init_path, submodule_search_locations=[_plugin_root],
    )
    if spec is None or spec.loader is None:
        return

    mod = importlib.util.module_from_spec(spec)
    mod.__path__ = [_plugin_root]
    mod.__package__ = alias
    mod.__file__ = init_path
    sys.modules[alias] = mod

    try:
        spec.loader.exec_module(mod)
    except ImportError:
        pass

    # Pre-register submodules
    for sub in ("models", "scoring", "skip_engine", "benchmark", "routes"):
        sub_path = os.path.join(_plugin_root, f"{sub}.py")
        if os.path.isfile(sub_path):
            fqn = f"{alias}.{sub}"
            if fqn not in sys.modules:
                sub_spec = importlib.util.spec_from_file_location(fqn, sub_path)
                if sub_spec and sub_spec.loader:
                    sub_mod = importlib.util.module_from_spec(sub_spec)
                    sub_mod.__package__ = alias
                    sys.modules[fqn] = sub_mod
                    try:
                        sub_spec.loader.exec_module(sub_mod)
                    except ImportError:
                        pass


_create_alias()
