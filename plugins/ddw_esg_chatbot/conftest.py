"""Root conftest.py — prevent pytest from walking into parent plugins/ package.

This conftest runs at collection time, before individual test files are
imported.  It strips the parent ``plugins/`` directory from sys.path so
that pytest never tries to import ``plugins/__init__.py`` (which would
pull in every sibling plugin, many using Python 3.10+ syntax).
"""

import os
import sys

# Ensure the plugin root is on sys.path so 'models', 'routes', etc. resolve
_plugin_root = os.path.dirname(os.path.abspath(__file__))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

# Remove the parent plugins/ directory to avoid importing sibling plugins
_parent = os.path.dirname(_plugin_root)
if _parent in sys.path:
    sys.path.remove(_parent)
