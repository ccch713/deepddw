"""订阅管理服务"""
from __future__ import annotations


from sqlalchemy import select

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_saas_billing.models import Subscription


async def check_quota(tenant_id: int) -> bool:
    async with session_scope() as s, bypass_tenant_filter():
        sub = (await s.execute(select(Subscription).where(Subscription.tenant_id == tenant_id, Subscription.status == "active"))).scalar_one_or_none()
    if not sub:
        return False
    return sub.used < sub.monthly_limit
