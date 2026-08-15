"""DDW 插件间集成测试 — conftest"""
import sys
from pathlib import Path

# 添加两个插件目录到 sys.path
_plugin_root = Path(__file__).parent.parent
_gateway_dir = _plugin_root / "ddw-llm-gateway"
_token_dir = _plugin_root / "ddw-token-manager"

for d in [_gateway_dir, _token_dir]:
    d_str = str(d)
    if d_str not in sys.path:
        sys.path.insert(0, d_str)
