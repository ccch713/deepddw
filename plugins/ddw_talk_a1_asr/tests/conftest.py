"""Test fixtures for ddw_talk_a1_asr plugin.

将 plugins 父目录加入 sys.path，使 ``ddw_talk_a1_asr`` 作为包被加载，
内部子模块的相对导入（``from . import config`` 等）能正常工作。
"""
from __future__ import annotations

import os
import sys

# ddw_talk_a1_asr 父目录 = plugins/
_PLUGINS_PARENT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PLUGINS_PARENT not in sys.path:
    sys.path.insert(0, _PLUGINS_PARENT)
