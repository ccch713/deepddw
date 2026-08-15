"""DDW 转写与结构化插件 v1.0.0（DDW AI Hub — 销售端 CRM P3-3）。

提供录音/文本的 AI 处理能力（基于 DDW 内置 LLM Gateway）：
- 录音转写（模拟 ASR）
- 文本摘要
- 待办事项提取
- 关键实体抽取（公司/人名/金额/日期）

本插件为**聚合 AI 能力插件**，不创建新 ORM 表。
所有数据为请求-响应模式，无持久化需求。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-transcript-ai"

__all__ = ["PLUGIN_NAME", "VERSION"]
