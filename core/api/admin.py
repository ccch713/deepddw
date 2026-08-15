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

from fastapi import (
    APIRouter, Depends, File, HTTPException, Query,
    Request, UploadFile, status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from core.auth.jwt import current_admin
from core.config import get_settings
from core.database.models import (
    ApiKey,
    ChannelPartner,
    ForumThread,
    LicenseKey,
    LicensePluginChange,
    OnPremiseCustomer,
    PluginMarketItem,
    PluginMeta,
    Role,
    Tenant,
    User,
)
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
        return {
            "days": days, "total": {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost": 0},
            "by_provider": [], "recent": [],
            "cloud": {"tokens": 0, "cost_cny": 0, "providers": []},
            "selfhosted": {"tokens": 0, "saved_cny": 0, "providers": []},
        }
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
    except _sq.OperationalError:
        # 表不存在时返回空数据（测试 / 首次部署）
        total = (0, 0, 0, 0)
        by_provider = []
        recent = []
    finally:
        con.close()
    # 云端 / 自建 双轨分类
    _selfhosted = {"ollama"}
    cloud_tokens = 0
    cloud_cost = 0.0
    cloud_providers: set[str] = set()
    self_tokens = 0
    self_saved = 0.0
    self_providers: set[str] = set()
    for p in by_provider:
        prov = (p["provider"] or "").lower()
        total_tokens = p["tokens_in"] + p["tokens_out"]
        if prov in _selfhosted:
            self_tokens += total_tokens
            self_saved += p["cost"]
            self_providers.add(prov)
        else:
            cloud_tokens += total_tokens
            cloud_cost += p["cost"]
            cloud_providers.add(prov)

    return {
        "days": days,
        "total": {"calls": total[0], "tokens_in": total[1], "tokens_out": total[2], "cost": round(total[3], 6)},
        "by_provider": by_provider,
        "recent": recent,
        "cloud": {"tokens": cloud_tokens, "cost_cny": round(cloud_cost, 4), "providers": sorted(cloud_providers)},
        "selfhosted": {"tokens": self_tokens, "saved_cny": round(self_saved, 4), "providers": sorted(self_providers)},
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


@router.get("/plugins")
async def list_plugins(request: Request, user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """全部插件清单。返回 {items, total} 信封。

    - 扫描 plugins/*/manifest.yaml（与 load_plugins 一致）
    - installed = 已加载进 app.state.plugins（启动时 load_plugins 收集）
    - 联合 plugin_market_items + forum_threads 计数
    """
    from pathlib import Path

    try:
        import yaml as _yaml
    except Exception:  # noqa: BLE001
        _yaml = None

    # 已加载插件集合（main.py load_plugins 收集，key=插件目录名）
    loaded_plugins = getattr(request.app.state, "plugins", None) or {}

    # 批量读取市场元数据
    async with session_scope() as session, bypass_tenant_filter():
        market_items = (await session.scalars(select(PluginMarketItem))).all()
        market_map = {m.plugin_name: m for m in market_items}

        # 批量读取帖子计数
        thread_counts_raw = (await session.execute(
            select(ForumThread.plugin_name, func.count(ForumThread.id))
            .group_by(ForumThread.plugin_name)
        )).all()
        thread_map = {row[0]: row[1] for row in thread_counts_raw}

    plugins_dir = Path(__file__).resolve().parents[2] / "plugins"
    catalog = []
    if plugins_dir.is_dir():
        for manifest_path in sorted(plugins_dir.glob("*/manifest.yaml")):
            name = manifest_path.parent.name
            if name in {"_template", "embedded_llm"}:
                continue
            info: Dict[str, Any] = {
                "name": name, "version": "", "description": "",
                "installed": False, "enabled": False,
                "title": "", "category": "通用", "installs": 0,
                "stars": 0.0, "star_count": 0, "updated_at": "", "thread_count": 0,
            }
            if _yaml is not None:
                try:
                    m = _yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
                    info["version"] = str(m.get("version", "") or "")
                    info["description"] = str(m.get("description", "") or "")
                    info["tier"] = str(m.get("tier", "beta") or "beta")
                except Exception:  # noqa: BLE001
                    pass
            if name in loaded_plugins:
                info["installed"] = True
                info["enabled"] = True
            # 联合市场元数据
            mi = market_map.get(name)
            if mi:
                info["title"] = mi.title
                info["category"] = mi.category
                info["installs"] = mi.installs
                info["stars"] = mi.stars
                info["star_count"] = mi.star_count
                info["updated_at"] = mi.updated_at
            info["thread_count"] = thread_map.get(name, 0)
            catalog.append(info)
    return {"items": catalog, "total": len(catalog)}


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


@router.get("/billing/channels")
async def list_channels(user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """渠道商列表。返回 {items, total} 信封。"""
    async with session_scope() as session, bypass_tenant_filter():
        rows = (await session.scalars(select(ChannelPartner).order_by(ChannelPartner.id))).all()
    items = [
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
    ]
    return {"items": items, "total": len(items)}


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


# ---------------------------------------------------------------------------
# 用户管理改版（G 项）辅助
# ---------------------------------------------------------------------------

# 频道清单（前端侧边栏 + 角色权限勾选用）
ALL_CHANNELS = [
    "dashboard", "plugins", "users", "llm",
    "whitelist", "channels", "analytics", "docs",
    "marketplace", "forum",
]


def _last_active_label(last_login_at: Optional[datetime]) -> Optional[str]:
    """计算"最后登录距今 X天X时"文案。"""
    if last_login_at is None:
        return None
    delta = datetime.utcnow() - last_login_at
    days = delta.days
    hours = delta.seconds // 3600
    if days > 0:
        return f"{days}天{hours}时"
    if hours > 0:
        return f"{hours}时"
    return "刚刚"


def _is_zombie(last_login_at: Optional[datetime], threshold_days: int = 60) -> bool:
    """是否僵尸用户（>60 天未登录）。"""
    if last_login_at is None:
        return True
    return (datetime.utcnow() - last_login_at).days > threshold_days


async def _check_admin_perm(user: Dict[str, Any]) -> None:
    """校验是否 superadmin 或子管理员（频道含 users）。"""
    role = user.get("role", "")
    if role == "superadmin" or role == "owner":
        return
    # 子管理员：检查 channel_perms 是否含 "users"
    async with session_scope() as session, bypass_tenant_filter():
        u = (await session.execute(select(User).where(User.id == user["user_id"]))).scalar_one_or_none()
        if u is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户不存在")
        perms = u.channel_perms or []
        if "users" not in perms:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问用户管理")


async def _check_superadmin(user: Dict[str, Any]) -> None:
    """仅 superadmin / owner 通过。"""
    role = user.get("role", "")
    if role not in ("superadmin", "owner"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅超级管理员可操作")


# ---------------------------------------------------------------------------
# G-Schemas
# ---------------------------------------------------------------------------


class RoleCreateReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    description: Optional[str] = Field(None, max_length=255)
    channel_perms: List[str] = Field(default_factory=list)


class RoleUpdateReq(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=60)
    description: Optional[str] = Field(None, max_length=255)
    channel_perms: Optional[List[str]] = None


class CreateUserReq(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    password: str = Field(..., min_length=6, max_length=128)
    name: Optional[str] = Field(None, max_length=120)
    user_type: str = Field("saas", pattern="^(demo|dealer|saas|onpremise)$")
    company_name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=120)
    contact_phone: Optional[str] = Field(None, max_length=20)
    payment_proof_path: Optional[str] = Field(None, max_length=500)


class LicenseKeyCreateReq(BaseModel):
    license_code: str = Field(..., min_length=1, max_length=120)
    expires_at: Optional[datetime] = None
    notes: Optional[str] = None


class PluginChangeReq(BaseModel):
    action: str = Field(..., pattern="^(add|remove)$")
    plugin_names: List[str] = Field(..., min_length=1)
    reason: Optional[str] = None


class QuoteReq(BaseModel):
    plugin_names: List[str] = Field(..., min_length=1)


class BatchDisableReq(BaseModel):
    ids: List[int] = Field(..., min_length=1)


class SubAdminCreateReq(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    password: str = Field(..., min_length=6, max_length=128)
    name: Optional[str] = Field(None, max_length=120)
    channel_perms: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# G-1. 角色管理
# ---------------------------------------------------------------------------


@router.get("/roles")
async def list_roles(user: Dict[str, Any] = Depends(current_admin)) -> list:
    """角色列表（裸数组）。"""
    await _check_admin_perm(user)
    async with session_scope() as session, bypass_tenant_filter():
        roles = (await session.scalars(select(Role).order_by(Role.id))).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "channel_perms": r.channel_perms or [],
            "is_system": r.is_system,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in roles
    ]


class LicenseVerifyReq(BaseModel):
    license_code: str = Field(..., min_length=1, max_length=120)


@router.post("/license/verify")
async def verify_license(
    req: LicenseVerifyReq, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    """企业授权码验证（2026-08-11：企业基础信息页填入授权码验证）。"""
    async with session_scope() as session, bypass_tenant_filter():
        lk = (
            await session.execute(
                select(LicenseKey).where(LicenseKey.license_code == req.license_code.strip())
            )
        ).scalar_one_or_none()
        if lk is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="授权码不存在，请核对后重试")
        if lk.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="授权码已停用")
        if lk.expires_at and lk.expires_at < datetime.utcnow():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="授权码已过期")
        cust = (
            await session.execute(select(OnPremiseCustomer).where(OnPremiseCustomer.id == lk.customer_id))
        ).scalar_one_or_none()
        return {
            "valid": True,
            "license_code": lk.license_code,
            "company_name": cust.company_name if cust else None,
            "expires_at": lk.expires_at.isoformat() if lk.expires_at else None,
        }


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    req: RoleCreateReq, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    await _check_superadmin(user)
    async with session_scope() as session, bypass_tenant_filter():
        dup = (await session.execute(select(Role).where(Role.name == req.name))).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="角色名已存在")
        role = Role(
            name=req.name,
            description=req.description,
            channel_perms=req.channel_perms,
            is_system=False,
            created_by=user["user_id"],
        )
        session.add(role)
        await session.commit()
        await session.refresh(role)
        return {"id": role.id, "name": role.name}


@router.put("/roles/{role_id}")
async def update_role(
    role_id: int, req: RoleUpdateReq, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    await _check_superadmin(user)
    async with session_scope() as session, bypass_tenant_filter():
        role = (await session.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
        if req.name is not None:
            role.name = req.name
        if req.description is not None:
            role.description = req.description
        if req.channel_perms is not None:
            role.channel_perms = req.channel_perms
        await session.commit()
        return {"id": role.id, "name": role.name}


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(role_id: int, user: Dict[str, Any] = Depends(current_admin)):
    await _check_superadmin(user)
    async with session_scope() as session, bypass_tenant_filter():
        role = (await session.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
        if role.is_system:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="系统内置角色不可删除")
        await session.delete(role)
        await session.commit()


# ---------------------------------------------------------------------------
# G-2. 用户列表（分类筛选 + last_active_label + zombie 标志）
# ---------------------------------------------------------------------------


@router.get("/users/list")
async def admin_list_users(
    user: Dict[str, Any] = Depends(current_admin),
    user_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> list:
    """用户列表（裸数组，含 last_active_label + zombie 标志）。"""
    await _check_admin_perm(user)
    async with session_scope() as session, bypass_tenant_filter():
        q = select(User).where(User.status != "disabled")
        if user_type and user_type != "all":
            q = q.where(User.user_type == user_type)
        q = q.order_by(User.last_login_at.desc().nullslast(), User.id)
        offset = (page - 1) * size
        rows = (await session.execute(q.offset(offset).limit(size))).scalars().all()
    return [
        {
            "id": u.id,
            "phone": u.phone,
            "name": u.name,
            "role": u.role,
            "user_type": u.user_type,
            "status": u.status,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "last_active_label": _last_active_label(u.last_login_at),
            "zombie": _is_zombie(u.last_login_at),
        }
        for u in rows
    ]


# ---------------------------------------------------------------------------
# G-3. 用户详情
# ---------------------------------------------------------------------------


@router.get("/users/detail/{user_id}")
async def get_user_detail(
    user_id: int, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    await _check_admin_perm(user)
    async with session_scope() as session, bypass_tenant_filter():
        u = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if u is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        return {
            "id": u.id,
            "phone": u.phone,
            "name": u.name,
            "role": u.role,
            "user_type": u.user_type,
            "status": u.status,
            "channel_perms": u.channel_perms,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "last_active_label": _last_active_label(u.last_login_at),
            "zombie": _is_zombie(u.last_login_at),
            "disabled_at": u.disabled_at.isoformat() if u.disabled_at else None,
        }


# ---------------------------------------------------------------------------
# G-4. 新建用户（含独立部署凭证校验）
# ---------------------------------------------------------------------------


@router.post("/users/create", status_code=status.HTTP_201_CREATED)
async def create_user(
    req: CreateUserReq, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    await _check_admin_perm(user)
    from core.auth.password_policy import validate_password_strength

    # 密码强度
    err = validate_password_strength(req.password)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    # 独立部署必须有凭证
    if req.user_type == "onpremise" and not req.payment_proof_path:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="独立部署用户必须上传收款凭证")

    async with session_scope() as session, bypass_tenant_filter():
        # 手机号唯一性（同租户）
        dup = (await session.execute(
            select(User).where(User.phone == req.phone, User.tenant_id == user["tenant_id"])
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该手机号已注册")

        import bcrypt as _bcrypt
        pre = hashlib.sha256(req.password.encode()).hexdigest().encode()
        pwd_hash = _bcrypt.hashpw(pre, _bcrypt.gensalt(rounds=12)).decode()

        new_user = User(
            tenant_id=user["tenant_id"],
            phone=req.phone,
            password_hash=pwd_hash,
            name=req.name or req.phone,
            role="member",
            status="active",
            user_type=req.user_type,
            password_changed_at=datetime.utcnow(),
        )
        session.add(new_user)
        await session.flush()

        # 独立部署 → 创建档案
        if req.user_type == "onpremise":
            cust = OnPremiseCustomer(
                user_id=new_user.id,
                company_name=req.company_name,
                contact_name=req.contact_name,
                contact_phone=req.contact_phone,
                payment_proof_path=req.payment_proof_path,
            )
            session.add(cust)

        await session.commit()
        await session.refresh(new_user)
        return {"id": new_user.id, "phone": new_user.phone, "user_type": new_user.user_type}


# ---------------------------------------------------------------------------
# G-5. 独立部署档案
# ---------------------------------------------------------------------------


@router.get("/onpremise/{target_user_id}")
async def get_onpremise_profile(
    target_user_id: int, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    await _check_admin_perm(user)
    async with session_scope() as session, bypass_tenant_filter():
        cust = (await session.execute(
            select(OnPremiseCustomer).where(OnPremiseCustomer.user_id == target_user_id)
        )).scalar_one_or_none()
        if cust is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="独立部署档案不存在")

        # 授权码历史
        keys = (await session.scalars(
            select(LicenseKey).where(LicenseKey.customer_id == cust.id).order_by(LicenseKey.issued_at.desc())
        )).all()

        license_list = []
        for lk in keys:
            changes = (await session.scalars(
                select(LicensePluginChange).where(LicensePluginChange.license_id == lk.id).order_by(LicensePluginChange.changed_at)
            )).all()
            license_list.append({
                "id": lk.id,
                "license_code": lk.license_code,
                "issued_at": lk.issued_at.isoformat() if lk.issued_at else None,
                "expires_at": lk.expires_at.isoformat() if lk.expires_at else None,
                "status": lk.status,
                "notes": lk.notes,
                "plugin_changes": [
                    {
                        "id": pc.id,
                        "action": pc.action,
                        "plugin_name": pc.plugin_name,
                        "changed_at": pc.changed_at.isoformat() if pc.changed_at else None,
                        "reason": pc.reason,
                    }
                    for pc in changes
                ],
            })

        return {
            "id": cust.id,
            "user_id": cust.user_id,
            "company_name": cust.company_name,
            "contact_name": cust.contact_name,
            "contact_phone": cust.contact_phone,
            "notes": cust.notes,
            "payment_proof_path": cust.payment_proof_path,
            "payment_amount": cust.payment_amount,
            "first_license_date": cust.first_license_date.isoformat() if cust.first_license_date else None,
            "created_at": cust.created_at.isoformat() if cust.created_at else None,
            "license_keys": license_list,
        }


# ---------------------------------------------------------------------------
# G-6. 发授权码
# ---------------------------------------------------------------------------


@router.post("/onpremise/{target_user_id}/license-keys", status_code=status.HTTP_201_CREATED)
async def issue_license_key(
    target_user_id: int, req: LicenseKeyCreateReq, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    await _check_admin_perm(user)
    async with session_scope() as session, bypass_tenant_filter():
        cust = (await session.execute(
            select(OnPremiseCustomer).where(OnPremiseCustomer.user_id == target_user_id)
        )).scalar_one_or_none()
        if cust is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="独立部署档案不存在")

        dup = (await session.execute(
            select(LicenseKey).where(LicenseKey.license_code == req.license_code)
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="授权码已存在")

        lk = LicenseKey(
            customer_id=cust.id,
            license_code=req.license_code,
            expires_at=req.expires_at,
            status="active",
            created_by=user["user_id"],
            notes=req.notes,
        )
        session.add(lk)

        # 首次授权日期
        if cust.first_license_date is None:
            cust.first_license_date = datetime.utcnow()

        await session.commit()
        await session.refresh(lk)
        return {"id": lk.id, "license_code": lk.license_code}


# ---------------------------------------------------------------------------
# G-7. 授权码插件增删（支持批量 plugin_names）
# ---------------------------------------------------------------------------


@router.post("/license-keys/{kid}/plugins")
async def record_plugin_change(
    kid: int, req: PluginChangeReq, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    await _check_admin_perm(user)
    async with session_scope() as session, bypass_tenant_filter():
        lk = (await session.execute(select(LicenseKey).where(LicenseKey.id == kid))).scalar_one_or_none()
        if lk is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="授权码不存在")

        count = 0
        for pname in req.plugin_names:
            session.add(LicensePluginChange(
                license_id=kid,
                action=req.action,
                plugin_name=pname,
                changed_by=user["user_id"],
                reason=req.reason,
            ))
            count += 1
        await session.commit()
        return {"recorded": count}


# ---------------------------------------------------------------------------
# G-8. 授权码更新差价计算（不落库）
# ---------------------------------------------------------------------------


@router.post("/license-keys/{kid}/quote")
async def quote_plugin_price(
    kid: int, req: QuoteReq, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    await _check_admin_perm(user)
    async with session_scope() as session, bypass_tenant_filter():
        lk = (await session.execute(select(LicenseKey).where(LicenseKey.id == kid))).scalar_one_or_none()
        if lk is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="授权码不存在")

        total = 0.0
        for pname in req.plugin_names:
            meta = (await session.execute(
                select(PluginMeta).where(PluginMeta.plugin_name == pname)
            )).scalar_one_or_none()
            if meta:
                total += meta.price_cny
    return {"total_cny": round(total, 2)}


# ---------------------------------------------------------------------------
# G-9. 授权码详情
# ---------------------------------------------------------------------------


@router.get("/license-keys/{kid}")
async def get_license_detail(
    kid: int, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    await _check_admin_perm(user)
    async with session_scope() as session, bypass_tenant_filter():
        lk = (await session.execute(select(LicenseKey).where(LicenseKey.id == kid))).scalar_one_or_none()
        if lk is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="授权码不存在")

        changes = (await session.scalars(
            select(LicensePluginChange).where(LicensePluginChange.license_id == lk.id).order_by(LicensePluginChange.changed_at)
        )).all()

        return {
            "id": lk.id,
            "customer_id": lk.customer_id,
            "license_code": lk.license_code,
            "issued_at": lk.issued_at.isoformat() if lk.issued_at else None,
            "expires_at": lk.expires_at.isoformat() if lk.expires_at else None,
            "status": lk.status,
            "notes": lk.notes,
            "created_by": lk.created_by,
            "plugin_changes": [
                {
                    "id": pc.id,
                    "action": pc.action,
                    "plugin_name": pc.plugin_name,
                    "changed_at": pc.changed_at.isoformat() if pc.changed_at else None,
                    "reason": pc.reason,
                }
                for pc in changes
            ],
        }


# ---------------------------------------------------------------------------
# G-10. 批量停用
# ---------------------------------------------------------------------------


@router.post("/users/batch-disable")
async def batch_disable_users(
    req: BatchDisableReq, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    await _check_admin_perm(user)
    async with session_scope() as session, bypass_tenant_filter():
        now = datetime.utcnow()
        count = 0
        for uid in req.ids:
            u = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            if u and u.status != "disabled":
                u.status = "disabled"
                u.disabled_at = now
                count += 1
        await session.commit()
    return {"disabled": count}


# ---------------------------------------------------------------------------
# G-11. 停用用户列表
# ---------------------------------------------------------------------------


@router.get("/users/disabled")
async def list_disabled_users(
    user: Dict[str, Any] = Depends(current_admin),
) -> list:
    """停用用户列表（裸数组，按停用时长升序）。"""
    await _check_admin_perm(user)
    async with session_scope() as session, bypass_tenant_filter():
        rows = (await session.scalars(
            select(User).where(User.status == "disabled").order_by(User.disabled_at.asc().nullslast())
        )).all()
    now = datetime.utcnow()
    return [
        {
            "id": u.id,
            "phone": u.phone,
            "name": u.name,
            "user_type": u.user_type,
            "disabled_at": u.disabled_at.isoformat() if u.disabled_at else None,
            "disabled_days": (now - u.disabled_at).days if u.disabled_at else None,
        }
        for u in rows
    ]


# ---------------------------------------------------------------------------
# G-12. 凭证文件上传
# ---------------------------------------------------------------------------


@router.post("/upload-proof")
async def upload_proof(request: Request, user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """凭证文件上传（multipart，图片/PDF ≤5MB）→ 返回路径。"""
    from pathlib import Path as _Path

    form = await request.form()
    file = form.get("file")
    if file is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="未上传文件")

    filename = getattr(file, "filename", "") or "proof"
    content_type = getattr(file, "content_type", "") or ""

    # 校验类型
    allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}
    if content_type not in allowed_types:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="仅支持图片或 PDF")

    # 读取内容
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件不能超过 5MB")

    # 存储
    ext = _Path(filename).suffix or (".pdf" if "pdf" in content_type else ".jpg")
    safe_name = f"{user['user_id']}_{int(datetime.utcnow().timestamp())}{ext}"
    upload_dir = _Path("data/payment_proofs") / str(user["user_id"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / safe_name
    dest.write_bytes(content)

    rel_path = str(dest)
    return {"path": rel_path, "filename": filename, "size": len(content)}


# ---------------------------------------------------------------------------
# G-13. 子管理员创建（superadmin 专属）
# ---------------------------------------------------------------------------


@router.post("/sub-admins", status_code=status.HTTP_201_CREATED)
async def create_sub_admin(
    req: SubAdminCreateReq, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    await _check_superadmin(user)
    async with session_scope() as session, bypass_tenant_filter():
        dup = (await session.execute(
            select(User).where(User.phone == req.phone, User.tenant_id == user["tenant_id"])
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该手机号已注册")

        import bcrypt as _bcrypt
        pre = hashlib.sha256(req.password.encode()).hexdigest().encode()
        pwd_hash = _bcrypt.hashpw(pre, _bcrypt.gensalt(rounds=12)).decode()

        sub = User(
            tenant_id=user["tenant_id"],
            phone=req.phone,
            password_hash=pwd_hash,
            name=req.name or req.phone,
            role="admin",
            status="active",
            user_type="saas",
            channel_perms=req.channel_perms,
            password_changed_at=datetime.utcnow(),
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return {"id": sub.id, "phone": sub.phone, "channel_perms": sub.channel_perms}


# ---------------------------------------------------------------------------
# G-14. 插件列表扩展（返回 price_cny）
# ---------------------------------------------------------------------------


@router.get("/plugins-with-price")
async def list_plugins_with_price(
    request: Request, user: Dict[str, Any] = Depends(current_admin)
) -> list:
    """全部插件清单（含 price_cny，供授权码更新弹窗用）。"""
    from pathlib import Path

    try:
        import yaml as _yaml
    except Exception:  # noqa: BLE001
        _yaml = None

    loaded_plugins = getattr(request.app.state, "plugins", None) or {}
    plugins_dir = Path(__file__).resolve().parents[2] / "plugins"

    # 批量读取 price_cny
    async with session_scope() as session, bypass_tenant_filter():
        metas = (await session.scalars(select(PluginMeta))).all()
        price_map = {m.plugin_name: m.price_cny for m in metas}

    catalog = []
    if plugins_dir.is_dir():
        for manifest_path in sorted(plugins_dir.glob("*/manifest.yaml")):
            name = manifest_path.parent.name
            if name in {"_template", "embedded_llm"}:
                continue
            info = {
                "name": name,
                "version": "",
                "description": "",
                "installed": name in loaded_plugins,
                "enabled": name in loaded_plugins,
                "price_cny": price_map.get(name, 0.0),
            }
            if _yaml is not None:
                try:
                    m = _yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
                    info["version"] = str(m.get("version", "") or "")
                    info["description"] = str(m.get("description", "") or "")
                    info["tier"] = str(m.get("tier", "beta") or "beta")
                except Exception:  # noqa: BLE001
                    pass
            catalog.append(info)
    return catalog


__all__ = ["router"]


# --------------------------------------------------------------------------- #
# 企业工作日志（2026-08-11：owner/admin 可见，对话 + 流程执行）
# --------------------------------------------------------------------------- #


@router.get("/work-logs")
async def work_logs(
    days: int = Query(7, ge=1, le=90),
    log_type: str = Query("all", description="all / chat / flow"),
    limit: int = Query(50, ge=1, le=200),
    user: Dict[str, Any] = Depends(current_admin),
) -> Dict[str, Any]:
    """企业工作日志：员工对话记录 + 碳硅流程执行记录（租户级，倒序）。"""
    tenant_id = user.get("tenant_id")
    since = datetime.utcnow() - timedelta(days=days)
    items: list[Dict[str, Any]] = []
    async with session_scope() as session, bypass_tenant_filter():
        # 1) 对话日志（chat_messages 表直连 + 用户姓名）
        if log_type in ("all", "chat"):
            from sqlalchemy import text as sa_text
            rows = (await session.execute(sa_text(
                "SELECT c.id, c.user_id, c.role, c.content, c.provider, c.model, "
                "c.tokens_in, c.tokens_out, c.cost, c.created_at, "
                "u.name AS user_name, u.role AS user_role, u.phone AS user_phone "
                "FROM chat_messages c LEFT JOIN users u ON u.id = c.user_id "
                "WHERE c.tenant_id = :tid AND c.created_at >= :since "
                "ORDER BY c.id DESC LIMIT :lim"
            ), {"tid": tenant_id, "since": since, "lim": limit})).mappings().all()
            for r in rows:
                items.append({
                    "type": "chat",
                    "id": r["id"],
                    "user": r["user_name"] or (r["user_phone"] or f"用户#{r['user_id']}"),
                    "user_role": r["user_role"] or "",
                    "role": r["role"],
                    "content": r["content"],
                    "provider": r["provider"] or "",
                    "model": r["model"] or "",
                    "tokens_in": r["tokens_in"] or 0,
                    "tokens_out": r["tokens_out"] or 0,
                    "cost": float(r["cost"] or 0),
                    "created_at": str(r["created_at"]) if r["created_at"] else None,
                })
        # 2) 流程执行日志（flow_runs + 流程名）
        if log_type in ("all", "flow"):
            from sqlalchemy import text as sa_text
            rows = (await session.execute(sa_text(
                "SELECT r.id, r.flow_id, r.version, r.status, r.result, r.error, r.created_by, "
                "r.started_at, r.finished_at, f.name AS flow_name, f.tenant_id AS f_tenant, "
                "u.name AS user_name, u.phone AS user_phone "
                "FROM flow_runs r LEFT JOIN flow_definitions f ON f.id = r.flow_id "
                "LEFT JOIN users u ON u.id = r.created_by "
                "WHERE f.tenant_id = :tid AND r.started_at >= :since "
                "ORDER BY r.id DESC LIMIT :lim"
            ), {"tid": tenant_id, "since": since, "lim": limit})).mappings().all()
            for r in rows:
                items.append({
                    "type": "flow",
                    "id": r["id"],
                    "user": r["user_name"] or (r["user_phone"] or f"用户#{r['created_by']}"),
                    "flow_name": r["flow_name"] or f"流程#{r['flow_id']}",
                    "flow_version": r["version"],
                    "status": r["status"],
                    "result": r["result"],
                    "error": r["error"],
                    "created_at": str(r["started_at"]) if r["started_at"] else None,
                })
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"total": len(items), "items": items[:limit]}


# ---------------------------------------------------------------------------
# H. 发证 API（P1：表单化发证，复用 P0 Ed25519 签名逻辑）
# ---------------------------------------------------------------------------


class LicenseGenerateFileReq(BaseModel):
    customer_id: int = Field(..., gt=0, description="onpremise_customers.id")
    instance_id: str = Field(..., min_length=1, max_length=120)
    machine_fingerprint: str = Field(
        ..., min_length=32, max_length=64, description="目标机器指纹（32位hex）"
    )
    valid_days: int = Field(365, gt=0, le=3650, description="有效期天数")
    authorized_plugins: List[str] = Field(
        default_factory=list, description="授权插件列表；空=全部（*）"
    )


@router.post("/license/generate-file")
async def generate_license_file(
    req: LicenseGenerateFileReq, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    """表单化发证：客户 + 机器码 + 插件清单 → 返回签名 license 文件内容（base64）。

    仅 superadmin 可调用；私钥路径来自环境变量 ``DDW_LICENSE_PRIVATE_KEY_PATH``
    （管理端才配置），代码/测试不硬编码任何密钥；签名逻辑复用
    ``scripts/issue_license.py``（P0 产出），不重复实现。
    """
    from core.constants.roles import Role

    if user.get("role") != Role.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级管理员可签发许可证文件",
        )

    import base64
    import json
    import os
    from pathlib import Path

    async with session_scope() as session, bypass_tenant_filter():
        cust = (await session.execute(
            select(OnPremiseCustomer).where(OnPremiseCustomer.id == req.customer_id)
        )).scalar_one_or_none()
        if cust is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="独立部署客户档案不存在",
            )

    key_path = os.environ.get("DDW_LICENSE_PRIVATE_KEY_PATH", "").strip()
    if not key_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置 DDW_LICENSE_PRIVATE_KEY_PATH，无法签发许可证",
        )

    from scripts.issue_license import issue_license, load_private_key

    try:
        private_key = load_private_key(Path(key_path))
    except (OSError, ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"私钥加载失败: {e}",
        ) from e

    customer_name = cust.company_name or f"客户#{req.customer_id}"
    license_key = f"LIC-{datetime.utcnow():%Y%m%d}-{secrets.token_hex(3).upper()}"
    payload = issue_license(
        private_key=private_key,
        license_key=license_key,
        customer=customer_name,
        instance_id=req.instance_id,
        machine_fingerprint=req.machine_fingerprint,
        valid_days=req.valid_days,
        authorized_plugins=req.authorized_plugins,
        issued_by=f"DDW-Admin-{user.get('user_id')}",
    )
    content = json.dumps(payload, indent=2, ensure_ascii=False)
    logger.info(
        "license file generated customer=%s license_key=%s valid_to=%s "
        "plugins=%d by_user=%s",
        customer_name,
        license_key,
        payload.get("valid_to"),
        len(req.authorized_plugins),
        user.get("user_id"),
    )
    return {
        "license_file_base64": base64.b64encode(content.encode("utf-8")).decode(),
        "license_key": license_key,
        "customer": customer_name,
        "valid_to": payload.get("valid_to"),
    }


# ---------------------------------------------------------------------------
# I. 插件运行时管理（P4 热加载，仅 superadmin；操作全审计）
# ---------------------------------------------------------------------------


def _get_plugin_runtime(request: Request):
    """取 PluginRuntime（load_plugins 挂到 app.state.plugin_runtime）。"""
    runtime = getattr(request.app.state, "plugin_runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=503,
            detail="插件运行时未初始化（服务未完成启动？）",
        )
    return runtime


@router.get("/plugins/runtime")
async def list_plugin_runtime(
    request: Request, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    """插件运行时状态快照（loaded/disabled/error/pending_restart）。"""
    from core.constants.roles import Role

    if user.get("role") != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="仅超级管理员可查看插件运行时")
    runtime = _get_plugin_runtime(request)
    return {"items": runtime.snapshot(), "total": len(runtime.snapshot())}


@router.post("/plugins/{name}/load", status_code=200)
async def load_plugin_runtime(
    name: str, request: Request, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    """热启已落盘插件（红线：locked 拒绝 / 授权过滤同路径 / 保留名拒绝）。"""
    from core.constants.roles import Role

    if user.get("role") != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="仅超级管理员可热启插件")
    runtime = _get_plugin_runtime(request)
    operator = f"user:{user.get('user_id')}"
    instance = runtime.load_one(name, operator=operator)
    if instance is None:
        raise HTTPException(
            status_code=400, detail=f"插件 {name} 加载失败（见审计/日志）"
        )
    return {"loaded": True, "name": name, "state": "loaded"}


@router.post("/plugins/{name}/unload", status_code=200)
async def unload_plugin_runtime(
    name: str, request: Request, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    """停用插件入口（路由保留，彻底清理走重启）。"""
    from core.constants.roles import Role

    if user.get("role") != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="仅超级管理员可停用插件")
    runtime = _get_plugin_runtime(request)
    operator = f"user:{user.get('user_id')}"
    if not runtime.unload_entry(name, operator=operator):
        raise HTTPException(
            status_code=404, detail=f"插件 {name} 不在运行时注册表（未加载？）"
        )
    return {"unloaded": True, "name": name, "state": "disabled"}


@router.post("/plugins/{name}/reload", status_code=200)
async def reload_plugin_runtime(
    name: str, request: Request, user: Dict[str, Any] = Depends(current_admin)
) -> Dict[str, Any]:
    """滚动重挂：停用入口 → 重新加载。

    模块级单例插件（如 ddw_memory）热替换不彻底：返回 pending_restart=true
    时需重启服务才完全生效（诚实边界）。
    """
    from core.constants.roles import Role

    if user.get("role") != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="仅超级管理员可重挂插件")
    runtime = _get_plugin_runtime(request)
    operator = f"user:{user.get('user_id')}"
    ok = runtime.reload_one(name, operator=operator)
    rec = runtime.registry.get(name)
    pending = bool(rec and rec.get("pending_restart"))
    if not ok:
        raise HTTPException(
            status_code=400, detail=f"插件 {name} 重挂失败（见审计/日志）"
        )
    return {"reloaded": True, "name": name, "pending_restart": pending}


@router.post("/plugins/install", status_code=201)
async def install_plugin_package(
    request: Request,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(current_admin),
) -> Dict[str, Any]:
    """上传 .ddwplugin 包 → 验签 → 落盘 → 安装即生效（P4）。

    红线①：验签唯一入口（installer.verify_package），未签名/篡改包拒绝安装，
    不触发加载。
    """
    from core.constants.roles import Role

    if user.get("role") != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="仅超级管理员可安装插件")
    runtime = _get_plugin_runtime(request)
    if not (file.filename or "").endswith(".ddwplugin"):
        raise HTTPException(status_code=400, detail="仅支持 .ddwplugin 包")

    import tempfile
    from pathlib import Path

    from core.plugin_manager.installer import install_from_package

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".ddwplugin"
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(await file.read())
        from core.plugin_manager.manager import PluginManager

        name = install_from_package(
            tmp_path,
            runtime=runtime,
            pm=PluginManager(plugins_root=runtime.plugin_root),
        )
    except (ValueError, FileExistsError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"插件安装被拒绝: {e}") from e
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
    rec = runtime.registry.get(name)
    return {
        "installed": True,
        "name": name,
        "state": (rec or {}).get("state", "installed"),
        "note": "安装即生效（加载失败时 registry 记 error，见 /plugins/runtime）",
    }
