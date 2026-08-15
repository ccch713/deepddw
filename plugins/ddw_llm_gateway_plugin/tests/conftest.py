# pytest 配置
import sys
import types
from pathlib import Path

# 添加插件目录到 Python 路径
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir))

# 创建虚拟包让 `from ddw_llm_gateway.xxx import ...` 工作
if "ddw_llm_gateway" not in sys.modules:
    pkg = types.ModuleType("ddw_llm_gateway")
    pkg.__path__ = [str(plugin_dir)]
    pkg.__package__ = "ddw_llm_gateway"
    sys.modules["ddw_llm_gateway"] = pkg
