"""DDW Token 额度管理插件 v1.0.0（DDW AI Hub — 销售端 CRM P4-4）。

为客户企业 / 安装实例分配 token 额度，跟踪使用量，控制超量策略：
- entitlement_type：platform（平台共享）/ custom-key（客户自带 Key）/ local-llm（本地 LLM）
- 分配额度 vs 已用额度 vs 剩余额度
- 是否允许超量（overage_allowed）
- 客户自带 Key 仅以脱敏形式（sk-****1234）存储
- 物理删除（本表无 status 字段）

所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-token-entitlement"

__all__ = ["PLUGIN_NAME", "VERSION"]
