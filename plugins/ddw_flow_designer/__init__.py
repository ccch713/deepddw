"""碳硅协作空间插件 v1.0.0（DDW AI Hub — 零代码 DAG 流程设计器）。

企业员工通过拖拽方式设计数字员工和员工之间的 skill 协作流程：
- 流程 CRUD + 草稿/发布/版本管理（semver 自动递增）
- 跨部门流程审核（pending_review → published）
- 串行 LLM 执行引擎（按拓扑序调用节点）
- 公司级统计看板（只读）
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-flow-designer"

__all__ = ["PLUGIN_NAME", "VERSION"]
