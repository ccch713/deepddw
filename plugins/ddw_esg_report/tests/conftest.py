"""conftest.py — handle imports for ddw-esg-report plugin.

The plugin directory uses hyphens (ddw-esg-report) which Python can't
import as a module name directly. This conftest adds the plugin parent
to sys.path and creates a sys.modules alias so that:
    from ddw_esg_report.models import ...
works even though the directory is named ddw-esg-report.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_PARENT = os.path.dirname(PLUGIN_DIR)  # plugins/

# Add plugins/ to sys.path so `ddw_esg_report` can be resolved
if PLUGIN_PARENT not in sys.path:
    sys.path.insert(0, PLUGIN_PARENT)

# Create a fake `ddw_esg_report` module that points to the real package
_real_pkg_path = os.path.join(PLUGIN_DIR, "py.typed")


def _create_alias():
    """Create a sys.modules alias: ddw_esg_report → ddw-esg-report."""
    alias_name = "ddw_esg_report"
    if alias_name in sys.modules:
        return

    # Use importlib to import the hyphenated package from its path
    spec = importlib.util.spec_from_file_location(
        alias_name,
        os.path.join(PLUGIN_DIR, "__init__.py"),
        submodule_search_locations=[PLUGIN_DIR],
    )
    if spec is None or spec.loader is None:
        return

    mod = importlib.util.module_from_spec(spec)
    mod.__path__ = [PLUGIN_DIR]
    mod.__package__ = alias_name
    sys.modules[alias_name] = mod

    try:
        spec.loader.exec_module(mod)
    except ImportError:
        # Some sub-imports may fail; that's OK for test discovery
        sys.modules[alias_name] = mod


_create_alias()
