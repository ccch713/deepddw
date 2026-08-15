"""DDW 岗位设计器插件 v1.0.0（DDW AI Hub - 人机协同岗位设计）。

能力：
- 4 维岗位设计：Outcome × 人的责任 × Agent Stack × Decision Rights
- 5 因素决策路由引擎（risk_level / explainability / complexity / urgency / precedent）
- 按部门推荐 Agent 组合
- 联动 ddw_opc_departments（按部门查询岗位）
- 导出 HTML 岗位说明书

数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-position-designer"

__all__ = ["VERSION", "PLUGIN_NAME"]
