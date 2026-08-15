"""DDW 账号/租户/实例映射插件 v1.0.0（DDW AI Hub — 销售端 CRM P5-3）。

将 CRM 客户企业映射到下游三种账号/租户/实例（user / saas_tenant / on_premise_instance），
支撑跨系统账号关联、唯一性校验、生命周期管理。所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-account-linker"

__all__ = ["PLUGIN_NAME", "VERSION"]
