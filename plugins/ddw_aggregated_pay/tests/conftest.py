import os
import sys

_PLUGINS_PARENT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
if _PLUGINS_PARENT not in sys.path:
    sys.path.insert(0, _PLUGINS_PARENT)
