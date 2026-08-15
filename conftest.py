"""Pytest 根 conftest：把项目根加入 sys.path，让 ``plugins.xxx`` 可 import。"""
import os
import sys

# 项目根 = conftest.py 所在目录
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 测试环境默认使用独立访问 Token（P0-1 门禁）
os.environ.setdefault("DDW_ACCESS_TOKEN", "test-token-deepddw")

# 测试默认关闭局域网免密（DDW_LAN_BYPASS=0）：
# 保持"无 Token → 401"的安全语义测试有效（LAN 免密是运行时行为，
# 由专门的 test_lan_bypass 用例在开启状态下单独验证）。
os.environ.setdefault("DDW_LAN_BYPASS", "0")
