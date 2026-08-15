"""DDW 造价知识库插件 v1.0.0（DDW AI Hub — 设计院插件群 D2）。

历史造价文件 + 定额/清单/指标 → LLM 提炼结构化数据 → 知识检索 → 造价估算。
所有数据落 SQLite（async SQLAlchemy 2.0）。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-cost-knowledge"

__all__ = ["VERSION", "PLUGIN_NAME"]
