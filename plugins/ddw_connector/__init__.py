"""DDW 连接器元数据发现框架插件 V0.1（DDW AI Hub — AI 层连接器）。

连接数据源 → 自动扫描元数据 → 生成数据字典草稿 → 客户确认 → 入库。
支持 sql_readonly（只读数据库）和 api_openapi（OpenAPI 规范）两种数据源。
"""

VERSION = "0.1.0"
PLUGIN_NAME = "ddw-connector"

__all__ = ["PLUGIN_NAME", "VERSION"]
