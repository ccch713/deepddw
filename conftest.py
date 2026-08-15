"""Pytest 根 conftest：把项目根加入 sys.path，让 ``plugins.xxx`` 可 import。"""
import os
import sys

# 项目根 = conftest.py 所在目录
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 测试环境默认使用独立访问 Token（P0-1 门禁）
os.environ.setdefault("DDW_ACCESS_TOKEN", "test-token-deepddw")
