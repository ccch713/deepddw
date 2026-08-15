"""DDW 工具路由（Set 减法模型）

继承 技术规范 v1.0 §3.1 + Plugin_SDK §2.2。
"""
from __future__ import annotations

# Coordinator 专用工具（最多 6 个，不可扩展）
COORDINATOR_ONLY_TOOLS: frozenset[str] = frozenset({
    "ddw.delegate_agent",
    "ddw.stop_task",
    "ddw.send_message",
    "ddw.output_result",
    "ddw.modify_plugin",
    "ddw.view_metrics",
})

# 全局禁止工具（所有 Worker 不可用）
ALL_AGENT_DISALLOWED_TOOLS: frozenset[str] = frozenset({
    "ddw.delegate_agent",   # 防递归
    "ddw.schedule_cron",    # 子代理不能创建定时任务
    "ddw.broadcast_signal", # 子代理不能广播信号
})


# Coordinator 专用但不在全局禁止：coordinator 必须能用
# Coordinator 可以有 ALL 但 worker 必须有 ALL_AGENT_DISALLOWED - COORDINATOR_ONLY
# 即:ALL_AGENT_DISALLOWED 中只有 "schedule_cron" 和 "broadcast_signal" 真正全局禁
# "delegate_agent" 在 coordinator 下保留，worker 下禁用

COORDINATOR_OVERLAP = {"ddw.delegate_agent"}  # 在两个集合里

def get_worker_tools(
    declared: set[str],
    agent_type: str = "worker",
) -> set[str]:
    """Set 减法：Worker 可用工具 = Plugin 声明 - 全局禁止 - Coordinator 专用。

    Args:
        declared: Plugin 声明的工具集合
        agent_type: "worker" 或 "coordinator"

    Returns:
        实际可用的工具集合
    """
    base = set(declared)
    if agent_type == "coordinator":
        # Coordinator 保留 delegate_agent（必须能派发），但仍禁 schedule_cron 和 broadcast_signal
        disallowed = ALL_AGENT_DISALLOWED_TOOLS - COORDINATOR_OVERLAP
        return base - disallowed
    # Worker: 减去全部
    return base - ALL_AGENT_DISALLOWED_TOOLS - COORDINATOR_ONLY_TOOLS


def check_version_conflicts(
    new_tool_name: str,
    new_replaces: str | None,
    existing: dict[str, "object"],  # dict[tool_name, ToolDefinition]
) -> list[str]:
    """检查工具版本冲突。返回需要禁用的旧工具名列表。"""
    to_disable: list[str] = []
    if new_replaces and new_replaces in existing:
        to_disable.append(new_replaces)
    # 自身如果已被替换也禁用
    if new_tool_name in existing:
        existing_def = existing[new_tool_name]
        if getattr(existing_def, "replaces", None) == new_tool_name:
            to_disable.append(new_tool_name)
    return to_disable
