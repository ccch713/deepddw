"""SaaS 管理后台端点（DDW AI Hub v5.4 — 模块 B5 + 补充 C 知识库权限）。

端点：
- ``GET    /api/v1/admin/overview``     用量概览
- ``GET    /api/v1/admin/users``        用户列表
- ``POST   /api/v1/admin/users/invite`` 邀请用户
- ``DELETE /api/v1/admin/users/{id}``   移除用户
- ``GET    /api/v1/admin/apikeys``      Key 列表
- ``POST   /api/v1/admin/apikeys``      创建 Key
- ``DELETE /api/v1/admin/apikeys/{id}`` 删除 Key
- ``GET    /api/v1/admin/billing``      套餐信息
- ``POST   /api/v1/admin/billing/upgrade`` 升级套餐
- 知识库权限（补充 C）：
  - ``GET    /api/v1/knowledge/bases``
  - ``POST   /api/v1/knowledge/bases``
  - ``GET    /api/v1/knowledge/bases/{id}/permissions``
  - ``PUT    /api/v1/knowledge/bases/{id}/permissions``
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from core.auth.jwt import current_admin
from core.config import get_settings
from core.database.models import ApiKey, ChannelPartner, Tenant, User
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from core.plugin_manager.manager import get_plugin_manager
from core.services import tenant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InviteUserReq(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    name: Optional[str] = Field(None, max_length=120)
    role: str = Field("member", pattern="^(owner|admin|member)$")


class CreateApiKeyReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class UpgradeReq(BaseModel):
    plan: str = Field(..., pattern="^(free|standard|enterprise)$")


# ---------------------------------------------------------------------------
# 概览
# ---------------------------------------------------------------------------


@router.get("/overview", response_model=Dict[str, Any])
async def overview(user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        usage = await tenant_service.get_tenant_usage(session, user["tenant_id"])
        # 7 天 daily 用量（mock：均匀分布）
        today = datetime.utcnow().date()
        trend = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            trend.append({"date": d.isoformat(), "tokens": int(usage["tokens_used"] * (0.1 + 0.05 * (i % 3)))})
        return {
            "tenant_id": user["tenant_id"],
            "user": usage["user_count"],
            "api_key_count": usage["api_key_count"],
            "tokens_used": usage["tokens_used"],
            "token_limit": usage["token_limit"],
            "trend_7d": trend,
            "plugin_ranking": [
                {"name": "ddw-llm-gateway", "calls": 1234},
                {"name": "ddw-training", "calls": 312},
                {"name": "ddw-token-manager", "calls": 256},
            ],
        }


@router.get("/llm/usage", response_model=Dict[str, Any])
async def llm_usage(
    days: int = Query(7, ge=1, le=90),
    user: Dict[str, Any] = Depends(current_admin),
) -> Dict[str, Any]:
    """LLM 网关真实消耗统计（llm_usage_records 表）— 汇总 + 按 provider 分组 + 最近 20 条。"""
    import sqlite3 as _sq

    from core.llm_gateway.usage import UsageTracker

    path = UsageTracker._main_db_path()
    if not path:
        return {"days": days, "error": "main db is not sqlite"}
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    con = _sq.connect(path, timeout=5)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0), COALESCE(SUM(cost),0) "
            "FROM llm_usage_records WHERE created_at >= ?",
            (since,),
        )
        total = cur.fetchone()
        cur.execute(
            "SELECT provider, model, COUNT(*), COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0), COALESCE(SUM(cost),0) "
            "FROM llm_usage_records WHERE created_at >= ? GROUP BY provider, model ORDER BY 6 DESC",
            (since,),
        )
        by_provider = [
            {"provider": r[0], "model": r[1], "calls": r[2], "tokens_in": r[3], "tokens_out": r[4], "cost": round(r[5], 6)}
            for r in cur.fetchall()
        ]
        cur.execute(
            "SELECT provider, model, tokens_in, tokens_out, cost, latency_ms, rule, ok, created_at "
            "FROM llm_usage_records ORDER BY rowid DESC LIMIT 20",
        )
        recent = [
            {"provider": r[0], "model": r[1], "tokens_in": r[2], "tokens_out": r[3], "cost": round(r[4], 6),
             "latency_ms": r[5], "rule": r[6], "ok": r[7], "created_at": r[8]}
            for r in cur.fetchall()
        ]
    finally:
        con.close()
    return {
        "days": days,
        "total": {"calls": total[0], "tokens_in": total[1], "tokens_out": total[2], "cost": round(total[3], 6)},
        "by_provider": by_provider,
        "recent": recent,
    }


# ---------------------------------------------------------------------------
# 用户
# ---------------------------------------------------------------------------


@router.get("/users", response_model=Dict[str, Any])
async def list_users(
    user: Dict[str, Any] = Depends(current_admin),
    page: int = 1,
    size: int = 20,
) -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        # 总数
        total = await session.scalar(
            select(func.count(User.id)).where(User.tenant_id == user["tenant_id"])
        ) or 0
        # 分页查询
        offset = (max(page, 1) - 1) * size
        rows = (
            await session.execute(
                select(User)
                .where(User.tenant_id == user["tenant_id"])
                .order_by(User.id)
                .offset(offset)
                .limit(size)
            )
        ).scalars().all()
        return {
            "total": total,
            "page": page,
            "size": size,
            "items": [
                {
                    "id": u.id,
                    "phone": u.phone,
                    "name": u.name,
                    "role": u.role,
                    "status": u.status,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                }
                for u in rows
            ],
        }


@router.post("/users/invite", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def invite_user(req: InviteUserReq, user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        # 用户数限制
        cnt = await session.scalar(select(func.count(User.id)).where(User.tenant_id == user["tenant_id"])) or 0
        tenant = (await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]))).scalar_one()
        plans = get_settings().saas_plans
        limit = plans.get(tenant.plan, {}).get("user_limit", 5)
        if cnt >= limit:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"已达套餐用户上限 {limit}")
        # 检查重复
        if (await session.execute(select(User).where(User.phone == req.phone))).scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该手机号已注册")
        u = User(tenant_id=user["tenant_id"], phone=req.phone, name=req.name, role=req.role, status="invited")
        session.add(u)
        await session.commit()
        await session.refresh(u)
        return {"id": u.id, "phone": u.phone, "name": u.name, "role": u.role, "status": u.status}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user(user_id: int, user: Dict[str, Any] = Depends(current_admin)):
    async with session_scope() as session, bypass_tenant_filter():
        u = (await session.execute(select(User).where(User.id == user_id, User.tenant_id == user["tenant_id"]))).scalar_one_or_none()
        if u is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        if u.role == "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无法删除 owner")
        await session.delete(u)
        await session.commit()


# ---------------------------------------------------------------------------
# API Key
# ---------------------------------------------------------------------------


@router.get("/apikeys", response_model=List[Dict[str, Any]])
async def list_apikeys(user: Dict[str, Any] = Depends(current_admin)) -> List[Dict[str, Any]]:
    async with session_scope() as session, bypass_tenant_filter():
        rows = (await session.execute(select(ApiKey).where(ApiKey.tenant_id == user["tenant_id"]))).scalars().all()
        return [
            {
                "id": k.id,
                "name": k.name,
                "key_prefix": k.key_prefix,
                "status": k.status,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
            }
            for k in rows
        ]


@router.post("/apikeys", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_apikey(req: CreateApiKeyReq, user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    raw_key = "ddw_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    prefix = raw_key[:12]
    async with session_scope() as session, bypass_tenant_filter():
        k = ApiKey(tenant_id=user["tenant_id"], name=req.name, key_prefix=prefix, key_hash=key_hash, status="active")
        session.add(k)
        await session.commit()
        await session.refresh(k)
        return {
            "id": k.id,
            "name": k.name,
            "key_prefix": prefix,
            "raw_key": raw_key,  # 仅创建时返回一次
            "status": k.status,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }


@router.delete("/apikeys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_apikey(key_id: int, user: Dict[str, Any] = Depends(current_admin)):
    async with session_scope() as session, bypass_tenant_filter():
        k = (await session.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == user["tenant_id"]))).scalar_one_or_none()
        if k is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key 不存在")
        await session.delete(k)
        await session.commit()


# ---------------------------------------------------------------------------
# 计费 / 套餐
# ---------------------------------------------------------------------------


@router.get("/billing", response_model=Dict[str, Any])
async def billing(user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        t = (await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]))).scalar_one()
        usage = await tenant_service.get_tenant_usage(session, t.id)
        plans = get_settings().saas_plans
        current = plans.get(t.plan, plans["free"])
        return {
            "plan": t.plan,
            "plan_name": current.get("name", t.plan),
            "price_cny": current.get("price_cny", 0),
            "user_limit": current.get("user_limit", 5),
            "features": current.get("features", []),
            "tokens_used": usage["tokens_used"],
            "token_limit": usage["token_limit"],
            "usage_ratio": (usage["tokens_used"] / usage["token_limit"]) if usage["token_limit"] else 0,
            "available_plans": [{"id": k, **v} for k, v in plans.items()],
        }


@router.post("/billing/upgrade", response_model=Dict[str, Any])
async def upgrade(req: UpgradeReq, user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    async with session_scope() as session, bypass_tenant_filter():
        try:
            t = await tenant_service.upgrade_plan(session, user["tenant_id"], req.plan)
        except tenant_service.TenantNotFound as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except tenant_service.PlanNotAllowed as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        await session.commit()
        return {"id": t.id, "plan": t.plan}


# ---------------------------------------------------------------------------
# 插件管理（前端 admin.html 插件管理频道）
# ---------------------------------------------------------------------------


@router.get("/plugins", response_model=Dict[str, Any])
async def list_plugins(user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """插件列表。"""
    try:
        pm = get_plugin_manager()
        manifests = pm.list() if hasattr(pm, "list") else []
        items = []
        for m in manifests:
            items.append(
                {
                    "name": getattr(m, "name", ""),
                    "version": getattr(m, "version", ""),
                    "isolation": getattr(m, "isolation", ""),
                    "enabled": getattr(m, "enabled", True),
                    "description": getattr(m, "description", ""),
                }
            )
        return {"items": items, "total": len(items)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_plugins failed: %s", exc)
        return {"items": [], "total": 0, "error": str(exc)}


@router.post("/plugins/{name}/enable", response_model=Dict[str, Any])
async def enable_plugin(name: str, user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """启用插件。"""
    pm = get_plugin_manager()
    enable = getattr(pm, "enable", None)
    if enable:
        await enable(name)
    return {"name": name, "enabled": True}


@router.post("/plugins/{name}/disable", response_model=Dict[str, Any])
async def disable_plugin(name: str, user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """停用插件。"""
    pm = get_plugin_manager()
    disable = getattr(pm, "disable", None)
    if disable:
        await disable(name)
    return {"name": name, "enabled": False}


# ---------------------------------------------------------------------------
# 渠道商管理（前端 admin.html 渠道商频道）
# ---------------------------------------------------------------------------


class ChannelCreateReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    level: str = Field("small", pattern="^(big|small)$")
    parent_id: Optional[int] = None
    contact: Optional[str] = Field(None, max_length=255)


@router.get("/billing/channels", response_model=Dict[str, Any])
async def list_channels(user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """渠道商列表。"""
    async with session_scope() as session, bypass_tenant_filter():
        rows = (await session.scalars(select(ChannelPartner).order_by(ChannelPartner.id))).all()
    return {
        "items": [
            {
                "id": c.id,
                "name": c.name,
                "level": c.level,
                "parent_id": c.parent_id,
                "contact": c.contact,
                "commission_balance_cny": c.commission_balance_cny,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in rows
        ],
        "total": len(rows),
    }


@router.post("/billing/channels", response_model=Dict[str, Any])
async def create_channel(
    req: ChannelCreateReq, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    """新增渠道商。"""
    async with session_scope() as session, bypass_tenant_filter():
        channel = ChannelPartner(
            name=req.name,
            level=req.level,
            parent_id=req.parent_id,
            contact=req.contact,
        )
        session.add(channel)
        await session.flush()
        return {"id": channel.id, "name": channel.name}


__all__ = ["router"]
