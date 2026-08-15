from __future__ import annotations

"""DDW 应收实收核销插件测试用例（10 个）。

覆盖：
 1. 精确匹配（金额 + 公司完全相等）
 2. 无匹配
 3. 单笔核销
 4. 多笔对多笔核销（一笔 payment 拆给多 receivable）
 5. 超额核销（应抛 ValueError）
 6. 取消核销
 7. 核销历史记录
 8. 未核销汇总
 9. payment status 自动转换（pending → partial → matched）
10. receivable status 自动转换（pending → partial → paid）
"""

from decimal import Decimal

import pytest

from plugins.ddw_offline_pos.models import Payment
from plugins.ddw_receivable.models import Receivable
from plugins.ddw_reconciliation.schemas import (
    CancelReq,
    ConfirmMatchItem,
    ConfirmReq,
    MatchReq,
)

# ===========================================================================
# 1. 精确匹配（金额 + 公司完全相等）
# ===========================================================================


@pytest.mark.asyncio
async def test_match_exact(service, make_receivable, make_payment):
    """精确匹配：payment 10000 应收 10000 + 同公司 → 1 条 suggestion。"""
    # 1 个应收 10000 元
    await make_receivable(
        node_name="首款", amount=Decimal("10000.00"), company_id=100
    )
    # 2 个实收：第一个 10000 同公司（应被推荐），第二个 5000 不同金额（不推荐）
    p1 = await make_payment(
        payer_name="测试客户公司",
        amount=Decimal("10000.00"),
        company_id=100,
    )
    await make_payment(
        payer_name="测试客户公司",
        amount=Decimal("5000.00"),
        company_id=100,
    )

    resp = await service.match(MatchReq(payment_id=p1.id))
    assert resp.payment_id == p1.id
    assert resp.payment_amount == Decimal("10000.00")
    assert resp.payment_remaining == Decimal("10000.00")
    assert resp.payment_company_id == 100

    # 1 条精确匹配
    assert len(resp.suggestions) == 1
    sug = resp.suggestions[0]
    assert sug.match_type == "exact"
    assert sug.confidence == 1.0
    assert sug.amount == Decimal("10000.00")
    assert sug.outstanding_amount == Decimal("10000.00")
    assert sug.suggested_amount == Decimal("10000.00")


# ===========================================================================
# 2. 无匹配（金额 / 公司 / 状态 三种异常）
# ===========================================================================


@pytest.mark.asyncio
async def test_match_no_result(service, make_receivable, make_payment):
    """无匹配场景：金额不等 / 公司不同 / 应收已付清，三种情况都应 0 匹配。"""
    # 应收 8000 元（同公司 100）
    await make_receivable(
        node_name="首款", amount=Decimal("8000.00"), company_id=100
    )
    # 实收 10000 元（金额不等 → 0 匹配）
    p1 = await make_payment(
        amount=Decimal("10000.00"), company_id=100
    )
    resp = await service.match(MatchReq(payment_id=p1.id))
    assert len(resp.suggestions) == 0

    # 应收 10000 元（公司 200）
    await make_receivable(
        node_name="部署款", amount=Decimal("10000.00"), company_id=200
    )
    # 实收 10000 元（公司 100 → 不同公司 → 0 匹配）
    p2 = await make_payment(
        amount=Decimal("10000.00"), company_id=100
    )
    resp = await service.match(MatchReq(payment_id=p2.id))
    assert len(resp.suggestions) == 0

    # 实收 status=matched（不应允许匹配）
    p3 = await make_payment(
        amount=Decimal("10000.00"),
        company_id=100,
        matched_amount=Decimal("10000.00"),
        status="matched",
    )
    with pytest.raises(ValueError, match="不允许参与匹配"):
        await service.match(MatchReq(payment_id=p3.id))


# ===========================================================================
# 3. 单笔核销：payment 10000 → receivable 10000（status 改 paid）
# ===========================================================================


