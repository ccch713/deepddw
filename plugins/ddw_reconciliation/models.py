from __future__ import annotations

"""DDW 应收实收核销插件 —— 不创建任何新表的聚合/操作型插件。

本插件直接读写 P1-3 crm_receivables 与 P1-4 crm_payments 两张表，
不维护自己的 ORM 模型。因此 models.py 留空（仅占位以保持插件目录结构一致，
便于后续如需新增 reconciliation 流水表时直接扩展）。

历史记录当前使用模块级内存 list（_history），无需新增表。
"""

__all__: list[str] = []
