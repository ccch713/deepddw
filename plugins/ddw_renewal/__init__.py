"""DDW 续费与预警插件 v1.0.0（DDW AI Hub — 销售端 CRM P4-6）。

跨插件聚合查询 ``crm_licenses``（P4-2 license_core）和 ``crm_contracts``
（P2 contract_core）两张表，输出销售端续费管理所需的指标：

- 即将到期（30/60/90 天）许可证清单（按 valid_to 升序）
- 已逾期许可证清单（按 valid_to 升序）
- 续费报价估算（基于历史合同单价 + 同等时长）
- 续费统计概览（30/60/90 天到期 + 逾期 + 续费率）

本插件 **不创建任何新表**，所有数据通过 SQLAlchemy 直接 query 上述
两张表的 ORM 模型聚合得到。聚合金额统一走 ``func.coalesce(func.sum(...), 0)``，
避免 Python 端 float 精度漂移。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-renewal"

__all__ = ["PLUGIN_NAME", "VERSION"]