@pytest.mark.asyncio
async def test_confirm_single_match(service, make_receivable, make_payment):
    """单笔核销：1 笔 payment 全部匹配到 1 笔 receivable，金额相等。"""
    r = await make_receivable(
        node_name="首款", amount=Decimal("10000.00"), company_id=100
    )
    p = await make_payment(
        amount=Decimal("10000.00"), company_id=100
    )

    resp = await service.confirm(
        ConfirmReq(
            payment_id=p.id,
            matches=[ConfirmMatchItem(receivable_id=r.id, amount=Decimal("10000.00"))],
        )
    )

    assert resp.payment_id == p.id
    assert resp.payment_status == "matched"
    assert resp.payment_matched_amount == Decimal("10000.00")
    assert resp.payment_remaining == Decimal(0)
    assert resp.total_matched == Decimal("10000.00")
    assert len(resp.results) == 1

    # receivable 应变为 paid
    res_item = resp.results[0]
    assert res_item.receivable_id == r.id
    assert res_item.paid_amount == Decimal("10000.00")
    assert res_item.outstanding_amount == Decimal(0)
    assert res_item.status == "paid"
    assert res_item.matched_this_time == Decimal("10000.00")

    # 校验 DB 实际状态
    refreshed = await service.db.get(Receivable, r.id)
    assert refreshed.status == "paid"
    assert refreshed.paid_amount == Decimal("10000.00")
    prefreshed = await service.db.get(Payment, p.id)
    assert prefreshed.status == "matched"


# ===========================================================================
# 4. 多笔对多笔核销（一笔 payment 拆给多 receivable）
# ===========================================================================


@pytest.mark.asyncio
async def test_confirm_multi_match(service, make_receivable, make_payment):
    """一笔 10000 拆给 3 个 receivable（3000+4000+3000），payment → matched。"""
    r1 = await make_receivable(
        node_name="首款", amount=Decimal("3000.00"), company_id=100
    )
    r2 = await make_receivable(
        node_name="部署款", amount=Decimal("4000.00"), company_id=100
    )
    r3 = await make_receivable(
        node_name="尾款", amount=Decimal("3000.00"), company_id=100
    )
    p = await make_payment(
        amount=Decimal("10000.00"), company_id=100
    )

    resp = await service.confirm(
        ConfirmReq(
            payment_id=p.id,
            matches=[
                ConfirmMatchItem(receivable_id=r1.id, amount=Decimal("3000.00")),
                ConfirmMatchItem(receivable_id=r2.id, amount=Decimal("4000.00")),
                ConfirmMatchItem(receivable_id=r3.id, amount=Decimal("3000.00")),
            ],
        )
    )

    assert resp.total_matched == Decimal("10000.00")
    assert resp.payment_status == "matched"
    assert resp.payment_remaining == Decimal(0)
    assert len(resp.results) == 3

    # 三个 receivable 都应该是 paid
    for item in resp.results:
        assert item.paid_amount == Decimal("3000.00") or item.paid_amount == Decimal("4000.00")
        assert item.status == "paid"
        assert item.matched_this_time > Decimal(0)

    # DB 验证
    r1db = await service.db.get(Receivable, r1.id)
    r2db = await service.db.get(Receivable, r2.id)
    r3db = await service.db.get(Receivable, r3.id)
    assert (r1db.status, r2db.status, r3db.status) == ("paid", "paid", "paid")
    pdb = await service.db.get(Payment, p.id)
    assert pdb.status == "matched"


# ===========================================================================
# 5. 超额核销：matches 总和 > payment_remaining → ValueError
# ===========================================================================


@pytest.mark.asyncio
async def test_confirm_exceeds_payment(service, make_receivable, make_payment):
    """核销超额：sum(matches) > payment.amount - payment.matched_amount 抛 ValueError。"""
    r1 = await make_receivable(
        node_name="首款", amount=Decimal("5000.00"), company_id=100
    )
    r2 = await make_receivable(
        node_name="尾款", amount=Decimal("8000.00"), company_id=100
    )
    p = await make_payment(
        amount=Decimal("10000.00"), company_id=100
    )

    # 6000 + 5000 = 11000 > 10000 → 超出
    with pytest.raises(ValueError, match="超过实收单剩余可核销金额"):
        await service.confirm(
            ConfirmReq(
                payment_id=p.id,
                matches=[
                    ConfirmMatchItem(receivable_id=r1.id, amount=Decimal("6000.00")),
                    ConfirmMatchItem(receivable_id=r2.id, amount=Decimal("5000.00")),
                ],
            )
        )

    # 校验：失败时数据应回滚（receivable / payment 状态都未变）
    r1db = await service.db.get(Receivable, r1.id)
    pdb = await service.db.get(Payment, p.id)
    assert r1db.paid_amount == Decimal(0)
    assert r1db.status == "pending"
    assert pdb.matched_amount == Decimal(0)
    assert pdb.status == "pending"


