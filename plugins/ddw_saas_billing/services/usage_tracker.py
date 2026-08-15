"""用量计量"""
from __future__ import annotations


from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_saas_billing.models import UsageLog


async def record_usage(tenant_id: int, user_id: int, event_type: str, tokens: int) -> None:
    async with session_scope() as s, bypass_tenant_filter():
        log = UsageLog(tenant_id=tenant_id, user_id=user_id, event_type=event_type, tokens_used=tokens)
        s.add(log)
        await s.commit()
