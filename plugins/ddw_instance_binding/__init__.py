"""DDW 实例绑定插件 v1.0.0（DDW AI Hub — 销售端 CRM P4-3）。

销售端实例绑定（Instance Binding）：把客户企业 / 许可证与具体运行时实例
（云端租户 ID 或本地部署实例 ID）建立关联。核心功能：
- 绑定：企业 / 许可证 ↔ 实例（saas / on-premise）
- 状态机：active / inactive / suspended（软删除走 suspended）
- 心跳：实例上报 last_heartbeat
- 统计：total / 各状态计数 / by_instance_type / by_environment

所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-instance-binding"

__all__ = ["PLUGIN_NAME", "VERSION"]
