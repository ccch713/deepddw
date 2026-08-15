"""DDW 产品文档栏目插件（ddw_docs_portal）。

定位：企业级记忆（ENTERPRISE）的前端显现层 —— 正式文档资产
（白皮书/手册/方案/规章制度）的统一存放、展示、检索、版本管理入口。
复用 ddw_doc_assistant（内容存储/向量化/检索）、ddw_memory（记忆联动）、
ddw-llm-gateway（LLM 代理）、ddw_online_cs（客服引用）。
"""

VERSION = "0.1.0"
PLUGIN_NAME = "ddw-docs-portal"

__all__ = ["PLUGIN_NAME", "VERSION"]
