"""
Plugin 基类接入测试

覆盖:
- PluginBase 继承
- __init__ 接受 manifest + **kwargs
- 属性设置
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# 确保 SDK 可导入
_plugin_dir = Path(__file__).parent.parent
_root_dir = _plugin_dir.parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

from sdk.plugin_base import PluginBase


class TestPluginBase:
    """Plugin 基类接入测试"""

    def test_plugin_inherits_plugin_base(self):
        """Plugin 继承 PluginBase"""
        from ddw_llm_gateway.plugin import Plugin
        assert issubclass(Plugin, PluginBase)

    def test_plugin_init_with_manifest(self):
        """__init__ 接受 manifest 参数"""
        from ddw_llm_gateway.plugin import Plugin
        app = MagicMock()
        manifest = {"name": "test", "version": "1.0.0"}
        plugin = Plugin(app=app, manifest=manifest)
        assert plugin.manifest == manifest
        assert plugin.app is app

    def test_plugin_init_with_kwargs(self):
        """__init__ 接受 **kwargs 并设置属性"""
        from ddw_llm_gateway.plugin import Plugin
        plugin = Plugin(custom_attr="value", debug=True)
        assert plugin.custom_attr == "value"
        assert plugin.debug is True

    def test_plugin_init_backward_compatible(self):
        """__init__ 向后兼容：无参数调用"""
        from ddw_llm_gateway.plugin import Plugin
        plugin = Plugin()
        assert plugin.name == "ddw_llm_gateway_plugin"
        assert plugin.version == "1.0.0"

    def test_plugin_has_description(self):
        """Plugin 有 description 属性"""
        from ddw_llm_gateway.plugin import Plugin
        assert Plugin.description != ""

    def test_main_plugin_init_with_kwargs(self):
        """LLMGatewayPlugin __init__ 接受 **kwargs"""
        from ddw_llm_gateway.main import LLMGatewayPlugin
        app = MagicMock()
        plugin = LLMGatewayPlugin(app=app, extra="data")
        assert plugin.extra == "data"
