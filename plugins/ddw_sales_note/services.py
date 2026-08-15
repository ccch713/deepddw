from __future__ import annotations

"""DDW 拜访与沟通记录插件业务逻辑层。"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import SalesNote
from .schemas import (
    SalesNoteCreateReq,
    SalesNoteListResp,
    SalesNoteResp,
    SalesNoteStatsResp,
    SalesNoteUpdateReq,
)

logger = logging.getLogger(__name__)

# 沟通类型白名单（与 manifest.yaml config_schema.note_types 保持一致）
ALLOWED_NOTE_TYPES = {"visit", "call", "meeting", "email", "wechat"}


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _note_to_dict(n: SalesNote) -> Dict[str, Any]:
    """ORM → dict（用于响应）。"""
    return {
        "id": n.id,
        "tenant_id": n.tenant_id,
        "user_id": n.user_id,
        "company_id": n.company_id,
        "contact_id": n.contact_id,
        "opportunity_id": n.opportunity_id,
        "note_type": n.note_type,
        "title": n.title,
        "content": n.content,
        "visit_date": n.visit_date,
        "tags": n.tags or [],
        "attachments": n.attachments or [],
        "created_at": n.created_at,
        "updated_at": n.updated_at,
        "created_by": n.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class SalesNoteService:
    """拜访/沟通记录业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------------------------------------------------------------------
    # 新建
    # ---------------------------------------------------------------------

    async def create(self, data: SalesNoteCreateReq) -> Dict[str, Any]:
        """新建沟通记录。

        - ``created_by`` 缺省时退化为 ``user_id``（保证审计字段非空）
        - ``note_type`` 必须在白名单内，否则抛 ValueError
        """
        if data.note_type not in ALLOWED_NOTE_TYPES:
            raise ValueError(
                f"note_type '{data.note_type}' 不合法，允许值: {sorted(ALLOWED_NOTE_TYPES)}"
            )

        created_by = data.created_by if data.created_by is not None else data.user_id

        note = SalesNote(
            tenant_id=data.tenant_id,
            user_id=data.user_id,
            company_id=data.company_id,
            contact_id=data.contact_id,
            opportunity_id=data.opportunity_id,
            note_type=data.note_type,
            title=data.title,
            content=data.content,
            visit_date=data.visit_date,
            tags=data.tags or [],
            attachments=data.attachments or [],
            created_by=created_by,
        )
        self.db.add(note)
        await self.db.commit()
        await self.db.refresh(note)
        logger.info(
            "sales note created: id=%s type=%s opp_id=%s",
            note.id,
            note.note_type,
            note.opportunity_id,
        )
        return _note_to_dict(note)

    # ---------------------------------------------------------------------
    # 详情
    # ---------------------------------------------------------------------

    async def get(self, note_id: int) -> Optional[Dict[str, Any]]:
        """获取单条记录详情。"""
        note = await self.db.get(SalesNote, note_id)
        if not note:
            return None
        return _note_to_dict(note)

    # ---------------------------------------------------------------------
    # 列表
    # ---------------------------------------------------------------------

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[int] = None,
        company_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        note_type: Optional[str] = None,
        visit_date_from: Optional[datetime] = None,
        visit_date_to: Optional[datetime] = None,
    ) -> SalesNoteListResp:
        """记录列表（分页 + 多维筛选）。"""
        conditions = []
        if user_id is not None:
            conditions.append(SalesNote.user_id == user_id)
        if company_id is not None:
            conditions.append(SalesNote.company_id == company_id)
        if contact_id is not None:
            conditions.append(SalesNote.contact_id == contact_id)
        if opportunity_id is not None:
            conditions.append(SalesNote.opportunity_id == opportunity_id)
        if note_type:
            conditions.append(SalesNote.note_type == note_type)
        if visit_date_from is not None:
            conditions.append(SalesNote.visit_date >= visit_date_from)
        if visit_date_to is not None:
            conditions.append(SalesNote.visit_date <= visit_date_to)

        # 总数
        count_stmt = select(func.count(SalesNote.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # 列表
        offset = (page - 1) * page_size
        list_stmt = (
            select(SalesNote)
            .order_by(SalesNote.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return SalesNoteListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[SalesNoteResp(**_note_to_dict(n)) for n in rows],
        )

    # ---------------------------------------------------------------------
    # 按商机查询
    # ---------------------------------------------------------------------

    async def list_by_opportunity(self, opportunity_id: int) -> List[Dict[str, Any]]:
        """某商机下的所有记录（按 visit_date 降序，visit_date 为空时回退 id 倒序）。"""
        stmt = (
            select(SalesNote)
            .where(SalesNote.opportunity_id == opportunity_id)
            .order_by(SalesNote.visit_date.desc().nulls_last(), SalesNote.id.desc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_note_to_dict(n) for n in rows]

    # ---------------------------------------------------------------------
    # 更新
    # ---------------------------------------------------------------------

    async def update(self, note_id: int, data: SalesNoteUpdateReq) -> Optional[Dict[str, Any]]:
        """更新记录字段。"""
        note = await self.db.get(SalesNote, note_id)
        if not note:
            return None

        updates = data.model_dump(exclude_unset=True)

        # note_type 改值时需校验白名单
        if "note_type" in updates and updates["note_type"] not in ALLOWED_NOTE_TYPES:
            raise ValueError(
                f"note_type '{updates['note_type']}' 不合法，允许值: {sorted(ALLOWED_NOTE_TYPES)}"
            )

        for k, v in updates.items():
            setattr(note, k, v)

        await self.db.commit()
        await self.db.refresh(note)
        logger.info("sales note updated: id=%s", note.id)
        return _note_to_dict(note)

    # ---------------------------------------------------------------------
    # 硬删除
    # ---------------------------------------------------------------------

    async def delete(self, note_id: int) -> bool:
        """硬删除记录（任务规范明确走真删除）。

        沟通记录属于销售过程性数据，无强制审计要求，按规范物理删除。
        """
        note = await self.db.get(SalesNote, note_id)
        if not note:
            return False
        await self.db.delete(note)
        await self.db.commit()
        logger.info("sales note hard-deleted: id=%s", note_id)
        return True

    # ---------------------------------------------------------------------
    # 统计
    # ---------------------------------------------------------------------

    async def stats(self) -> SalesNoteStatsResp:
        """统计概览：total + by_note_type + 最近 30 天。"""
        # 按 note_type
        by_type_rows = (
            await self.db.execute(
                select(SalesNote.note_type, func.count(SalesNote.id)).group_by(
                    SalesNote.note_type
                )
            )
        ).all()
        by_type = {t: cnt for t, cnt in by_type_rows}
        total = sum(by_type.values())

        # 最近 30 天（基于 visit_date，非 created_at）
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        # 兼容 naive datetime：去掉 tzinfo 后比较
        cutoff_naive = cutoff.replace(tzinfo=None)
        recent_30d = (
            await self.db.execute(
                select(func.count(SalesNote.id)).where(
                    and_(
                        SalesNote.visit_date.isnot(None),
                        SalesNote.visit_date >= cutoff_naive,
                    )
                )
            )
        ).scalar_one()

        return SalesNoteStatsResp(
            total=total,
            by_note_type=by_type,
            recent_30d=int(recent_30d),
        )


__all__ = ["SalesNoteService"]
