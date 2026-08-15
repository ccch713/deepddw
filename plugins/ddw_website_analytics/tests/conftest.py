"""Test fixtures for ddw_website_analytics."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 让 ``ddw_website_analytics`` 可被 import（直接 import，不需要 plugins. 前缀）。
_PLUGINS_DIR = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGINS_DIR not in sys.path:
    sys.path.insert(0, _PLUGINS_DIR)
