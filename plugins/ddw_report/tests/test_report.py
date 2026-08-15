"""ddw-report 基本测试"""
from plugins.ddw_report import PLUGIN_NAME, VERSION


def test_plugin_metadata():
    assert VERSION == "0.1.0"
    assert PLUGIN_NAME == "ddw-report"