# ===========================================================================
# 6. 取消核销：confirm 之后 cancel（单条）
# ===========================================================================


@pytest.mark.asyncio
async def test_cancel_match(service, make_receivable, make_payment):
    """单条取消：先 confirm 一笔 → 再 cancel，receivable / payment 状态都回退。"""
    r = await make_receivable(
        node_name="首款", amount=Decimal("10000.00"), company_id=100
    )
    p = await make_payment(
        amount=Decimal("10000.00"), company_id=100
    )

    # confirm
    confirm_resp = await service.confirm(
        ConfirmReq(
            payment_id=p.id,
            matches=[ConfirmMatchItem(receivable_id=r.id, amount=Decimal("10000.00"))],
        )
    )
    assert confirm_resp.payment_status == "matched"

    # cancel
    cancel_resp = await service.cancel(
        CancelReq(payment_id=p.id, receivable_id=r.id)
    )
    assert cancel_resp.payment_id == p.id
    assert cancel_resp.payment_status == "pending"  # 回到 pending
    assert cancel_resp.payment_matched_amount == Decimal(0)
    assert cancel_resp.total_reversed == Decimal("10000.00")
    assert len(cancel_resp.results) == 1
    item = cancel_resp.results[0]
    assert item.receivable_id == r.id
    assert item.reversed_amount == Decimal("10000.00")
    assert item.paid_amount == Decimal(0)
    assert item.status == "pending"

    # DB 验证
    rdb = await service.db.get(Receivable, r.id)
    pdb = await service.db.get(Payment, p.id)
    assert rdb.status == "pending"
    assert rdb.paid_amount == Decimal(0)
    assert pdb.status == "pending"
    assert pdb.matched_amount == Decimal(0)


# ===========================================================================
# 7. 核销历史记录（confirm + cancel 都进 _history）
# ===========================================================================


@pytest.mark.asyncio
async def test_history_recorded(service, make_receivable, make_payment):
    """核销历史：confirm 1 笔 + cancel 1 笔 → _history 至少 2 条。"""
    r = await make_receivable(
        node_name="首款", amount=Decimal("10000.00"), company_id=100
    )
    p = await make_payment(
        amount=Decimal("10000.00"), company_id=100
    )

    # confirm
    await service.confirm(
        ConfirmReq(
            payment_id=p.id,
            matches=[ConfirmMatchItem(receivable_id=r.id, amount=Decimal("10000.00"))],
        )
    )
    # cancel
    await service.cancel(
        CancelReq(payment_id=p.id, receivable_id=r.id)
    )

    # 拉历史（不过滤 payment_id）
    hist = await service.history()
    # confirm 写 1 条明细 + cancel 写 1 条明细 = 2 条
    assert hist.total == 2

    actions = sorted([h.action for h in hist.items])
    assert actions == ["cancel", "confirm"]

    # 第一条（id 最小）应为 confirm，第二条为 cancel
    sorted_asc = sorted(hist.items, key=lambda x: x.id)
    assert sorted_asc[0].action == "confirm"
    assert sorted_asc[0].payment_id == p.id
    assert sorted_asc[0].receivable_id == r.id
    assert sorted_asc[0].amount == Decimal("10000.00")
    assert sorted_asc[0].payment_status_before == "pending"
    assert sorted_asc[0].payment_status_after == "matched"
    assert sorted_asc[1].action == "cancel"
    assert sorted_asc[1].payment_status_before == "matched"
    assert sorted_asc[1].payment_status_after == "pending"

    # 按 payment_id 过滤
    hist_by_pid = await service.history(payment_id=p.id)
    assert hist_by_pid.total == 2

    # 按 action 过滤
    hist_confirm = await service.history(action="confirm")
    assert hist_confirm.total == 1
    assert hist_confirm.items[0].action == "confirm"


# ===========================================================================
# 8. 未核销汇总
# ===========================================================================


