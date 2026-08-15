"""DDW 产品与插件目录插件 v1.0.0（DDW AI Hub — 销售端 CRM P4-1）。

销售端产品/插件目录主数据：DDW 自研产品（DDW 底座、DDW 插件、Token 套餐）
与第三方产品/服务的统一管理。
- 编码 (code) 全局唯一
- 产品类型枚举：package / plugin / service / token
- 单位 (unit) 灵活：套/年、套/月、个、次等
- 单价 (unit_price) 必填，Numeric(12,2) 精度
- 元数据 (metadata_json) JSON 字段，存放非结构化扩展（如容量、有效期、SKU）
- 软删除：通过 is_active 标志位实现（DELETE 仅翻 is_active=False）

所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-product-catalog"

__all__ = ["PLUGIN_NAME", "VERSION"]
