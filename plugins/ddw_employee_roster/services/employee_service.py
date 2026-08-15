"""员工服务"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import select

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_employee_roster.models import Employee


async def get_all_employees() -> List[Dict[str, Any]]:
    async with session_scope() as s, bypass_tenant_filter():
        rows = (await s.execute(select(Employee))).scalars().all()
    return [{"id": e.id, "name": e.name, "department": e.department} for e in rows]
