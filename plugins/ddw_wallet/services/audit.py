"""审计日志服务（G12）— 记录余额变更操作。"""
from __future__ import annotations

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from plugins.ddw_wallet.models import AuditLog

logger = logging.getLogger(__name__)


async def log_audit(
    session: AsyncSession,
    tenant_id: str,
    user_id: str,
    operator: str,
    action: str,
    amount_cents: int,
    balance_before: int,
    balance_after: int,
    reason: str = "",
):
    """写入审计日志。"""
    rec = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        operator=operator,
        action=action,
        amount_cents=amount_cents,
        balance_before=balance_before,
        balance_after=balance_after,
        reason=reason,
    )
    session.add(rec)
    await session.flush()
    logger.info(
        "Audit log: %s %s %d (%s)", action, user_id, amount_cents, reason
    )
