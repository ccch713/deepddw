"""DDW 销售端 AI 副驾驶插件 v1.0.0（DDW AI Hub — 销售端 CRM P3-4）。

基于 P0-1~P0-5 / P1 / P2 / P3-1~P3-3 插件的数据，为销售员提供 AI 辅助能力：
- 商机阶段建议：基于商机基本信息 + 拜访记录，LLM 推荐下一步阶段
- 客户风险提示：评估停滞天数 / 阶段 / 拜访频率，输出风险等级
- 行动建议：根据当前上下文生成下一步具体动作
- 销售日报：聚合指定销售当日工作指标并生成结构化日报
- 销售周报：聚合指定销售本周工作指标并生成结构化周报

本插件**不创建任何新表**：
- 所有数据通过 SQLAlchemy 直接 query 现有插件的 ORM 模型
- 所有 AI 推理走平台 ``embedded_llm.engine.EmbeddedLLM``（默认 echo backend）
- 不持有任何 LLM API Key / 配置硬编码
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-sales-copilot"

__all__ = ["PLUGIN_NAME", "VERSION"]
