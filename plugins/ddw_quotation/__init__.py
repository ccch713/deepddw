"""DDW 报价单管理插件 v1.0.0（DDW AI Hub — 销售端 CRM P0-4）。

销售端报价单全生命周期管理：报价单主表 + 明细子表、自动单号生成、总金额 / 折后金额计算、
状态机（draft → sent → accepted/rejected/expired）、多维筛选与统计。
所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-quotation"

__all__ = ["VERSION", "PLUGIN_NAME"]
