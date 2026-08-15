"""pytest fixtures for ddw_clinic_cs / ddw_online_cs tests.

Adds the plugins/ parent dir to sys.path so `from ddw_clinic_cs import router`
works.  NOTE: no `__init__.py` trick / no `import conftest` — pytest loads
this file automatically, avoiding the tests.conftest module collision seen
in legacy hyphenated plugins.
"""
from __future__ import annotations

import os
import sys

_PLUGINS_PARENT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PLUGINS_PARENT not in sys.path:
    sys.path.insert(0, _PLUGINS_PARENT)
