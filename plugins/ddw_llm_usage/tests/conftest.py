"""ddw_llm_usage 测试 conftest（适配开发仓根 conftest）。

ECS 快照原版含防御性 sys.modules purge（针对 cloud-llm/local-llm 副本环境），
与开发仓根 conftest 冲突（KeyError: plugins.ddw_llm_usage.tests.conftest）。
此处保留环境变量 / sys.path / sdk 版本断言，去掉 purge 与 namespace 重建。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 测试环境变量（鉴权用）
os.environ["DDW_LLM_USAGE_ADMIN_KEY"] = "test-admin-key"
os.environ["DDW_LLM_USAGE_SERVICE_KEY"] = "test-service-key"

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import sdk  # noqa: E402,F401
import sdk.plugin_base  # noqa: E402,F401

assert sys.modules["sdk.plugin_base"].__file__.endswith("sdk/plugin_base.py"), (
    "PluginBase 必须来自本地 sdk/"
)
