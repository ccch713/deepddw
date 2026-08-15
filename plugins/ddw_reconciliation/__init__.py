"""DDW 应收与实收核销插件 v1.0.0（DDW AI Hub — 销售端 CRM P1-5）。

核销（Reconciliation）= 把实收（Payment）的金额分配到应收（Receivable）上，
是销售端 CRM 财务对账的核心操作。

本插件**不创建任何新表**，仅通过 SQLAlchemy 直接 query / update
P1-3 ``crm_receivables`` 和 P1-4 ``crm_payments`` 两张表，实现：

- 自动匹配推荐（按金额 + 公司精确匹配）
- 确认核销（事务：更新 receivable.paid_amount + payment.matched_amount，
  状态机自动重算）
- 取消核销（事务：回退已核销金额）
- 核销历史（内存 list，不落库）
- 未核销汇总

所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-reconciliation"

__all__ = ["PLUGIN_NAME", "VERSION"]
