"""Root conftest.py — set up sys.path for ddw-esg-question-bank plugin tests.

The plugin directory uses hyphens (ddw-esg-question-bank) which Python cannot
import as a package name.  This conftest adds the plugin root to sys.path so
that absolute imports (``from loader import ...``) work, and creates a
sys.modules alias so that ``from plugins.ddw_esg_question_bank import register``
resolves correctly.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys

# Ensure the plugin root is on sys.path so 'loader', 'models', 'scoring' resolve
_plugin_root = os.path.dirname(os.path.abspath(__file__))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

# Remove the parent plugins/ directory to avoid importing sibling plugins
_parent = os.path.dirname(_plugin_root)
if _parent in sys.path:
    sys.path.remove(_parent)


def _create_alias():
    """Create sys.modules alias: ddw_esg_question_bank → ddw-esg-question-bank."""
    alias = "ddw_esg_question_bank"
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

    # Also register under the dotted path so
    # ``from plugins.ddw_esg_question_bank import ...`` works
    if "plugins" not in sys.modules:
        plugins_pkg = type(sys)("plugins")
        plugins_pkg.__path__ = [_parent]
        plugins_pkg.__package__ = "plugins"
        sys.modules["plugins"] = plugins_pkg
    sys.modules[f"plugins.{alias}"] = mod


_create_alias()
