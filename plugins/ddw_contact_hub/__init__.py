from __future__ import annotations

"""DDW 联系人管理插件 v1.0.0（DDW AI Hub — 销售端 CRM P0-2）。

企业级联系人主数据管理：姓名、职位、手机、邮箱、微信、标签、分组、主联系人标记。
所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-contact-hub"

__all__ = ["VERSION", "PLUGIN_NAME"]
