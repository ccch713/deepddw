"""DDW 企业主体管理插件 v1.0.0（DDW AI Hub — 销售端 CRM P0-1）。

企业工商主数据管理：统一社会信用代码、营业执照、认证状态、开票信息。
所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-company-profile"

__all__ = ["VERSION", "PLUGIN_NAME"]
