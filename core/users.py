"""用户管理 API（/users）— 用户列表 + 白名单。

前端 admin.html 频道依赖：
- GET  /users/                用户列表（require_admin）
- GET  /users/whitelist       白名单列表
- POST /users/whitelist       新增白名单
- DELETE /users/whitelist/{phone}  删除白名单
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.auth.jwt import current_admin
from core.database.models import User, WhitelistEntry
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


class WhitelistRequest(BaseModel):
    phone: str = Field(..., min_length=4, max_length=20)
    note: Optional[str] = None


@router.get("/", response_model=Dict[str, Any])
async def list_users(claims: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """用户列表（管理后台用户管理频道）。"""
    async with session_scope() as session, bypass_tenant_filter():
        rows = (await session.scalars(select(User).order_by(User.id))).all()
    return {
        "items": [
            {
                "id": u.id,
                "phone": u.phone,
                "name": u.name,
                "role": u.role,
                "status": u.status,
                "tenant_id": u.tenant_id,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in rows
        ],
        "total": len(rows),
    }


@router.get("/whitelist", response_model=Dict[str, Any])
async def list_whitelist(claims: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """白名单列表。"""
    async with session_scope() as session, bypass_tenant_filter():
        rows = (await session.scalars(select(WhitelistEntry).order_by(WhitelistEntry.id))).all()
    return {
        "items": [
            {
                "id": w.id,
                "phone": w.phone,
                "note": w.note,
                "tenant_id": w.tenant_id,
                "created_at": w.created_at.isoformat() if w.created_at else None,
            }
            for w in rows
        ],
        "total": len(rows),
    }


@router.post("/whitelist", response_model=Dict[str, Any])
async def add_whitelist(
    payload: WhitelistRequest, claims: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    """新增白名单。"""
    tenant_id = claims.get("tenant_id")
    async with session_scope() as session, bypass_tenant_filter():
        existing = (
            await session.scalars(
                select(WhitelistEntry).where(
                    WhitelistEntry.phone == payload.phone,
                    WhitelistEntry.tenant_id == tenant_id,
                )
            )
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="该手机号已在白名单中")
        entry = WhitelistEntry(
            phone=payload.phone,
            note=payload.note,
            tenant_id=tenant_id,
            added_by=claims.get("user_id"),
        )
        session.add(entry)
        await session.flush()
        return {"ok": True, "id": entry.id}


@router.delete("/whitelist/{phone}", response_model=Dict[str, Any])
async def delete_whitelist(
    phone: str, claims: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    """删除白名单。"""
    tenant_id = claims.get("tenant_id")
    async with session_scope() as session, bypass_tenant_filter():
        entry = (
            await session.scalars(
                select(WhitelistEntry).where(
                    WhitelistEntry.phone == phone,
                    WhitelistEntry.tenant_id == tenant_id,
                )
            )
        ).first()
        if entry is None:
            raise HTTPException(status_code=404, detail="白名单条目不存在")
        await session.delete(entry)
        await session.flush()
    return {"ok": True}
