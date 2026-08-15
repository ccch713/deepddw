"""DDW 售后工单插件 v1.0.0（DDW AI Hub — 销售端 CRM P4-5）。

销售端售后工单（Support Ticket）：客户报修、咨询、投诉等工单的全生命周期管理。
- 自动生成工单号 TKT-YYYYMMDD-NNN
- 状态机：open → in_progress → resolved → closed（不可跳）
- 多维筛选（按 company/instance/category/priority/assigned_to/status）与统计
- 与客户企业（crm_companies）、客户实例（crm_instances）关联

所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-support-ticket"

__all__ = ["PLUGIN_NAME", "VERSION"]
