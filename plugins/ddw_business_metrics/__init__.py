"""DDW 业务指标仪表盘插件（DDW AI Hub — 阶段 3-1）。

纯只读聚合查询插件，零新埋点、零新表。
指标从现有表聚合：
- dw_wallet_recharge_orders（MRR，status='paid'）
- usage_logs（WAU / 插件使用率 / Token 消耗）
- crm_lead_claims / crm_opportunities / crm_orders（转化漏斗）
"""

VERSION = "0.1.0"
PLUGIN_NAME = "ddw-business-metrics"

__all__ = ["PLUGIN_NAME", "VERSION"]
