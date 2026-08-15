"""DDW 设计人员资质管理插件 v1.0.0（DDW AI Hub — 设计院插件群 D1）。

覆盖设计院人员证书全生命周期：录入、查询、导入导出、到期预警、年检追踪、统计。
所有数据落 SQLite（async SQLAlchemy 2.0）。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-personnel-qual"

__all__ = ["VERSION", "PLUGIN_NAME"]
