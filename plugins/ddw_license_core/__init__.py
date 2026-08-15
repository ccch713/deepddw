"""DDW 许可证管理插件 v1.0.0（DDW AI Hub — 销售端 CRM P4-2）。

销售端许可证（License）全生命周期管理：
- 许可证单号自动生成：LIC-YYYYMMDD-NNN
- 状态机：active → expired / suspended / revoked（suspended ↔ active 可逆）
- 自动过期检查：list / get / stats 前批量把 valid_to<today 的 active 标记为 expired
- 续费：POST /licenses/{id}/renewal（创建新许可证，关联旧许可证，旧许可证变 renewed）
- 插件授权清单 / 产品授权清单 / 节点数 / 用户数管理
- 多租户隔离

所有数据落 SQLite（async SQLAlchemy 2.0）。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-license-core"

__all__ = ["PLUGIN_NAME", "VERSION"]
