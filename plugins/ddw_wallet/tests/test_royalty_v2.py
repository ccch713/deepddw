"""M1 分成 v2 测试：抽佣幂等 + 先佣后分。"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.services.charge import settle_platform_fee


@pytest.mark.asyncio
async def test_platform_fee_idempotent(session: AsyncSession):
    """抽佣幂等：同 txn 只抽一次。"""
    fee1 = await settle_platform_fee(session, "TX_PF1", 1000)
    fee2 = await settle_platform_fee(session, "TX_PF1", 1000)
    assert fee1 == fee2 == 50
    await session.commit()


@pytest.mark.asyncio
async def test_platform_fee_then_royalty(session: AsyncSession):
    """先抽佣后分作者：抽佣金额正确。"""
    fee = await settle_platform_fee(session, "TX_PF2", 2000)
    assert fee == 100  # 2000 * 5% = 100
    await session.commit()
