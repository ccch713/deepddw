"""DDW Followup - FastAPI router."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from .models import (
    CHANNELS,
    FOLLOWUP_TYPES,
    STATUSES,
    FollowupTask,
    FollowupTaskCreate,
    FollowupTaskUpdate,
    FollowupTemplate,
    FollowupTemplateCreate,
    HealthResponse,
    StatsByType,
    StatsResponse,
    TaskList,
    TemplateList,
)
from .store import FollowupStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plugins/ddw_followup", tags=["ddw_followup"])
_store: FollowupStore | None = None


def set_store(s: FollowupStore) -> None:
    global _store
    _store = s


def _ensure() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if _store is None:
        return HealthResponse()
    return HealthResponse(total_tasks=_store.total_tasks())


@router.post("/tasks", response_model=FollowupTask, status_code=201)
async def create_task(req: FollowupTaskCreate) -> FollowupTask:
    _ensure()
    if req.followup_type not in FOLLOWUP_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid followup_type: {req.followup_type}")
    if req.channel not in CHANNELS:
        raise HTTPException(status_code=400, detail=f"invalid channel: {req.channel}")
    d = _store.create_task(req.model_dump())
    return FollowupTask(**d)


@router.get("/tasks", response_model=TaskList)
async def list_tasks(status: Optional[str] = None) -> TaskList:
    _ensure()
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {status}")
    rows = _store.list_tasks(status=status)
    return TaskList(total=len(rows), tasks=rows)


@router.patch("/tasks/{task_id}", response_model=FollowupTask)
async def update_task(task_id: str, req: FollowupTaskUpdate) -> FollowupTask:
    _ensure()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "status" in updates and updates["status"] not in STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {updates['status']}")
    if updates.get("status") == "sent" and "sent_at" not in updates:
        updates["sent_at"] = datetime.now(timezone.utc).isoformat()
    t = _store.update_task(task_id, updates)
    if t is None:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
    return FollowupTask(**t)


@router.get("/templates", response_model=TemplateList)
async def list_templates() -> TemplateList:
    _ensure()
    rows = _store.list_templates()
    return TemplateList(total=len(rows), templates=rows)


@router.post("/templates", response_model=FollowupTemplate, status_code=201)
async def create_template(req: FollowupTemplateCreate) -> FollowupTemplate:
    _ensure()
    if req.followup_type not in FOLLOWUP_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid followup_type: {req.followup_type}")
    d = _store.create_template(req.model_dump())
    return FollowupTemplate(**d)


@router.get("/stats", response_model=StatsResponse)
async def stats(period: str) -> StatsResponse:
    _ensure()
    s = _store.stats(period)
    by_type = {k: StatsByType(**v) for k, v in s["by_type"].items()}
    return StatsResponse(
        period=s["period"],
        total_tasks=s["total_tasks"],
        sent=s["sent"],
        responded=s["responded"],
        response_rate=s["response_rate"],
        by_type=by_type,
    )
