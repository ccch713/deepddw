"""DDW Wallet 预付费钱包插件"""
from __future__ import annotations

PLUGIN_NAME = "DDW Wallet 预付费钱包"
VERSION = "0.1.0"

TOOL_ANNOTATIONS: dict[str, dict] = {
    "create_account": {"readOnly": False},
    "get_account": {"readOnly": True},
    "create_recharge_order": {"readOnly": False},
    "wechat_notify": {"readOnly": False},
    "alipay_notify": {"readOnly": False},
    "get_order": {"readOnly": True},
    "create_charge": {"readOnly": False},
    "create_refund": {"readOnly": False},
    "create_royalty": {"readOnly": False},
    "list_transactions": {"readOnly": True},
    "list_rates": {"readOnly": True},
}

__all__ = ["PLUGIN_NAME", "VERSION", "TOOL_ANNOTATIONS"]
