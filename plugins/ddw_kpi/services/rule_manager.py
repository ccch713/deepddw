"""KPI 规则管理"""
from __future__ import annotations

from typing import List

from sqlalchemy import select

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_kpi.models import KpiRule


async def get_enabled_rules(subject: str = "") -> List[KpiRule]:
    async with session_scope() as s, bypass_tenant_filter():
        q = select(KpiRule).where(KpiRule.enabled == True)
        if subject:
            q = q.where(KpiRule.subject == subject)
        return list((await s.execute(q)).scalars().all())
