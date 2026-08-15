"""Pytest 根 conftest：把项目根加入 sys.path，让 ``plugins.xxx`` 可 import。"""
import os
import sys

# 项目根 = conftest.py 所在目录
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 测试环境显式 opt-in 调试万能码（与生产行为分离）
os.environ.setdefault("DDW_ALWAYS_ACCEPT_CODE", "8888")
