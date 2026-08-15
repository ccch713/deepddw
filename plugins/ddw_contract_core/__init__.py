"""DDW 合同中心插件 v1.0.0（DDW AI Hub — 销售端 CRM P1-1）。

销售端合同全生命周期管理：合同主表、自动单号生成（CT-YYYYMMDD-NNN）、
合同状态机（draft → pending_approval → approved → signed → active → completed/terminated）、
多维筛选与统计。
所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-contract-core"

__all__ = ["VERSION", "PLUGIN_NAME"]
