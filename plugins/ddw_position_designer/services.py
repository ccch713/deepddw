"""DDW 岗位设计器业务逻辑层。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import DECISION_TYPE_LABELS, PositionDesign
from .schemas import PositionDesignCreateReq, PositionDesignUpdateReq

logger = logging.getLogger(__name__)


def _position_to_dict(p: PositionDesign) -> Dict[str, Any]:
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "name": p.name,
        "department": p.department,
        "report_to": p.report_to,
        "company": p.company,
        "description": p.description,
        "outcomes": p.outcomes or [],
        "human_responsibilities": p.human_responsibilities or [],
        "agent_stack": p.agent_stack or [],
        "decision_rights": p.decision_rights or [],
        "human_capability": p.human_capability,
        "agent_capability": p.agent_capability,
        "handoff_protocol": p.handoff_protocol,
        "risk_controls": p.risk_controls or [],
        "status": p.status,
        "version": p.version,
        "tags": p.tags or [],
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


class PositionDesignService:
    """岗位设计业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- 创建 --------------------------------------------------------------

    async def create(self, data: PositionDesignCreateReq) -> Dict[str, Any]:
        """创建岗位设计。"""
        p = PositionDesign(
            tenant_id=data.tenant_id,
            name=data.name,
            department=data.department,
            report_to=data.report_to,
            company=data.company,
            description=data.description,
            outcomes=data.outcomes or [],
            human_responsibilities=data.human_responsibilities or [],
            agent_stack=data.agent_stack or [],
            decision_rights=[dr.model_dump() for dr in (data.decision_rights or [])],
            human_capability=data.human_capability,
            agent_capability=data.agent_capability,
            handoff_protocol=data.handoff_protocol,
            risk_controls=data.risk_controls or [],
            tags=data.tags or [],
            status="draft",
            version=1,
        )
        self.db.add(p)
        await self.db.commit()
        await self.db.refresh(p)
        return _position_to_dict(p)

    # ----- 查询 --------------------------------------------------------------

    async def get(self, position_id: int, tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        stmt = select(PositionDesign).where(PositionDesign.id == position_id)
        if tenant_id is not None:
            stmt = stmt.where(PositionDesign.tenant_id == tenant_id)
        p = (await self.db.execute(stmt)).scalar_one_or_none()
        return _position_to_dict(p) if p else None

    async def list(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        department: Optional[str] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """分页查询岗位列表。"""
        stmt = select(PositionDesign).where(PositionDesign.tenant_id == tenant_id)
        count_stmt = select(func.count(PositionDesign.id)).where(PositionDesign.tenant_id == tenant_id)

        if department:
            stmt = stmt.where(PositionDesign.department == department)
            count_stmt = count_stmt.where(PositionDesign.department == department)

        if status:
            stmt = stmt.where(PositionDesign.status == status)
            count_stmt = count_stmt.where(PositionDesign.status == status)

        if search:
            kw = f"%{search}%"
            cond = or_(
                PositionDesign.name.ilike(kw),
                PositionDesign.department.ilike(kw),
                PositionDesign.company.ilike(kw),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = (await self.db.execute(count_stmt)).scalar_one() or 0

        stmt = stmt.order_by(PositionDesign.updated_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_position_to_dict(p) for p in rows], int(total)

    async def list_by_department(self, department: str, tenant_id: int) -> List[Dict[str, Any]]:
        """按部门列出所有岗位（用于部门配置页联动展示）。"""
        stmt = (
            select(PositionDesign)
            .where(and_(
                PositionDesign.tenant_id == tenant_id,
                PositionDesign.department == department,
                PositionDesign.status != "archived",
            ))
            .order_by(PositionDesign.name)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_position_to_dict(p) for p in rows]

    # ----- 更新 --------------------------------------------------------------

    async def update(
        self, position_id: int, data: PositionDesignUpdateReq, tenant_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        stmt = select(PositionDesign).where(PositionDesign.id == position_id)
        if tenant_id is not None:
            stmt = stmt.where(PositionDesign.tenant_id == tenant_id)
        p = (await self.db.execute(stmt)).scalar_one_or_none()
        if not p:
            return None

        update_fields = data.model_dump(exclude_unset=True)
        for k, v in update_fields.items():
            if k == "decision_rights" and v is not None:
                # 转换 DecisionRight 对象 → dict
                v = [dr if isinstance(dr, dict) else dr.model_dump() for dr in v]
            setattr(p, k, v)
        p.version += 1

        await self.db.commit()
        await self.db.refresh(p)
        return _position_to_dict(p)

    async def archive(self, position_id: int, tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        return await self.update(
            position_id,
            PositionDesignUpdateReq(status="archived"),
            tenant_id,
        )

    # ----- 统计 --------------------------------------------------------------

    async def count(self, tenant_id: int) -> int:
        stmt = select(func.count(PositionDesign.id)).where(PositionDesign.tenant_id == tenant_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0)


__all__ = ["PositionDesignService"]