@pytest.mark.asyncio
async def test_unmatched_summary(service, make_receivable, make_payment):
    """未核销汇总：分别拉 payments + receivables，校验金额合计。"""
    # 2 个应收（都未收齐）
    r1 = await make_receivable(
        node_name="首款", amount=Decimal("10000.00"), company_id=100
    )
    r2 = await make_receivable(
        node_name="尾款", amount=Decimal("20000.00"), company_id=100
    )
    # 1 个应收已收齐（不计入）
    r_paid = await make_receivable(
        node_name="验收款", amount=Decimal("5000.00"), company_id=100,
        paid_amount=Decimal("5000.00"), status="paid",
    )

    # 1 个实收未核销
    p1 = await make_payment(
        amount=Decimal("10000.00"), company_id=100
    )
    # 1 个实收部分核销（不计入：matched_amount < amount 且 status=partial → 仍计入）
    p_partial = await make_payment(
        amount=Decimal("20000.00"),
        company_id=100,
        matched_amount=Decimal("5000.00"),
        status="partial",
    )
    # 1 个实收已完全核销（不计入）
    p_matched = await make_payment(
        amount=Decimal("3000.00"),
        company_id=100,
        matched_amount=Decimal("3000.00"),
        status="matched",
    )

    resp = await service.unmatched()

    # payments: p1 (10000) + p_partial (20000-5000=15000) = 2 条
    assert resp.payment_count == 2
    assert resp.payment_unmatched_total == Decimal("25000.00")
    pay_ids = {p.id for p in resp.payments}
    assert pay_ids == {p1.id, p_partial.id}
    # 显式校验已核销实收 / 部分核销实收的排除规则
    assert p_matched.id not in pay_ids

    # receivables: r1 (10000) + r2 (20000) = 2 条（r_paid 不计）
    assert resp.receivable_count == 2
    assert resp.receivable_outstanding_total == Decimal("30000.00")
    recv_ids = {r.id for r in resp.receivables}
    assert recv_ids == {r1.id, r2.id}
    # 显式校验已收齐应收的排除规则
    assert r_paid.id not in recv_ids

    # 部分核销 payment 的 unmatched_amount 字段正确
    partial_item = next(p for p in resp.payments if p.id == p_partial.id)
    assert partial_item.unmatched_amount == Decimal("15000.00")
    pending_item = next(p for p in resp.payments if p.id == p1.id)
    assert pending_item.unmatched_amount == Decimal("10000.00")


# ===========================================================================
# 9. payment status 自动转换（pending → partial → matched）
# ===========================================================================


@pytest.mark.asyncio
async def test_payment_status_transitions(service, make_receivable, make_payment):
    """实收状态机：matched_amount 从 0 → 5000 → 10000 时 status 应跟随变化。

    路径：pending (matched=0) → partial (matched=5000, amount=10000) → matched (matched=10000)
    """
    # 实收 10000
    p = await make_payment(amount=Decimal("10000.00"), company_id=100)
    assert p.status == "pending"
    assert p.matched_amount == Decimal(0)

    # 应收 1 = 5000, 应收 2 = 5000
    r1 = await make_receivable(
        node_name="首款", amount=Decimal("5000.00"), company_id=100
    )
    r2 = await make_receivable(
        node_name="尾款", amount=Decimal("5000.00"), company_id=100
    )

    # 第一次 confirm 5000 → status 应为 partial
    resp1 = await service.confirm(
        ConfirmReq(
            payment_id=p.id,
            matches=[ConfirmMatchItem(receivable_id=r1.id, amount=Decimal("5000.00"))],
        )
    )
    assert resp1.payment_status == "partial"
    assert resp1.payment_matched_amount == Decimal("5000.00")
    assert resp1.payment_remaining == Decimal("5000.00")

    pdb = await service.db.get(Payment, p.id)
    assert pdb.status == "partial"
    assert pdb.matched_amount == Decimal("5000.00")

    # 第二次 confirm 5000 → status 应为 matched
    resp2 = await service.confirm(
        ConfirmReq(
            payment_id=p.id,
            matches=[ConfirmMatchItem(receivable_id=r2.id, amount=Decimal("5000.00"))],
        )
    )
    assert resp2.payment_status == "matched"
    assert resp2.payment_matched_amount == Decimal("10000.00")
    assert resp2.payment_remaining == Decimal(0)

    pdb2 = await service.db.get(Payment, p.id)
    assert pdb2.status == "matched"

    # 取消一笔后，状态应回到 partial
    cancel_resp = await service.cancel(
        CancelReq(payment_id=p.id, receivable_id=r2.id)
    )
    assert cancel_resp.payment_status == "partial"
    pdb3 = await service.db.get(Payment, p.id)
    assert pdb3.status == "partial"
    assert pdb3.matched_amount == Decimal("5000.00")


