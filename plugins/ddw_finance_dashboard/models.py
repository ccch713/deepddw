from __future__ import annotations

"""DDW 财务看板插件 —— 聚合查询插件，**不创建任何新表**。

本插件直接 query P1-1 / P1-3 / P1-4 提供的 ORM 模型（crm_contracts /
crm_receivables / crm_payments），所有统计指标在 service 层用 SQL 聚合计算。

因此 models.py 为空占位，但保留文件以保持插件目录结构一致（方便后续若
需要做物化视图缓存表时直接扩展）。
"""

__all__: list[str] = []
