"""User-to-user direct messages API (PRD §7.2.5)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.api_response import ok
from core.database.factory import get_engine_factory
from core.database.models import DirectMessage
from core.middleware.tenant import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messages", tags=["messages"])


class SendRequest(BaseModel):
    to_user_id: int
    content: str = Field(..., min_length=1, max_length=8000)


@router.post("/")
async def send(payload: SendRequest, claims=Depends(require_user)) -> Any:
    from_user_id = int(claims["sub"])
    tenant_id = claims.get("tenant_id")
    factory = get_engine_factory()
    async with factory.session("main") as session:
        msg = DirectMessage(from_user_id=from_user_id, to_user_id=payload.to_user_id, content=payload.content, tenant_id=tenant_id)
        session.add(msg)
        await session.flush()
        return ok({"id": msg.id, "created_at": msg.created_at.isoformat()})


@router.get("/inbox")
async def inbox(claims=Depends(require_user)) -> Any:
    user_id = int(claims["sub"])
    factory = get_engine_factory()
    async with factory.session("main") as session:
        rows = (await session.scalars(select(DirectMessage).where(DirectMessage.to_user_id == user_id).order_by(DirectMessage.created_at.desc()).limit(100))).all()
    return ok([{"id": m.id, "from": m.from_user_id, "content": m.content, "read_at": m.read_at.isoformat() if m.read_at else None, "created_at": m.created_at.isoformat()} for m in rows])


@router.post("/{message_id}/read")
async def mark_read(message_id: int, claims=Depends(require_user)) -> Any:
    user_id = int(claims["sub"])
    factory = get_engine_factory()
    async with factory.session("main") as session:
        msg = await session.get(DirectMessage, message_id)
        if msg is None or msg.to_user_id != user_id:
            raise HTTPException(status_code=404, detail="not found")
        from datetime import datetime

        msg.read_at = datetime.utcnow()
    return ok({"id": message_id, "read": True})
