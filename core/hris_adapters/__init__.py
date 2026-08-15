"""HRIS 适配器包入口（DDW AI Hub v5.4 — 模块 C）。

所有适配器通过 ``HRISManager.register_adapter_class`` 登记。
"""

from core.hris_adapters.base import BaseHRISAdapter, HRISAuthError, HRISError
from core.hris_adapters.beisen import BeisenAdapter
from core.hris_adapters.dingtalk import DingTalkAdapter
from core.hris_adapters.feishu import FeishuAdapter
from core.hris_adapters.kingdee import KingdeeAdapter
from core.hris_adapters.manager import HRISManager, get_manager
from core.hris_adapters.oracle import OracleHCMAdapter
from core.hris_adapters.sap import SAPSFAdapter
from core.hris_adapters.wecom import WeComAdapter
from core.hris_adapters.workday import WorkdayAdapter

# 内置适配器类
BUILTIN_ADAPTERS = {
    "kingdee": KingdeeAdapter,
    "wecom": WeComAdapter,
    "beisen": BeisenAdapter,
    "feishu": FeishuAdapter,
    "dingtalk": DingTalkAdapter,
    "workday": WorkdayAdapter,
    "sap": SAPSFAdapter,
    "oracle": OracleHCMAdapter,
}

# 自注册到 manager
get_manager()


def install_default_adapters() -> None:
    """把内置适配器注册到 manager。"""
    m = get_manager()
    for name, cls in BUILTIN_ADAPTERS.items():
        m.register_adapter_class(name, cls)
    logger_default = __import__("logging").getLogger(__name__)
    logger_default.info("installed %d default HRIS adapters", len(BUILTIN_ADAPTERS))


__all__ = [
    "BUILTIN_ADAPTERS",
    "BaseHRISAdapter",
    "BeisenAdapter",
    "DingTalkAdapter",
    "FeishuAdapter",
    "HRISAuthError",
    "HRISError",
    "HRISManager",
    "KingdeeAdapter",
    "OracleHCMAdapter",
    "SAPSFAdapter",
    "WeComAdapter",
    "WorkdayAdapter",
    "get_manager",
    "install_default_adapters",
]
