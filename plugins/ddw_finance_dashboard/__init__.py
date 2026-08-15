"""DDW 财务看板插件 v1.0.0（DDW AI Hub — 销售端 CRM P1-6）。

聚合查询 P1-1 合同 / P1-3 应收 / P1-4 实收 三张表的数据，输出财务仪表盘
所需的统计指标：

- 总览（/dashboard/overview）：合同总额 / 已签合同金额 / 应收总额 / 已收金额 /
  未收金额 / 逾期金额
- 逾期列表（/dashboard/overdue）：按未收金额降序的 top N 逾期应收
- 趋势（/dashboard/trend）：最近 12 月按月统计应收金额 + 实收金额
- 财务统计（/dashboard/stats）：按合同 / 应收 / 实收状态分布 + 按企业未收金额

本插件**不创建任何新表**，所有数据通过 SQLAlchemy 直接 query
P1-1 / P1-3 / P1-4 的 ORM 模型聚合得到。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-finance-dashboard"

__all__ = ["PLUGIN_NAME", "VERSION"]
