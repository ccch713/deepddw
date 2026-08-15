from __future__ import annotations

"""DDW 续费与预警插件 ORM 模型占位。

本插件为 **跨插件聚合查询插件**，不创建任何新表。

- 即将到期 / 已逾期 → 读 ``crm_licenses``（由 P4-2 license_core 提供）
- 续费报价估算 → 读 ``crm_licenses`` + ``crm_contracts``（P2 contract_core）
- 续费率统计 → 读 ``crm_licenses``（基于 parent_license_id 自关联）

因此 ``models.py`` 保留为空占位文件，仅供 Base.metadata 注册流程兜底，
且与其它 P0-1~P4-5 插件保持目录结构一致。
"""

__all__: list[str] = []