# ===========================================================================
# 10. receivable status 自动转换（pending → partial → paid）
# ===========================================================================


@pytest.mark.asyncio
async def test_receivable_status_transitions(service, make_receivable, make_payment):
    """应收状态机：paid_amount 从 0 → 5000 → 10000 时 status 应跟随变化。

    路径：pending → partial → paid
    """
    # 应收 10000
    r = await make_receivable(
        node_name="验收款", amount=Decimal("10000.00"), company_id=100
    )
    assert r.status == "pending"
    assert r.paid_amount == Decimal(0)

    # 实收 1 = 5000, 实收 2 = 5000
    p1 = await make_payment(amount=Decimal("5000.00"), company_id=100)
    p2 = await make_payment(amount=Decimal("5000.00"), company_id=100)

    # 第一次 confirm 5000 → partial
    resp1 = await service.confirm(
        ConfirmReq(
            payment_id=p1.id,
            matches=[ConfirmMatchItem(receivable_id=r.id, amount=Decimal("5000.00"))],
        )
    )
    assert resp1.results[0].status == "partial"
    assert resp1.results[0].paid_amount == Decimal("5000.00")
    assert resp1.results[0].outstanding_amount == Decimal("5000.00")

    rdb = await service.db.get(Receivable, r.id)
    assert rdb.status == "partial"
    assert rdb.paid_amount == Decimal("5000.00")

    # 第二次 confirm 5000 → paid
    resp2 = await service.confirm(
        ConfirmReq(
            payment_id=p2.id,
            matches=[ConfirmMatchItem(receivable_id=r.id, amount=Decimal("5000.00"))],
        )
    )
    assert resp2.results[0].status == "paid"
    assert resp2.results[0].paid_amount == Decimal("10000.00")
    assert resp2.results[0].outstanding_amount == Decimal(0)

    rdb2 = await service.db.get(Receivable, r.id)
    assert rdb2.status == "paid"

    # 取消后应收回到 partial
    cancel_resp = await service.cancel(
        CancelReq(payment_id=p2.id, receivable_id=r.id)
    )
    assert cancel_resp.results[0].status == "partial"
    rdb3 = await service.db.get(Receivable, r.id)
    assert rdb3.status == "partial"
    assert rdb3.paid_amount == Decimal("5000.00")


# ===========================================================================
# 补充测试：cancel_all（整笔回退）
# ===========================================================================


@pytest.mark.asyncio
async def test_cancel_all(service, make_receivable, make_payment):
    """cancel_all=True：把 payment 上的所有配对一次性回退。"""
    r1 = await make_receivable(
        node_name="首款", amount=Decimal("3000.00"), company_id=100
    )
    r2 = await make_receivable(
        node_name="尾款", amount=Decimal("4000.00"), company_id=100
    )
    p = await make_payment(amount=Decimal("7000.00"), company_id=100)

    # confirm 两笔
    await service.confirm(
        ConfirmReq(
            payment_id=p.id,
            matches=[
                ConfirmMatchItem(receivable_id=r1.id, amount=Decimal("3000.00")),
                ConfirmMatchItem(receivable_id=r2.id, amount=Decimal("4000.00")),
            ],
        )
    )
    pdb = await service.db.get(Payment, p.id)
    assert pdb.status == "matched"

    # cancel_all
    resp = await service.cancel(
        CancelReq(payment_id=p.id, cancel_all=True)
    )
    assert resp.total_reversed == Decimal("7000.00")
    assert resp.payment_status == "pending"
    assert resp.payment_matched_amount == Decimal(0)
    assert len(resp.results) == 2

    pdb2 = await service.db.get(Payment, p.id)
    assert pdb2.matched_amount == Decimal(0)
    r1db = await service.db.get(Receivable, r1.id)
    r2db = await service.db.get(Receivable, r2.id)
    assert r1db.paid_amount == Decimal(0)
    assert r2db.paid_amount == Decimal(0)
    assert r1db.status == "pending"
    assert r2db.status == "pending"
