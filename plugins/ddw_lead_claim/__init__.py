"""DDW 客户报备与归属插件 v1.0.0（DDW AI Hub — 销售端 CRM P2-2）。

销售端客户报备与归属保护机制：渠道/销售对某客户企业的保护期占位。
- 创建报备时按 protection_days 自动计算 expire_at（默认 60 天）
- list / get / conflict / stats 等 read 类操作前自动把 active 且 expire_at<now 的
  报备批量标记为 expired（模式与 ddw_receivable 的 _auto_mark_overdue 一致）
- 主动释放：POST /claims/{id}/release
- 冲突查询：GET /claims/conflict?company_id=...
- 统计概览：GET /claims/stats
所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-lead-claim"

__all__ = ["PLUGIN_NAME", "VERSION"]
