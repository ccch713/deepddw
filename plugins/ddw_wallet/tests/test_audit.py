"""M1 审计日志测试：写入 + 租户隔离。"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.models import AuditLog
from plugins.ddw_wallet.services.audit import log_audit


@pytest.mark.asyncio
async def test_audit_write(session: AsyncSession):
    """审计日志写入。"""
    await log_audit(session, "default", "u_aud", "admin", "manual_credit", 1000, 0, 1000, "测试调账")
    await session.commit()

    result = await session.execute(select(AuditLog).where(AuditLog.user_id == "u_aud"))
    logs = result.scalars().all()
    assert len(logs) >= 1
    assert logs[-1].action == "manual_credit"
    assert logs[-1].amount_cents == 1000


@pytest.mark.asyncio
async def test_audit_tenant_isolation(session: AsyncSession):
    """审计日志租户隔离。"""
    await log_audit(session, "school_x", "u_ax", "admin", "adjust", 500, 1000, 1500)
    await log_audit(session, "school_y", "u_ay", "admin", "adjust", 300, 500, 800)
    await session.commit()

    result_x = await session.execute(select(AuditLog).where(AuditLog.tenant_id == "school_x"))
    result_y = await session.execute(select(AuditLog).where(AuditLog.tenant_id == "school_y"))
    logs_x = result_x.scalars().all()
    logs_y = result_y.scalars().all()
    # school_x 只有自己的日志
    assert all(log.tenant_id == "school_x" for log in logs_x)
    assert all(log.tenant_id == "school_y" for log in logs_y)
