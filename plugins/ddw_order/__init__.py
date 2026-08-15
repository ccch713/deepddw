"""DDW 订单管理插件 v1.0.0（DDW AI Hub — 销售端 CRM P1-2）。

销售端订单全生命周期管理：
- 自动生成单号 ORD-YYYYMMDD-NNN（按日序号）
- 订单明细用 JSON 列存储（与 P0-4 报价单子表不同的规范选择）
- 状态机：pending → confirmed → delivered → completed；任意非终态可 cancelled
- 多维筛选（order_no / company / contract / status）与统计概览
- 取消必须填写原因

所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-order"

__all__ = ["VERSION", "PLUGIN_NAME"]
