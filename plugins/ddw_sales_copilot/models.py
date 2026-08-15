from __future__ import annotations

"""DDW 销售端 AI 副驾驶插件 —— AI 能力聚合插件，**不创建任何新表**。

本插件的所有端点都是基于现有插件的 ORM 模型（crm_opportunities /
crm_sales_notes / crm_quotations / crm_companies / crm_contacts）的
**只读 / 推断 / 报告** 操作，没有任何持久化需求。

因此 models.py 为空占位，仅保留文件以保持插件目录结构一致
（与 P0-5 ddw_sales_dashboard 模式一致）。
"""

__all__: list[str] = []
