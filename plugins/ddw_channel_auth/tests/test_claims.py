"""DDW 渠道授权与结算插件 — 报备状态机测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_channel_auth.models import ChannelPartner
from plugins.ddw_channel_auth.schemas import ClaimCreateReq
from plugins.ddw_channel_auth.services import ClaimService


async def _seed_partner(
    db: AsyncSession,
    partner_id: int = 1,
    name: str = "经销商A",
) -> ChannelPartner:
    """创建测试合作伙伴。"""
    partner = ChannelPartner(
        id=partner_id, name=name,
        partner_type="company", tenant_id=1,
    )
    db.add(partner)
    await db.commit()
    await db.refresh(partner)
    return partner


@pytest.mark.anyio
async def test_claim_state_machine_transitions_claimed_to_paid(db: AsyncSession):
    """全链路：创建 claim -> 上传合同 -> 标记支付 -> 断言 state='paid'。"""
    await _seed_partner(db)
    svc = ClaimService(db)
    req = ClaimCreateReq(
        company_full_name="测试科技有限公司",
        company_credit_code="91310000MA1FL5E030",
    )
    result = await svc.create_claim(partner_id=1, req=req)
    claim = result["claim"]
    assert claim.state == "claimed", "新建报备应为 claimed 状态"

    # 上传合同
    result2 = await svc.mark_contract_uploaded(claim.id, "/tmp/test.pdf")
    assert result2["is_first_to_upload_contract"] is True, "首次上传应获胜"
    claim2 = await svc.get_claim(claim.id)
    assert claim2.state == "contract_signed", "首个上传合同应直接锁定为 contract_signed"

    # 标记支付
    result3 = await svc.mark_paid(claim.id)
    assert result3["is_first_to_pay"] is True
    claim3 = await svc.get_claim(claim.id)
    assert claim3.state == "paid", "付款后应为 paid 状态"


@pytest.mark.anyio
async def test_claim_first_to_upload_contract_wins(db: AsyncSession):
    """同公司 2 个 claim，第二个上传合同不会被选中。"""
    await _seed_partner(db, partner_id=1, name="经销商A")
    svc = ClaimService(db)
    req = ClaimCreateReq(
        company_full_name="竞争测试有限公司",
        company_credit_code="91110000MA004P0N3G",
    )
    # 第一个 claim
    r1 = await svc.create_claim(partner_id=1, req=req)
    claim1 = r1["claim"]
    # 第二个 claim（不同合作伙伴）
    await _seed_partner(db, partner_id=2, name="经销商B")
    r2 = await svc.create_claim(partner_id=2, req=req)
    claim2 = r2["claim"]

    # 第一个先上传合同 -> 锁定
    result1 = await svc.mark_contract_uploaded(claim1.id, "/tmp/c1.pdf")
    assert result1["is_first_to_upload_contract"] is True, "第一个上传应获胜"

    # 第二个再上传 -> 不应获胜
    result2 = await svc.mark_contract_uploaded(claim2.id, "/tmp/c2.pdf")
    assert result2["is_first_to_upload_contract"] is False, (
        "第二个上传不应获胜，已被锁定"
    )


@pytest.mark.anyio
async def test_claim_first_to_pay_wins_in_release_window(db: AsyncSession):
    """释放后付款者得。"""
    await _seed_partner(db)
    svc = ClaimService(db)
    req = ClaimCreateReq(
        company_full_name="释放测试有限公司",
        company_credit_code="91440300MA5EQTF001",
    )
    result = await svc.create_claim(partner_id=1, req=req)
    claim = result["claim"]

    # 手动设置 claimed_at 为 31 天前以触发释放
    from datetime import datetime, timedelta
    claim.claimed_at = datetime.utcnow() - timedelta(days=31)
    await db.commit()

    # 释放
    release_result = await svc.release_expired(claim.id)
    assert release_result["released"] is True, "超过 30 天应被释放"

    # 新 claim 付款
    r2 = await svc.create_claim(partner_id=1, req=req)
    claim2 = r2["claim"]
    pay_result = await svc.mark_paid(claim2.id)
    assert pay_result["is_first_to_pay"] is True, "新 claim 付款应获胜"
    claim2_after = await svc.get_claim(claim2.id)
    assert claim2_after.state == "paid", "付款后应为 paid 状态"
