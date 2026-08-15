"""conftest.py — isolate tests from parent plugins package.

The ddw-esg-chatbot directory name contains hyphens, so it cannot be a
normal Python package.  We add the plugin root to sys.path so that
module-level imports (models, routes, etc.) resolve directly.

We also prevent pytest from walking up into the parent ``plugins/``
directory whose ``__init__.py`` tries to import every plugin — many of
which use Python 3.10+ ``str | None`` syntax that breaks on 3.9.
"""

import os
import sys

# Ensure the plugin root is importable
_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

# Prevent parent package import by blocking the plugins/ __init__.py
_plugins_dir = os.path.dirname(_plugin_root)
if _plugins_dir in sys.path:
    sys.path.remove(_plugins_dir)
