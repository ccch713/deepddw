"""DDW 商机管理插件 v1.0.0（DDW AI Hub — 销售端 CRM P0-3）。

销售线索/商机全生命周期管理：阶段流转、成交/丢单标记、漏斗与统计。
所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-opportunity"

__all__ = ["VERSION", "PLUGIN_NAME"]
