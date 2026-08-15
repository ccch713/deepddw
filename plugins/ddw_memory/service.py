"""ddw_memory 核心业务逻辑 — 四层持久化记忆引擎。"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import core.database.session as _db_mod

from .models import (
    AutoCaptureConfigORM,
    AutoCapturePendingORM,
    MemoryEntryOut,
    MemoryLayer,
    MemoryORM,
    MemorySearchHit,
    MemorySearchResponse,
    PositionSOPTemplateORM,
    PositionSOPTemplateOut,
)


@asynccontextmanager
async def _committed_session() -> AsyncIterator[AsyncSession]:
    """session_scope 的 auto-commit 版本：成功时 commit，异常时 rollback。"""
    sm = _db_mod._session_maker
    if sm is None:
        sm = _db_mod.get_session_maker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

logger = logging.getLogger(__name__)

PHYSICAL_DELETE_DAYS = 30

# 层级权重（检索排序用）
LAYER_WEIGHTS: dict[str, float] = {
    MemoryLayer.PERSONAL.value: 1.2,
    MemoryLayer.POSITION.value: 1.1,
    MemoryLayer.DEPARTMENT.value: 1.0,
    MemoryLayer.ENTERPRISE.value: 0.9,
}


def _orm_to_out(row: MemoryORM) -> MemoryEntryOut:
    tags = row.tags if isinstance(row.tags, list) else []
    return MemoryEntryOut(
        id=row.id,
        memory_uuid=row.memory_uuid,
        layer=MemoryLayer(row.layer),
        content=row.content,
        summary=row.summary,
        creator_id=row.creator_id,
        department_id=row.department_id,
        position_id=row.position_id,
        tags=tags,
        source_type=row.source_type or "manual",
        source_session_id=row.source_session_id,
        expires_at=row.expires_at,
        is_deleted=row.is_deleted,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _sorm_to_out(row: PositionSOPTemplateORM) -> PositionSOPTemplateOut:
    return PositionSOPTemplateOut(
        id=row.id,
        template_uuid=row.template_uuid,
        position_name=row.position_name,
        position_id=row.position_id,
        sop_steps=row.sop_steps if isinstance(row.sop_steps, list) else [],
        knowledge_doc_ids=row.knowledge_doc_ids if isinstance(row.knowledge_doc_ids, list) else [],
        applicable_departments=row.applicable_departments if isinstance(row.applicable_departments, list) else [],
        version=row.version,
        created_at=row.created_at,
    )


class MemoryService:
    """四层记忆系统服务（SQLAlchemy 持久化）。"""

    # ── 记忆 CRUD ──────────────────────────────────────────

    async def create_memory(
        self,
        tenant_id: int,
        layer: MemoryLayer,
        content: str,
        creator_id: int,
        department_id: int | None = None,
        position_id: int | None = None,
        tags: list[str] | None = None,
        source_type: str = "manual",
        source_session_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> MemoryEntryOut:
        if layer == MemoryLayer.DEPARTMENT and not department_id:
            raise ValueError("department 层记忆必须指定 department_id")

        async with _committed_session() as session:
            row = MemoryORM(
                tenant_id=tenant_id,
                layer=layer.value,
                content=content,
                creator_id=creator_id,
                department_id=department_id,
                position_id=position_id,
                tags=tags or [],
                source_type=source_type,
                source_session_id=source_session_id,
                expires_at=expires_at,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            logger.info("memory created: uuid=%s layer=%s tenant=%s", row.memory_uuid, layer.value, tenant_id)
            return _orm_to_out(row)

    async def get_memory(self, tenant_id: int, memory_id: int) -> MemoryEntryOut | None:
        async with _committed_session() as session:
            row = (
                await session.execute(
                    select(MemoryORM).where(
                        MemoryORM.tenant_id == tenant_id,
                        MemoryORM.id == memory_id,
                        MemoryORM.is_deleted == False,
                    )
                )
            ).scalar_one_or_none()
            return _orm_to_out(row) if row else None

    async def list_memories(
        self,
        tenant_id: int,
        layer: MemoryLayer | None = None,
        department_id: int | None = None,
        position_id: int | None = None,
        creator_id: int | None = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        async with _committed_session() as session:
            q = select(MemoryORM).where(MemoryORM.tenant_id == tenant_id)
            if not include_deleted:
                q = q.where(MemoryORM.is_deleted == False)
            if layer:
                q = q.where(MemoryORM.layer == layer.value)
            if department_id is not None:
                q = q.where(MemoryORM.department_id == department_id)
            if position_id is not None:
                q = q.where(MemoryORM.position_id == position_id)
            if creator_id is not None:
                q = q.where(MemoryORM.creator_id == creator_id)

            # total count
            count_q = select(func.count()).select_from(q.subquery())
            total = (await session.execute(count_q)).scalar() or 0

            # paginated results
            rows = (
                await session.execute(
                    q.order_by(MemoryORM.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()

            return {"items": [_orm_to_out(r) for r in rows], "total": total}

    async def update_memory(
        self,
        tenant_id: int,
        memory_id: int,
        content: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> MemoryEntryOut | None:
        async with _committed_session() as session:
            row = (
                await session.execute(
                    select(MemoryORM).where(
                        MemoryORM.tenant_id == tenant_id,
                        MemoryORM.id == memory_id,
                        MemoryORM.is_deleted == False,
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return None
            if content is not None:
                row.content = content
            if summary is not None:
                row.summary = summary
            if tags is not None:
                row.tags = tags
            if expires_at is not None:
                row.expires_at = expires_at
            await session.flush()
            await session.refresh(row)
            return _orm_to_out(row)

    async def delete_memory(self, tenant_id: int, memory_id: int) -> bool:
        async with _committed_session() as session:
            row = (
                await session.execute(
                    select(MemoryORM).where(
                        MemoryORM.tenant_id == tenant_id,
                        MemoryORM.id == memory_id,
                        MemoryORM.is_deleted == False,
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return False
            row.is_deleted = True
            row.deleted_at = datetime.now(timezone.utc)
            await session.flush()
            return True

    # ── 四层穿透检索 ────────────────────────────────────────

    async def search_memories(
        self,
        tenant_id: int,
        query: str,
        user_id: int,
        layers: list[MemoryLayer] | None = None,
        department_id: int | None = None,
        position_id: int | None = None,
        top_k: int = 10,
        search_mode: str = "hybrid",
        query_embedding: list[float] | None = None,
    ) -> MemorySearchResponse:
        from .retrieval import _cosine_similarity, _keyword_score, _rrf_merge

        t0 = time.monotonic()
        async with _committed_session() as session:
            # base query with tenant + layer + not-deleted filters
            base_q = select(MemoryORM).where(
                MemoryORM.tenant_id == tenant_id,
                MemoryORM.is_deleted == False,
            )
            if layers:
                base_q = base_q.where(MemoryORM.layer.in_([lyr.value for lyr in layers]))

            rows = (await session.execute(base_q.limit(top_k * 5))).scalars().all()

        # ── keyword branch ──
        keyword_hits: list[dict] = []
        if search_mode in ("keyword", "hybrid"):
            # scoring done in Python (not DB) for ngram support
            for row in rows:
                tags = row.tags if isinstance(row.tags, list) else []
                if row.layer == MemoryLayer.PERSONAL.value and row.creator_id != user_id:
                    continue
                kw_score = _keyword_score(query, row.content)
                if kw_score <= 0:
                    continue
                layer_w = LAYER_WEIGHTS.get(row.layer, 1.0)
                if row.layer == MemoryLayer.ENTERPRISE.value and "redline" in tags:
                    kw_score = 999.0
                    layer_w = 1.5
                keyword_hits.append({
                    "row": row, "score": kw_score * layer_w,
                    "match_type": "keyword", "layer_weight": layer_w, "uuid": row.memory_uuid,
                })

        # ── vector branch ──
        vector_hits: list[dict] = []
        if search_mode in ("vector", "hybrid") and query_embedding:
            for row in rows:
                tags = row.tags if isinstance(row.tags, list) else []
                if row.layer == MemoryLayer.PERSONAL.value and row.creator_id != user_id:
                    continue
                if not row.embedding_json:
                    continue
                try:
                    import json as _json
                    doc_emb = _json.loads(row.embedding_json) if isinstance(row.embedding_json, str) else row.embedding_json
                    cos_sim = _cosine_similarity(query_embedding, doc_emb)
                    if cos_sim <= 0.1:
                        continue
                    layer_w = LAYER_WEIGHTS.get(row.layer, 1.0)
                    if row.layer == MemoryLayer.ENTERPRISE.value and "redline" in tags:
                        cos_sim = 999.0
                        layer_w = 1.5
                    vector_hits.append({
                        "row": row, "score": cos_sim * layer_w,
                        "match_type": "vector", "layer_weight": layer_w, "uuid": row.memory_uuid,
                    })
                except Exception:
                    continue

        # ── merge branches ──
        if search_mode == "hybrid" and keyword_hits and vector_hits:
            merged = _rrf_merge(keyword_hits, vector_hits, k=60)
        elif search_mode == "vector" and vector_hits:
            merged = sorted(vector_hits, key=lambda h: h["score"], reverse=True)
        else:
            merged = sorted(keyword_hits, key=lambda h: h["score"], reverse=True)

        # build response
        hits: list[MemorySearchHit] = []
        for item in merged[:top_k]:
            row = item["row"]
            hits.append(MemorySearchHit(
                entry=_orm_to_out(row),
                score=item["score"],
                match_type=item["match_type"],
                layer_weight=item["layer_weight"],
            ))

        took_ms = int((time.monotonic() - t0) * 1000)
        return MemorySearchResponse(hits=hits, total=len(hits), took_ms=took_ms)

    # ── SOP 模板 ────────────────────────────────────────────

    async def create_sop_template(
        self,
        tenant_id: int,
        position_name: str,
        sop_steps: list[str],
        position_id: int | None = None,
        knowledge_doc_ids: list[str] | None = None,
        applicable_departments: list[int] | None = None,
    ) -> PositionSOPTemplateOut:
        async with _committed_session() as session:
            row = PositionSOPTemplateORM(
                tenant_id=tenant_id,
                position_name=position_name,
                position_id=position_id,
                sop_steps=sop_steps,
                knowledge_doc_ids=knowledge_doc_ids or [],
                applicable_departments=applicable_departments or [],
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return _sorm_to_out(row)

    async def list_sop_templates(
        self,
        tenant_id: int,
        position_id: int | None = None,
    ) -> list[PositionSOPTemplateOut]:
        async with _committed_session() as session:
            q = select(PositionSOPTemplateORM).where(PositionSOPTemplateORM.tenant_id == tenant_id)
            if position_id is not None:
                q = q.where(PositionSOPTemplateORM.position_id == position_id)
            rows = (await session.execute(q.order_by(PositionSOPTemplateORM.created_at.desc()))).scalars().all()
            return [_sorm_to_out(r) for r in rows]

    async def get_sop_template(self, tenant_id: int, template_id: int) -> PositionSOPTemplateOut | None:
        async with _committed_session() as session:
            row = (
                await session.execute(
                    select(PositionSOPTemplateORM).where(
                        PositionSOPTemplateORM.tenant_id == tenant_id,
                        PositionSOPTemplateORM.id == template_id,
                    )
                )
            ).scalar_one_or_none()
            return _sorm_to_out(row) if row else None

    async def update_sop_template(
        self,
        tenant_id: int,
        template_id: int,
        sop_steps: list[str] | None = None,
        knowledge_doc_ids: list[str] | None = None,
        applicable_departments: list[int] | None = None,
    ) -> PositionSOPTemplateOut | None:
        async with _committed_session() as session:
            row = (
                await session.execute(
                    select(PositionSOPTemplateORM).where(
                        PositionSOPTemplateORM.tenant_id == tenant_id,
                        PositionSOPTemplateORM.id == template_id,
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return None
            if sop_steps is not None:
                row.sop_steps = sop_steps
            if knowledge_doc_ids is not None:
                row.knowledge_doc_ids = knowledge_doc_ids
            if applicable_departments is not None:
                row.applicable_departments = applicable_departments
            row.version += 1
            await session.flush()
            await session.refresh(row)
            return _sorm_to_out(row)

    # ── 岗位知识查询 ────────────────────────────────────────

    async def query_position_knowledge(
        self,
        tenant_id: int,
        user_id: int,
        position_id: int,
        question: str,
    ) -> dict:
        # 1. 查 SOP 模板
        templates = await self.list_sop_templates(tenant_id, position_id=position_id)
        sop_steps = []
        if templates:
            sop_steps = templates[0].sop_steps

        # 2. 检索 position 级记忆
        pos_search = await self.search_memories(
            tenant_id=tenant_id,
            query=question,
            user_id=user_id,
            layers=[MemoryLayer.POSITION],
            position_id=position_id,
            top_k=5,
        )

        # 3. 检索 enterprise 级红线
        redline_search = await self.search_memories(
            tenant_id=tenant_id,
            query=question,
            user_id=user_id,
            layers=[MemoryLayer.ENTERPRISE],
            top_k=5,
        )
        # 只保留 redline tag 的
        redlines = [h.entry for h in redline_search.hits if "redline" in h.entry.tags]

        return {
            "sop_steps": sop_steps,
            "position_memories": [h.entry for h in pos_search.hits],
            "enterprise_redlines": redlines,
            "ai_answer": "",  # LLM 生成由 router 层调用
            "sources": [],
        }

    # ── 自动捕获 ────────────────────────────────────────────

    async def get_capture_config(self, tenant_id: int) -> dict:
        async with _committed_session() as session:
            row = (
                await session.execute(
                    select(AutoCaptureConfigORM).where(AutoCaptureConfigORM.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()
            if not row:
                return {"enabled": True, "capture_after_turns": 5, "auto_archive_to_department": False, "exclude_patterns": []}
            return {
                "enabled": row.enabled,
                "capture_after_turns": row.capture_after_turns,
                "auto_archive_to_department": row.auto_archive_to_department,
                "exclude_patterns": row.exclude_patterns or [],
            }

    async def update_capture_config(self, tenant_id: int, **kwargs) -> dict:
        async with _committed_session() as session:
            row = (
                await session.execute(
                    select(AutoCaptureConfigORM).where(AutoCaptureConfigORM.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()
            if not row:
                row = AutoCaptureConfigORM(tenant_id=tenant_id)
                session.add(row)
            for k, v in kwargs.items():
                if v is not None and hasattr(row, k):
                    setattr(row, k, v)
            await session.flush()
            return {
                "enabled": row.enabled,
                "capture_after_turns": row.capture_after_turns,
                "auto_archive_to_department": row.auto_archive_to_department,
                "exclude_patterns": row.exclude_patterns or [],
            }

    async def create_pending_capture(
        self,
        tenant_id: int,
        user_id: int,
        session_id: str,
        summary: str,
        knowledge_points: list[str],
        suggested_layer: str = "personal",
        suggested_tags: list[str] | None = None,
        confidence: float = 0.0,
    ) -> dict:
        async with _committed_session() as session:
            row = AutoCapturePendingORM(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                summary=summary,
                knowledge_points=knowledge_points,
                suggested_layer=suggested_layer,
                suggested_tags=suggested_tags or [],
                confidence=confidence,
                status="pending",
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return {
                "id": row.id,
                "capture_uuid": row.capture_uuid,
                "status": "pending",
                "summary": summary,
            }

    async def list_pending_captures(self, tenant_id: int, user_id: int | None = None) -> list[dict]:
        async with _committed_session() as session:
            q = select(AutoCapturePendingORM).where(
                AutoCapturePendingORM.tenant_id == tenant_id,
                AutoCapturePendingORM.status == "pending",
            )
            if user_id is not None:
                q = q.where(AutoCapturePendingORM.user_id == user_id)
            rows = (await session.execute(q.order_by(AutoCapturePendingORM.created_at.desc()))).scalars().all()
            return [
                {
                    "id": r.id,
                    "capture_uuid": r.capture_uuid,
                    "user_id": r.user_id,
                    "session_id": r.session_id,
                    "summary": r.summary,
                    "knowledge_points": r.knowledge_points or [],
                    "suggested_layer": r.suggested_layer,
                    "suggested_tags": r.suggested_tags or [],
                    "confidence": r.confidence,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    async def approve_capture(self, tenant_id: int, capture_id: int, reviewer_id: int = 0) -> MemoryEntryOut | None:
        async with _committed_session() as session:
            row = (
                await session.execute(
                    select(AutoCapturePendingORM).where(
                        AutoCapturePendingORM.tenant_id == tenant_id,
                        AutoCapturePendingORM.id == capture_id,
                        AutoCapturePendingORM.status == "pending",
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return None
            row.status = "approved"
            row.reviewed_at = datetime.now(timezone.utc)
            await session.flush()

        # create memory from capture
        layer = MemoryLayer(row.suggested_layer) if row.suggested_layer in [lyr.value for lyr in MemoryLayer] else MemoryLayer.PERSONAL
        return await self.create_memory(
            tenant_id=tenant_id,
            layer=layer,
            content=row.summary,
            creator_id=row.user_id,
            tags=(row.suggested_tags or []) + ["auto_capture"],
            source_type="auto_capture",
            source_session_id=row.session_id,
        )

    async def reject_capture(self, tenant_id: int, capture_id: int) -> bool:
        async with _committed_session() as session:
            row = (
                await session.execute(
                    select(AutoCapturePendingORM).where(
                        AutoCapturePendingORM.tenant_id == tenant_id,
                        AutoCapturePendingORM.id == capture_id,
                        AutoCapturePendingORM.status == "pending",
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return False
            row.status = "rejected"
            row.reviewed_at = datetime.now(timezone.utc)
            await session.flush()
            return True

    # ── 记忆迁移 ────────────────────────────────────────────

    async def migrate_memories(
        self,
        tenant_id: int,
        source_user_id: int,
        target_user_id: int,
        scope: str = "personal",
    ) -> dict:
        migrated = 0
        async with _committed_session() as session:
            q = select(MemoryORM).where(
                MemoryORM.tenant_id == tenant_id,
                MemoryORM.creator_id == source_user_id,
                MemoryORM.is_deleted == False,
            )
            if scope == "personal":
                q = q.where(MemoryORM.layer == MemoryLayer.PERSONAL.value)
            elif scope == "position":
                q = q.where(MemoryORM.layer.in_([MemoryLayer.PERSONAL.value, MemoryLayer.POSITION.value]))

            rows = (await session.execute(q)).scalars().all()
            for row in rows:
                new_row = MemoryORM(
                    tenant_id=tenant_id,
                    memory_uuid=str(uuid.uuid4()),
                    layer=row.layer,
                    content=row.content,
                    summary=row.summary,
                    creator_id=target_user_id,
                    department_id=row.department_id,
                    position_id=row.position_id,
                    tags=row.tags,
                    source_type="migrated",
                    source_session_id=row.source_session_id,
                )
                session.add(new_row)
                migrated += 1
            await session.flush()
        return {"migrated": migrated, "skipped": 0}

    # ── 离职清除 ────────────────────────────────────────────

    async def soft_delete_user_memories(self, tenant_id: int, user_id: int) -> int:
        async with _committed_session() as session:
            result = await session.execute(
                update(MemoryORM)
                .where(
                    MemoryORM.tenant_id == tenant_id,
                    MemoryORM.creator_id == user_id,
                    MemoryORM.layer == MemoryLayer.PERSONAL.value,
                    MemoryORM.is_deleted == False,
                )
                .values(is_deleted=True, deleted_at=datetime.now(timezone.utc))
            )
            return result.rowcount

    async def physical_delete_expired(self, tenant_id: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=PHYSICAL_DELETE_DAYS)
        async with _committed_session() as session:
            rows = (
                await session.execute(
                    select(MemoryORM).where(
                        MemoryORM.tenant_id == tenant_id,
                        MemoryORM.is_deleted == True,
                        MemoryORM.deleted_at < cutoff,
                    )
                )
            ).scalars().all()
            for row in rows:
                await session.delete(row)
            return len(rows)

    # ── 统计 ────────────────────────────────────────────────

    async def get_stats(self, tenant_id: int) -> dict:
        async with _committed_session() as session:
            total = (await session.execute(
                select(func.count()).where(
                    MemoryORM.tenant_id == tenant_id,
                    MemoryORM.is_deleted == False,
                )
            )).scalar() or 0

            by_layer = {}
            for layer in MemoryLayer:
                cnt = (await session.execute(
                    select(func.count()).where(
                        MemoryORM.tenant_id == tenant_id,
                        MemoryORM.layer == layer.value,
                        MemoryORM.is_deleted == False,
                    )
                )).scalar() or 0
                by_layer[layer.value] = cnt

            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            auto_today = (await session.execute(
                select(func.count()).where(
                    MemoryORM.tenant_id == tenant_id,
                    MemoryORM.source_type == "auto_capture",
                    MemoryORM.created_at >= today_start,
                )
            )).scalar() or 0

            distill_cnt = (await session.execute(
                select(func.count()).where(
                    MemoryORM.tenant_id == tenant_id,
                    MemoryORM.source_type == "distill",
                )
            )).scalar() or 0

            sop_cnt = (await session.execute(
                select(func.count()).where(PositionSOPTemplateORM.tenant_id == tenant_id)
            )).scalar() or 0

            return {
                "total_entries": total,
                "by_layer": by_layer,
                "auto_captured_today": auto_today,
                "distill_count": distill_cnt,
                "sop_template_count": sop_cnt,
            }


__all__ = ["MemoryService"]
