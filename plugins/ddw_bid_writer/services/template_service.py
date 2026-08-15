"""标书模板 CRUD 服务。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_bid_writer.models import BidTemplate

logger = logging.getLogger(__name__)


class TemplateService:
    """标书模板服务。"""

    async def create(self, session: AsyncSession, payload: Dict[str, Any]) -> BidTemplate:
        if payload.get("is_default"):
            # 取消同 doc_type 的其他 default
            await self._clear_default(session, payload["tenant_id"], payload.get("doc_type", "技术标"))
        t = BidTemplate(**payload)
        session.add(t)
        await session.flush()
        await session.refresh(t)
        return t

    async def get(self, session: AsyncSession, template_id: int) -> Optional[BidTemplate]:
        return (
            await session.execute(select(BidTemplate).where(BidTemplate.id == template_id))
        ).scalar_one_or_none()

    async def update(
        self, session: AsyncSession, template_id: int, patch: Dict[str, Any]
    ) -> Optional[BidTemplate]:
        t = await self.get(session, template_id)
        if t is None:
            return None
        if patch.get("is_default"):
            await self._clear_default(session, t.tenant_id, patch.get("doc_type", t.doc_type))
        for k, v in patch.items():
            if v is not None and hasattr(t, k):
                setattr(t, k, v)
        await session.flush()
        await session.refresh(t)
        return t

    async def delete(self, session: AsyncSession, template_id: int) -> bool:
        t = await self.get(session, template_id)
        if t is None:
            return False
        await session.delete(t)
        await session.flush()
        return True

    async def list(
        self,
        session: AsyncSession,
        doc_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[int, List[BidTemplate]]:
        where = []
        if doc_type:
            where.append(BidTemplate.doc_type == doc_type)
        count_q = select(func.count(BidTemplate.id))
        list_q = select(BidTemplate).order_by(BidTemplate.id.desc())
        if where:
            count_q = count_q.where(and_(*where))
            list_q = list_q.where(and_(*where))
        total = (await session.execute(count_q)).scalar_one()
        items = (
            await session.execute(list_q.offset((page - 1) * page_size).limit(page_size))
        ).scalars().all()
        return total, list(items)

    async def get_default(
        self, session: AsyncSession, tenant_id: int, doc_type: str
    ) -> Optional[BidTemplate]:
        return (
            await session.execute(
                select(BidTemplate).where(
                    and_(
                        BidTemplate.tenant_id == tenant_id,
                        BidTemplate.doc_type == doc_type,
                        BidTemplate.is_default.is_(True),
                    )
                )
            )
        ).scalar_one_or_none()

    async def _clear_default(
        self, session: AsyncSession, tenant_id: int, doc_type: str
    ) -> None:
        from sqlalchemy import update

        await session.execute(
            update(BidTemplate)
            .where(
                and_(
                    BidTemplate.tenant_id == tenant_id,
                    BidTemplate.doc_type == doc_type,
                    BidTemplate.is_default.is_(True),
                )
            )
            .values(is_default=False)
        )


__all__ = ["TemplateService"]
