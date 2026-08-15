"""培训记录服务"""
from __future__ import annotations

from typing import Any, Dict

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_employee_roster.models import EmployeeTrainingRecord


async def write_training_record(data: Dict[str, Any]) -> None:
    async with session_scope() as s, bypass_tenant_filter():
        rec = EmployeeTrainingRecord(**data)
        s.add(rec)
        await s.commit()
