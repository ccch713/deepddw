"""Skill 分配/移除服务。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_org.models import AgentSkill, OrgSkillPool

logger = logging.getLogger(__name__)


class AgentSkillService:
    """数字员工 Skill 分配服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def assign_skill(
        self,
        agent_id: int,
        skill_id: int,
        assigned_by: Optional[int] = None,
    ) -> Dict[str, Any]:
        """为数字员工分配 skill。"""
        # 检查 skill 是否存在
        pool = await self.db.get(OrgSkillPool, skill_id)
        if not pool:
            raise ValueError(f"skill_id={skill_id} not found in skill pool")

        # 检查是否已分配
        existing = (
            await self.db.execute(
                select(AgentSkill).where(
                    AgentSkill.agent_id == agent_id,
                    AgentSkill.skill_id == skill_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise ValueError(f"agent {agent_id} already has skill {skill_id}")

        askill = AgentSkill(
            agent_id=agent_id,
            skill_id=skill_id,
            assigned_by=assigned_by,
        )
        self.db.add(askill)
        await self.db.commit()
        await self.db.refresh(askill)
        return _agent_skill_to_dict(askill, pool)

    async def remove_skill(self, agent_id: int, skill_id: int) -> bool:
        """移除数字员工的 skill。"""
        askill = (
            await self.db.execute(
                select(AgentSkill).where(
                    AgentSkill.agent_id == agent_id,
                    AgentSkill.skill_id == skill_id,
                )
            )
        ).scalar_one_or_none()
        if not askill:
            return False
        await self.db.delete(askill)
        await self.db.commit()
        return True

    async def update_agent_skill(
        self, askill_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新 agent-skill 关联字段。"""
        askill = await self.db.get(AgentSkill, askill_id)
        if not askill:
            return None
        for field in ("enabled", "proficiency", "trigger_conditions", "sla_seconds"):
            if field in data:
                setattr(askill, field, data[field])
        await self.db.commit()
        await self.db.refresh(askill)
        pool = await self.db.get(OrgSkillPool, askill.skill_id)
        return _agent_skill_to_dict(askill, pool)

    async def list_pool(self) -> List[Dict[str, Any]]:
        """列出 skill 池。"""
        rows = (
            await self.db.execute(select(OrgSkillPool).order_by(OrgSkillPool.id))
        ).scalars().all()
        return [
            {
                "id": sp.id,
                "skill_key": sp.skill_key,
                "name": sp.name,
                "description": sp.description or "",
                "category": sp.category,
            }
            for sp in rows
        ]


def _agent_skill_to_dict(askill: AgentSkill, pool: OrgSkillPool) -> Dict[str, Any]:
    return {
        "id": askill.id,
        "agent_id": askill.agent_id,
        "skill_id": askill.skill_id,
        "skill_key": pool.skill_key,
        "name": pool.name,
        "enabled": askill.enabled,
        "proficiency": askill.proficiency,
        "trigger_conditions": askill.trigger_conditions or [],
        "sla_seconds": askill.sla_seconds,
        "assigned_at": askill.assigned_at,
        "assigned_by": askill.assigned_by,
    }


__all__ = ["AgentSkillService"]
