"""插件独立测试 conftest：把 monorepo 根加入 sys.path，让 ``plugins.xxx`` 可 import。

效果：可在 plugins/<plugin>/tests/ 目录下直接 `pytest` 跑测，不需要从根目录跑。
"""
import sys
from pathlib import Path

# monorepo 根 = plugins/<plugin>/tests/conftest.py 的 4 层父目录
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
