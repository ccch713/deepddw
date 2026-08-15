"""DDW 应收管理插件 v1.0.0（DDW AI Hub — 销售端 CRM P1-3）。

应收（Receivable）全生命周期管理：应收计划 / 节点、部分收款 / 全额收款、
逾期自动标记、与企业/订单/合同关联。
所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-receivable"

__all__ = ["VERSION", "PLUGIN_NAME"]
