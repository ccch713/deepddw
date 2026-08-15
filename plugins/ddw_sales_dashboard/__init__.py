"""DDW 销售看板插件 v1.0.0（DDW AI Hub — 销售端 CRM P0-5）。

聚合查询 P0-1~P0-4 四个插件的数据，输出销售仪表盘所需的统计指标：
- 总览：企业 / 联系人 / 商机 / 报价 / 预计 / 成交 / 成交客户
- 漏斗：按商机阶段分组的 count + total_amount
- 趋势：最近 12 个月的新增商机数 / 总金额 / 成交金额
- 销售排行：按 owner_id 聚合的预计金额、成交金额、成交率
- 最近商机：按 updated_at 倒序的最新 10 条商机
- 阶段分布：用于前端饼图的精简漏斗数据

本插件**不创建任何新表**，所有数据通过 SQLAlchemy 直接 query
P0-1~P0-4 的 ORM 模型聚合得到。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-sales-dashboard"

__all__ = ["PLUGIN_NAME", "VERSION"]
