"""租户服务（DDW AI Hub v5.4 — 模块 A2）。

封装租户的 CRUD、套餐升降、用量统计等业务逻辑。
设计上：
- 所有方法接收 ``session: AsyncSession``，由调用方管理事务
- 不直接读 :data:`tenant_filter` 的 contextvar（业务层不应该关心）
- 内部抛 :class:`TenantNotFound` / :class:`PlanNotAllowed` 让 API 层映射为 HTTP 状态
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database.models import ApiKey, Tenant, TokenQuota, User

logger = logging.getLogger(__name__)


class TenantError(Exception):
    """租户业务异常基类。"""


class TenantNotFound(TenantError):
    pass


class PlanNotAllowed(TenantError):
    pass


VALID_PLANS = {"free", "standard", "enterprise"}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_tenant(
    session: AsyncSession,
    name: str,
    plan: str = "free",
    contact_phone: Optional[str] = None,
) -> Tenant:
    """创建租户 + 默认 TokenQuota。"""
    if plan not in VALID_PLANS:
        raise PlanNotAllowed(f"unsupported plan: {plan}")

    tenant = Tenant(name=name, plan=plan, contact_phone=contact_phone)
    session.add(tenant)
    await session.flush()  # 取到 tenant.id

    # 默认月配额
    settings = get_settings()
    default_limit = {
        "free": 100_000,
        "standard": 5_000_000,
        "enterprise": 50_000_000,
    }.get(plan, 100_000)
    now = datetime.utcnow()
    quota = TokenQuota(
        tenant_id=tenant.id,
        period="monthly",
        token_limit=default_limit,
        tokens_used=0,
        period_start=now,
        period_end=now + timedelta(days=30),
    )
    session.add(quota)
    await session.flush()

    logger.info("created tenant id=%s name=%s plan=%s", tenant.id, name, plan)
    return tenant


async def get_tenant_by_id(session: AsyncSession, tenant_id: int) -> Optional[Tenant]:
    res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    return res.scalar_one_or_none()


async def get_tenant_by_phone(session: AsyncSession, phone: str) -> Optional[Tenant]:
    """通过主用户手机号反查租户。"""
    res = await session.execute(select(Tenant).join(User, User.tenant_id == Tenant.id).where(User.phone == phone))
    return res.scalar_one_or_none()


async def upgrade_plan(session: AsyncSession, tenant_id: int, new_plan: str) -> Tenant:
    if new_plan not in VALID_PLANS:
        raise PlanNotAllowed(f"unsupported plan: {new_plan}")
    tenant = await get_tenant_by_id(session, tenant_id)
    if tenant is None:
        raise TenantNotFound(f"tenant {tenant_id} not found")
    old = tenant.plan
    tenant.plan = new_plan
    # 同步调整默认配额上限
    new_limit = {
        "free": 100_000,
        "standard": 5_000_000,
        "enterprise": 50_000_000,
    }[new_plan]
    await session.execute(
        TokenQuota.__table__.update().where(TokenQuota.tenant_id == tenant_id).values(token_limit=new_limit)
    )
    await session.flush()
    logger.info("tenant %s upgraded %s → %s", tenant_id, old, new_plan)
    return tenant


# ---------------------------------------------------------------------------
# 用量统计
# ---------------------------------------------------------------------------


async def get_tenant_usage(session: AsyncSession, tenant_id: int) -> Dict[str, Any]:
    """聚合统计：用户数 / API Key 数 / Token 用量 / 当前周期。"""
    user_count = await session.scalar(select(func.count(User.id)).where(User.tenant_id == tenant_id)) or 0
    key_count = await session.scalar(select(func.count(ApiKey.id)).where(ApiKey.tenant_id == tenant_id)) or 0
    quota = (
        await session.execute(
            select(TokenQuota).where(TokenQuota.tenant_id == tenant_id).order_by(TokenQuota.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return {
        "user_count": int(user_count),
        "api_key_count": int(key_count),
        "tokens_used": int(quota.tokens_used) if quota else 0,
        "token_limit": int(quota.token_limit) if quota else 0,
        "period_start": quota.period_start.isoformat() if quota else None,
        "period_end": quota.period_end.isoformat() if quota else None,
    }


__all__ = [
    "PlanNotAllowed",
    "TenantError",
    "TenantNotFound",
    "VALID_PLANS",
    "create_tenant",
    "get_tenant_by_id",
    "get_tenant_by_phone",
    "get_tenant_usage",
    "upgrade_plan",
]
