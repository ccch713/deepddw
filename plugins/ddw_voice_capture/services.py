from __future__ import annotations

"""DDW 录音与语音输入插件业务逻辑层。

服务：
- :class:`VoiceRecordService` —— 录音元数据 CRUD + 软删除 + 统计

软删除策略：
- ``DELETE`` 走软删除：``status = "failed"`` + ``notes`` 追加 "deleted by user"
- 与 P0-1 company_profile 一致：保留历史记录便于审计
- 不可物理删除（录音属于销售过程资产）
"""

import logging
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import VoiceRecord
from .schemas import (
    VoiceRecordCreateReq,
    VoiceRecordListResp,
    VoiceRecordResp,
    VoiceRecordStatsResp,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _voice_to_dict(v: VoiceRecord) -> dict[str, Any]:
    """ORM → dict（用于响应）。"""
    return {
        "id": v.id,
        "tenant_id": v.tenant_id,
        "user_id": v.user_id,
        "company_id": v.company_id,
        "contact_id": v.contact_id,
        "opportunity_id": v.opportunity_id,
        "file_url": v.file_url,
        "file_size": v.file_size,
        "duration_seconds": v.duration_seconds,
        "source_type": v.source_type,
        "notes": v.notes,
        "status": v.status,
        "created_by": v.created_by,
        "created_at": v.created_at,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class VoiceRecordService:
    """录音元数据业务服务。

    设计原则：
    - 本插件**不**实现语音转写。``status`` 中 ``transcribed / processed``
      状态由 P3-3 ddw_voice_transcribe 写入；本插件只负责创建、查询、软删除、统计。
    - 软删除：``status = failed`` + ``notes`` 追加 ``"deleted by user"``，**不物理删除**。
    - 默认 ``status = "uploaded"``。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #

    async def create(self, data: VoiceRecordCreateReq) -> dict[str, Any]:
        """上传录音元数据。

        - ``status`` 默认 ``uploaded``
        - ``file_url / file_size / duration_seconds`` 必填
        - 关联字段（``company_id / contact_id / opportunity_id``）皆可空
        """
        record = VoiceRecord(
            tenant_id=data.tenant_id,
            user_id=data.user_id,
            company_id=data.company_id,
            contact_id=data.contact_id,
            opportunity_id=data.opportunity_id,
            file_url=data.file_url,
            file_size=data.file_size,
            duration_seconds=data.duration_seconds,
            source_type=data.source_type,
            notes=data.notes,
            status="uploaded",
            created_by=data.created_by,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)

        logger.info(
            "voice record created: id=%s source=%s duration=%ss size=%s user_id=%s",
            record.id,
            record.source_type,
            record.duration_seconds,
            record.file_size,
            record.user_id,
        )
        return _voice_to_dict(record)

    # ------------------------------------------------------------------ #
    # get
    # ------------------------------------------------------------------ #

    async def get(self, record_id: int) -> dict[str, Any] | None:
        """获取录音详情。"""
        record = await self.db.get(VoiceRecord, record_id)
        if not record:
            return None
        return _voice_to_dict(record)

    # ------------------------------------------------------------------ #
    # list
    # ------------------------------------------------------------------ #

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[int] = None,
        company_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        source_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> VoiceRecordListResp:
        """录音列表（分页 + 多维筛选）。

        筛选字段：
        - user_id / company_id / contact_id / opportunity_id：精确匹配
        - source_type：精确匹配（local / phone / meeting / memo）
        - status：精确匹配（uploaded / transcribed / processed / failed）
        """
        conditions = []
        if user_id is not None:
            conditions.append(VoiceRecord.user_id == user_id)
        if company_id is not None:
            conditions.append(VoiceRecord.company_id == company_id)
        if contact_id is not None:
            conditions.append(VoiceRecord.contact_id == contact_id)
        if opportunity_id is not None:
            conditions.append(VoiceRecord.opportunity_id == opportunity_id)
        if source_type:
            conditions.append(VoiceRecord.source_type == source_type)
        if status:
            conditions.append(VoiceRecord.status == status)

        # total
        count_stmt = select(func.count(VoiceRecord.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(VoiceRecord)
            .order_by(VoiceRecord.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return VoiceRecordListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[VoiceRecordResp(**_voice_to_dict(r)) for r in rows],
        )

    # ------------------------------------------------------------------ #
    # soft delete
    # ------------------------------------------------------------------ #

    async def soft_delete(self, record_id: int) -> dict[str, Any] | None:
        """软删除录音（``status = failed`` + ``notes`` 追加 ``"deleted by user"``）。

        约束：
        - 仅未删除的记录（``status != failed``）可被软删除
        - 二次删除返回 None（视为已删除，避免重复追加 notes）
        - 不物理删除：录音属于历史资产
        """
        record = await self.db.get(VoiceRecord, record_id)
        if not record:
            return None
        if record.status == "failed":
            # 已是删除态，视作不存在
            return None

        # 追加 notes（不覆盖原内容）
        marker = "deleted by user"
        if record.notes and marker not in record.notes:
            record.notes = f"{record.notes}\n{marker}"
        elif not record.notes:
            record.notes = marker
        record.status = "failed"

        await self.db.commit()
        await self.db.refresh(record)
        logger.info(
            "voice record soft-deleted: id=%s source=%s",
            record.id,
            record.source_type,
        )
        return _voice_to_dict(record)

    # ------------------------------------------------------------------ #
    # stats
    # ------------------------------------------------------------------ #

    async def stats(self) -> VoiceRecordStatsResp:
        """统计概览：各状态计数 + 总时长 + 总大小 + 按 source_type 分组。

        状态由本插件创建时默认 ``uploaded``，``transcribed / processed``
        由 P3-3 ddw_voice_transcribe 写入；``failed`` 可由本插件软删除或
        P3-3 失败转写产生。
        """
        # 按 status 分组
        by_status_rows = (
            await self.db.execute(
                select(VoiceRecord.status, func.count(VoiceRecord.id)).group_by(
                    VoiceRecord.status
                )
            )
        ).all()
        by_status: dict[str, int] = {s: cnt for s, cnt in by_status_rows}

        # 总时长（秒）
        total_duration = (
            await self.db.execute(
                select(func.coalesce(func.sum(VoiceRecord.duration_seconds), 0))
            )
        ).scalar_one()
        total_duration = int(total_duration or 0)

        # 总大小（字节）
        total_size = (
            await self.db.execute(
                select(func.coalesce(func.sum(VoiceRecord.file_size), 0))
            )
        ).scalar_one()
        total_size = int(total_size or 0)

        # 按 source_type 分组
        by_source_rows = (
            await self.db.execute(
                select(VoiceRecord.source_type, func.count(VoiceRecord.id))
                .where(VoiceRecord.source_type.isnot(None))
                .group_by(VoiceRecord.source_type)
            )
        ).all()
        by_source = {s: cnt for s, cnt in by_source_rows}

        return VoiceRecordStatsResp(
            total=sum(by_status.values()),
            uploaded=by_status.get("uploaded", 0),
            transcribed=by_status.get("transcribed", 0),
            processed=by_status.get("processed", 0),
            failed=by_status.get("failed", 0),
            total_duration=total_duration,
            total_size=total_size,
            by_source_type=by_source,
        )


__all__ = ["VoiceRecordService"]
