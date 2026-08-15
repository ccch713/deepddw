"""DDW 经销商开户插件 v1.0.0（DDW AI Hub — 销售端 CRM P2-1）。

经销商/代理商/分销商三类的开户与档案管理。覆盖类型、等级、区域、行业、
折扣（产品/插件/服务）、可售范围、合作起止期、状态等。
所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-partner-directory"

__all__ = ["PLUGIN_NAME", "VERSION"]
