"""Skills / knowledge / cron API endpoints (PRD §7.2.6, 7.2.7, 7.2.8).

2026-08-11 兼容修复：ECS 生产库缺 Skill/KnowledgeNote/CronJob ORM 模型（四库合并遗留），
改为 SQLAlchemy Table 直连既有表；用户依赖改用 current_user。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Boolean, Column, DateTime, MetaData, String, Table, Text, select

from core.api_response import ok
from core.auth.jwt import current_user
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["skills"])

# ---- 表直连（表已存在；ORM 模型在四库合并时丢失，不重建避免冲突） ----
_skills_table = Table(
    "skills",
    MetaData(),
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("tenant_id", BigInteger),
    Column("name", String(128)),
    Column("canonical_id", BigInteger),
    Column("trigger", String(255)),
    Column("content", Text),
    Column("embedding_hash", String(64)),
    Column("is_soft_link", Boolean),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

_notes_table = Table(
    "knowledge_notes",
    MetaData(),
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("tenant_id", BigInteger),
    Column("title", String(255)),
    Column("tags", Text),
    Column("file_path", String(512)),
    Column("summary", Text),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

_cron_table = Table(
    "cron_jobs",
    MetaData(),
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("tenant_id", BigInteger),
    Column("name", String(128)),
    Column("schedule", String(64)),
    Column("handler", String(255)),
    Column("args", Text),
    Column("enabled", Boolean),
    Column("last_run_at", DateTime),
    Column("last_status", String(32)),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)


def _tenant_of(claims: dict) -> Optional[int]:
    return claims.get("tenant_id")


# --------------------------------------------------------------------------- #
# Skills
# --------------------------------------------------------------------------- #


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    content: str = Field(..., min_length=1)
    trigger: str | None = None


@router.get("/skills")
async def list_skills_endpoint(claims: dict = Depends(current_user)) -> Any:
    tenant_id = _tenant_of(claims)
    async with session_scope() as session, bypass_tenant_filter():
        stmt = select(_skills_table).where(_skills_table.c.tenant_id == tenant_id).order_by(_skills_table.c.id.desc()).limit(200)
        rows = (await session.execute(stmt)).all()
    return ok([{"id": r.id, "name": r.name, "trigger": r.trigger, "is_soft_link": bool(r.is_soft_link)} for r in rows])


@router.post("/skills")
async def create_skill(
    request: Request, response: Response, payload: SkillCreate,
    claims: dict = Depends(current_user),
) -> Any:
    # P3 数据同步授权校验 + P4 捎带响应头：旧码超 7 天倒计时 → 拒绝同步
    from core.utils.license_broker import state_response_headers
    from core.utils.license_state import check_sync_allowed

    sync_allowed, sync_reason = check_sync_allowed(
        request.headers.get("X-DDW-License-Key")
    )
    _state_headers = state_response_headers()
    if not sync_allowed:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=403,
            content={"detail": sync_reason},
            headers=_state_headers,
        )
    response.headers.update(_state_headers)

    tenant_id = _tenant_of(claims)
    now = datetime.utcnow()
    async with session_scope() as session, bypass_tenant_filter():
        # 表 id 非自增（四库合并遗留），显式取 max+1
        max_id = (await session.execute(select(_skills_table.c.id).order_by(_skills_table.c.id.desc()).limit(1))).scalar() or 0
        ins = _skills_table.insert().values(
            id=max_id + 1, tenant_id=tenant_id, name=payload.name, trigger=payload.trigger,
            content=payload.content, is_soft_link=False, created_at=now, updated_at=now,
        )
        await session.execute(ins)
        await session.commit()
        skill_id = max_id + 1
    return ok({"id": skill_id, "name": payload.name, "is_soft_link": False})


# --------------------------------------------------------------------------- #
# Knowledge notes
# --------------------------------------------------------------------------- #


class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    summary: str | None = None
    tags: List[str] | None = None
    file_path: str | None = None


@router.get("/knowledge")
async def list_notes(claims: dict = Depends(current_user)) -> Any:
    tenant_id = _tenant_of(claims)
    async with session_scope() as session, bypass_tenant_filter():
        stmt = select(_notes_table).where(_notes_table.c.tenant_id == tenant_id).order_by(_notes_table.c.id.desc()).limit(200)
        rows = (await session.execute(stmt)).all()
    return ok([{"id": n.id, "title": n.title, "summary": n.summary} for n in rows])


@router.post("/knowledge")
async def create_note(
    request: Request, response: Response, payload: NoteCreate,
    claims: dict = Depends(current_user),
) -> Any:
    # P3 数据同步授权校验 + P4 捎带响应头：旧码超 7 天倒计时 → 拒绝同步
    from core.utils.license_broker import state_response_headers
    from core.utils.license_state import check_sync_allowed

    sync_allowed, sync_reason = check_sync_allowed(
        request.headers.get("X-DDW-License-Key")
    )
    _state_headers = state_response_headers()
    if not sync_allowed:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=403,
            content={"detail": sync_reason},
            headers=_state_headers,
        )
    response.headers.update(_state_headers)

    tenant_id = _tenant_of(claims)
    now = datetime.utcnow()
    import json as _json
    async with session_scope() as session, bypass_tenant_filter():
        max_id = (await session.execute(select(_notes_table.c.id).order_by(_notes_table.c.id.desc()).limit(1))).scalar() or 0
        ins = _notes_table.insert().values(
            id=max_id + 1, tenant_id=tenant_id, title=payload.title, summary=payload.summary,
            tags=_json.dumps({"tags": payload.tags or []}, ensure_ascii=False),
            file_path=payload.file_path, created_at=now, updated_at=now,
        )
        await session.execute(ins)
        await session.commit()
        note_id = max_id + 1
    return ok({"id": note_id})


# --------------------------------------------------------------------------- #
# Cron jobs
# --------------------------------------------------------------------------- #


class CronCreate(BaseModel):
    name: str
    schedule: str = Field(..., description="cron expression")
    handler: str
    args: dict | None = None


@router.get("/cron")
async def list_cron(claims: dict = Depends(current_user)) -> Any:
    async with session_scope() as session, bypass_tenant_filter():
        rows = (await session.execute(select(_cron_table))).all()
    return ok([{"id": c.id, "name": c.name, "schedule": c.schedule, "handler": c.handler, "enabled": bool(c.enabled)} for c in rows])


@router.post("/cron")
async def create_cron(payload: CronCreate, claims: dict = Depends(current_user)) -> Any:
    tenant_id = _tenant_of(claims)
    now = datetime.utcnow()
    import json as _json
    async with session_scope() as session, bypass_tenant_filter():
        max_id = (await session.execute(select(_cron_table.c.id).order_by(_cron_table.c.id.desc()).limit(1))).scalar() or 0
        ins = _cron_table.insert().values(
            id=max_id + 1, tenant_id=tenant_id, name=payload.name, schedule=payload.schedule,
            handler=payload.handler, args=_json.dumps(payload.args or {}, ensure_ascii=False),
            enabled=True, created_at=now, updated_at=now,
        )
        await session.execute(ins)
        await session.commit()
        cron_id = max_id + 1
    return ok({"id": cron_id})
