"""DDW Knowledge Hierarchy Plugin — 企业级层级知识检索引擎。

核心能力：
- 多格式文档解析（PDF/DOCX/MD/TXT/HTML/Excel）
- 层级索引（文档→章节→页面→段落）
- 向量检索 + LLM 导航的三阶段混合检索
- 文档生成（8D报告/CAPA/质量报警/COA等模板）
"""

from __future__ import annotations

PLUGIN_NAME = "ddw-knowledge-hierarchy"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "企业级层级知识检索引擎"
