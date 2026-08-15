"""DDW 渠道授权与结算插件 — 难缠客户标记测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_channel_auth.services import DifficultCustomerService


@pytest.mark.anyio
async def test_difficult_customer_flagged_when_threshold_reached(db: AsyncSession):
    """同 company_credit_code 被标记 3 次 -> flag_count >= 3。"""
    svc = DifficultCustomerService(db)
    credit_code = "91310000MA1FL5E030"

    # 标记 3 次
    f1 = await svc.flag_customer(credit_code, reason="拒绝付款")
    assert f1.flag_count == 1

    f2 = await svc.flag_customer(credit_code, reason="恶意压价")
    assert f2.flag_count == 2

    f3 = await svc.flag_customer(credit_code, reason="拖延合同")
    assert f3.flag_count == 3, f"第 3 次标记 flag_count 应为 3，实际 {f3.flag_count}"

    # 验证阈值
    assert f3.flag_count >= DifficultCustomerService.FLAG_THRESHOLD, \
        f"flag_count 应 >= 阈值 {DifficultCustomerService.FLAG_THRESHOLD}"
