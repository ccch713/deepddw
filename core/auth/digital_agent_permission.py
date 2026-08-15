"""数字员工权限检查（P5 — decision_scope 执行）。

数字员工默认权限矩阵：
- read: True（可读取数据）
- create: False（默认不可创建，由 decision_scope 控制）
- edit: False（默认不可编辑）
- delete: False（默认不可删除）
- approve: False（默认不可审批）
- initiate_flow: True（可发起流程）
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 数字员工默认权限矩阵
DIGITAL_AGENT_DEFAULT_PERMISSIONS: Dict[str, bool] = {
    "read": True,
    "create": False,
    "edit": False,
    "delete": False,
    "approve": False,
    "initiate_flow": True,
}


def is_digital_agent(user_ctx: Dict[str, Any]) -> bool:
    """判断当前用户是否为数字员工。"""
    return user_ctx.get("is_digital_agent", False) or user_ctx.get("role") == "digital_agent"


def get_agent_id(user_ctx: Dict[str, Any]) -> Optional[int]:
    """从用户上下文中获取 agent_id。"""
    return user_ctx.get("agent_id")


async def check_digital_agent_permission(
    agent_id: int,
    action: str,
    db: AsyncSession,
    tenant_id: Optional[int] = None,
) -> bool:
    """检查数字员工是否有某项操作权限。

    Args:
        agent_id: 数字员工 ID
        action: 操作类型（read/create/edit/delete/approve/initiate_flow）
        db: 数据库会话
        tenant_id: 当前租户 ID（显式租户隔离）

    Returns:
        True 如果有权限，False 否则
    """
    from plugins.ddw_org.models import DigitalAgent

    agent = await db.get(DigitalAgent, agent_id)
    if not agent:
        logger.warning("digital agent %s not found", agent_id)
        return False
    
    # 租户隔离：显式校验 agent 属于当前租户
    if tenant_id is not None and agent.tenant_id != tenant_id:
        logger.warning("digital agent %s tenant mismatch: agent.tenant=%s, request.tenant=%s",
                       agent_id, agent.tenant_id, tenant_id)
        return False

    # decision_scope 为空时使用默认权限
    scope: List[str] = agent.decision_scope or []
    if not scope:
        return DIGITAL_AGENT_DEFAULT_PERMISSIONS.get(action, False)

    return action in scope


async def require_digital_agent_permission(
    user_ctx: Dict[str, Any],
    action: str,
    db: AsyncSession,
) -> None:
    """要求数字员工具有指定权限，否则抛出 403。

    Args:
        user_ctx: 用户上下文（current_user 返回值）
        action: 操作类型
        db: 数据库会话

    Raises:
        HTTPException: 403 如果权限不足
    """
    if not is_digital_agent(user_ctx):
        # 非数字员工不走此权限检查
        return

    agent_id = get_agent_id(user_ctx)
    if agent_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="数字员工 token 缺少 agent_id",
        )

    has_permission = await check_digital_agent_permission(
        agent_id, action, db, tenant_id=user_ctx.get("tenant_id")
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"数字员工无权执行操作: {action}",
        )


__all__ = [
    "DIGITAL_AGENT_DEFAULT_PERMISSIONS",
    "check_digital_agent_permission",
    "get_agent_id",
    "is_digital_agent",
    "require_digital_agent_permission",
]
