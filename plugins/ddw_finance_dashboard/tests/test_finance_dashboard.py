from __future__ import annotations

"""DDW 财务看板插件测试用例（≥6 个）。

覆盖：overview（空/有数据）、overdue、trend、stats、outstanding_by_company。
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from plugins.ddw_company_profile.models import Company
from plugins.ddw_contract_core.models import Contract
from plugins.ddw_offline_pos.models import Payment
from plugins.ddw_receivable.models import Receivable

# ---------------------------------------------------------------------------
# 内部 helper
# ---------------------------------------------------------------------------


async def _seed_company(db, **overrides) -> Company:
    """插入一个最小可行 Company。"""
    defaults = dict(
        tenant_id=1,
        name="测试企业 X",
        status="active",
        certification_status="pending",
        tags=[],
    )
    defaults.update(overrides)
    obj = Company(**defaults)
    db.add(obj)
    await db.flush()
    return obj


async def _seed_contract(db, **overrides) -> Contract:
    """插入一个最小可行 Contract。"""
    defaults = dict(
        tenant_id=1,
        contract_no="CT-TEST-0001",
        contract_type="standard",
        total_amount=Decimal("1000.00"),
        currency="CNY",
        version=1,
        status="draft",
    )
    defaults.update(overrides)
    obj = Contract(**defaults)
    db.add(obj)
    await db.flush()
    return obj


async def _seed_receivable(db, **overrides) -> Receivable:
    """插入一个最小可行 Receivable。"""
    defaults = dict(
        tenant_id=1,
        node_name="首款",
        amount=Decimal("1000.00"),
        paid_amount=Decimal("0"),
        due_date=date.today() + timedelta(days=30),
        status="pending",
    )
    defaults.update(overrides)
    obj = Receivable(**defaults)
    db.add(obj)
    await db.flush()
    return obj


async def _seed_payment(db, **overrides) -> Payment:
    """插入一个最小可行 Payment。"""
    defaults = dict(
        tenant_id=1,
        payment_no="PAY-TEST-0001",
        payer_name="测试客户公司",
        amount=Decimal("1000.00"),
        payment_date=date.today(),
        payment_method="bank",
        status="pending",
        matched_amount=Decimal("0"),
    )
    defaults.update(overrides)
    obj = Payment(**defaults)
    db.add(obj)
    await db.flush()
    return obj


# ===========================================================================
# 1. overview（空库）
# ===========================================================================


@pytest.mark.asyncio
async def test_overview_empty(service):
    """空数据下总览：所有计数为 0，金额为 0。"""
    r = await service.overview(tenant_id=1)
    assert r.tenant_id == 1
    # 合同
    assert r.contracts_total == 0
    assert r.contracts_signed == 0
    assert r.contracts_total_amount == Decimal("0")
    assert r.contracts_signed_amount == Decimal("0")
    # 应收
    assert r.receivables_total == 0
    assert r.receivables_total_amount == Decimal("0")
    assert r.receivables_paid_amount == Decimal("0")
    assert r.receivables_outstanding_amount == Decimal("0")
    # 实收
    assert r.payments_total == 0
    assert r.payments_total_amount == Decimal("0")
    assert r.payments_matched_amount == Decimal("0")
    assert r.payments_unmatched_amount == Decimal("0")
    # 逾期
    assert r.overdue_count == 0
    assert r.overdue_amount == Decimal("0")


# ===========================================================================
# 2. overview（造数据后）
# ===========================================================================


@pytest.mark.asyncio
async def test_overview_with_data(seeded_db, service):
    """造数据后总览：合同/应收/实收/逾期金额汇总正确。"""
    db = seeded_db

    # 2 个企业
    c1 = await _seed_company(db, name="A 公司")
    c2 = await _seed_company(db, name="B 公司")

    # 3 个合同：1 draft / 1 signed / 1 active → 2 个算 signed
    await _seed_contract(
        db, contract_no="CT-001", status="draft", total_amount=Decimal("1000")
    )
    await _seed_contract(
        db, contract_no="CT-002", status="signed", total_amount=Decimal("3000"),
        company_id=c1.id,
    )
    await _seed_contract(
        db, contract_no="CT-003", status="active", total_amount=Decimal("5000"),
        company_id=c2.id,
    )

    # 4 个应收：1 pending / 1 partial / 1 paid / 1 overdue
    await _seed_receivable(
        db, node_name="r1-pending", company_id=c1.id,
        amount=Decimal("100"), paid_amount=Decimal("0"), status="pending",
    )
    await _seed_receivable(
        db, node_name="r2-partial", company_id=c1.id,
        amount=Decimal("200"), paid_amount=Decimal("50"), status="partial",
    )
    await _seed_receivable(
        db, node_name="r3-paid", company_id=c2.id,
        amount=Decimal("400"), paid_amount=Decimal("400"), status="paid",
    )
    await _seed_receivable(
        db, node_name="r4-overdue", company_id=c2.id,
        amount=Decimal("800"), paid_amount=Decimal("200"), status="overdue",
    )

    # 3 个实收：1 pending / 1 matched / 1 partial
    await _seed_payment(
        db, payment_no="PAY-001", company_id=c1.id,
        amount=Decimal("100"), status="pending", matched_amount=Decimal("0"),
    )
    await _seed_payment(
        db, payment_no="PAY-002", company_id=c1.id,
        amount=Decimal("300"), status="matched", matched_amount=Decimal("300"),
    )
    await _seed_payment(
        db, payment_no="PAY-003", company_id=c2.id,
        amount=Decimal("200"), status="partial", matched_amount=Decimal("100"),
    )

    await db.commit()

    r = await service.overview(tenant_id=1)

    # 合同：3 个 / 2 个 signed / 9000 / 8000
    assert r.contracts_total == 3
    assert r.contracts_signed == 2
    assert r.contracts_total_amount == Decimal("9000")
    assert r.contracts_signed_amount == Decimal("8000")

    # 应收：4 条 / 100+200+400+800=1500 / 0+50+400+200=650 / 850
    assert r.receivables_total == 4
    assert r.receivables_total_amount == Decimal("1500")
    assert r.receivables_paid_amount == Decimal("650")
    assert r.receivables_outstanding_amount == Decimal("850")

    # 实收：3 条 / 100+300+200=600 / 0+300+100=400 / 200
    assert r.payments_total == 3
    assert r.payments_total_amount == Decimal("600")
    assert r.payments_matched_amount == Decimal("400")
    assert r.payments_unmatched_amount == Decimal("200")

    # 逾期：1 条 / 未收 = 800-200=600
    assert r.overdue_count == 1
    assert r.overdue_amount == Decimal("600")


# ===========================================================================
# 3. overdue
# ===========================================================================


@pytest.mark.asyncio
async def test_overdue_list(seeded_db, service):
    """逾期列表：造几条 overdue，验证按未收金额降序 + 总额 + 企业名。"""
    db = seeded_db

    c1 = await _seed_company(db, name="锐果互动")
    c2 = await _seed_company(db, name="武汉某科技公司")

    # 4 个 overdue：未收金额 = 1000 / 500 / 2000 / 100
    await _seed_receivable(
        db, node_name="r1", company_id=c1.id,
        amount=Decimal("1000"), paid_amount=Decimal("0"),
        due_date=date.today() - timedelta(days=10), status="overdue",
    )
    await _seed_receivable(
        db, node_name="r2", company_id=c2.id,
        amount=Decimal("1000"), paid_amount=Decimal("500"),
        due_date=date.today() - timedelta(days=20), status="overdue",
    )
    await _seed_receivable(
        db, node_name="r3", company_id=c1.id,
        amount=Decimal("3000"), paid_amount=Decimal("1000"),
        due_date=date.today() - timedelta(days=5), status="overdue",
    )
    await _seed_receivable(
        db, node_name="r4", company_id=c2.id,
        amount=Decimal("500"), paid_amount=Decimal("400"),
        due_date=date.today() - timedelta(days=30), status="overdue",
    )

    # 1 个非 overdue：不应出现在结果里
    await _seed_receivable(
        db, node_name="non-overdue", company_id=c1.id,
        amount=Decimal("9999"), paid_amount=Decimal("0"),
        due_date=date.today() + timedelta(days=10), status="pending",
    )

    await db.commit()

    r = await service.overdue(tenant_id=1, limit=100)

    # 4 个 overdue
    assert r.total == 4
    assert len(r.items) == 4

    # 总额：1000 + 500 + 2000 + 100 = 3600
    assert r.total_overdue_amount == Decimal("3600")

    # 按未收金额降序：r3(2000) > r1(1000) > r2(500) > r4(100)
    assert r.items[0].node_name == "r3"
    assert r.items[0].outstanding_amount == Decimal("2000")
    assert r.items[1].node_name == "r1"
    assert r.items[1].outstanding_amount == Decimal("1000")
    assert r.items[2].node_name == "r2"
    assert r.items[2].outstanding_amount == Decimal("500")
    assert r.items[3].node_name == "r4"
    assert r.items[3].outstanding_amount == Decimal("100")

    # LEFT JOIN 拿到企业名
    assert r.items[0].company_name == "锐果互动"
    assert r.items[2].company_name == "武汉某科技公司"

    # 验证 outstanding_amount = amount - paid_amount
    for it in r.items:
        assert it.outstanding_amount == it.amount - it.paid_amount

    # 非 overdue 不在结果里
    assert all(it.node_name != "non-overdue" for it in r.items)


# ===========================================================================
# 4. trend
# ===========================================================================


@pytest.mark.asyncio
async def test_trend_data(seeded_db, service):
    """趋势：造不同月份的应收 + 实收，验证按月聚合 + 缺失月份补 0。"""
    db = seeded_db

    now = datetime.now()

    # 当月：1 笔应收 (200) + 1 笔实收 (100)
    await _seed_receivable(
        db, node_name="cur-recv",
        amount=Decimal("200"),
        due_date=date(now.year, now.month, 15),
    )
    await _seed_payment(
        db, payment_no="PAY-CUR-001",
        amount=Decimal("100"),
        payment_date=date(now.year, now.month, 20),
    )

    # 3 个月前：1 笔应收 (500) + 1 笔实收 (300)
    if now.month >= 4:
        old_year, old_month = now.year, now.month - 3
    else:
        old_year, old_month = now.year - 1, now.month + 9
    await _seed_receivable(
        db, node_name="old-recv",
        amount=Decimal("500"),
        due_date=date(old_year, old_month, 10),
    )
    await _seed_payment(
        db, payment_no="PAY-OLD-001",
        amount=Decimal("300"),
        payment_date=date(old_year, old_month, 25),
    )

    # 6 个月前：只 1 笔应收 (700)，无实收
    if now.month >= 7:
        mid_year, mid_month = now.year, now.month - 6
    else:
        mid_year, mid_month = now.year - 1, now.month + 6
    await _seed_receivable(
        db, node_name="mid-recv",
        amount=Decimal("700"),
        due_date=date(mid_year, mid_month, 5),
    )

    # 13 个月前：超窗口，不应出现
    if now.month == 1:
        far_year, far_month = now.year - 2, 12
    else:
        far_year, far_month = now.year - 1, now.month - 1
    await _seed_receivable(
        db, node_name="far-recv",
        amount=Decimal("9999"),
        due_date=date(far_year, far_month, 1),
    )

    await db.commit()

    r = await service.trend(tenant_id=1, months=12)

    assert r.months == 12
    assert len(r.items) == 12

    # 月份升序 + 格式
    import re

    pat = re.compile(r"^\d{4}-\d{2}$")
    assert all(pat.match(it.month) for it in r.items)
    months_sorted = sorted(r.items, key=lambda x: x.month)
    assert [it.month for it in r.items] == [it.month for it in months_sorted]

    # 当月：200 / 100 / 100
    cur_item = r.items[-1]
    assert cur_item.receivable_amount == Decimal("200")
    assert cur_item.payment_amount == Decimal("100")
    assert cur_item.net == Decimal("100")

    # 找到 3 个月前那个月 → 应收 500 / 实收 300 / net 200
    anchor_month = date(now.year, now.month, 1)
    target_old = date(old_year, old_month, 1)
    diff_old = (anchor_month.year - target_old.year) * 12 + (
        anchor_month.month - target_old.month
    )
    old_item = r.items[12 - 1 - diff_old]
    assert old_item.receivable_amount == Decimal("500")
    assert old_item.payment_amount == Decimal("300")
    assert old_item.net == Decimal("200")

    # 找到 6 个月前那个月 → 应收 700 / 实收 0 / net 700
    target_mid = date(mid_year, mid_month, 1)
    diff_mid = (anchor_month.year - target_mid.year) * 12 + (
        anchor_month.month - target_mid.month
    )
    mid_item = r.items[12 - 1 - diff_mid]
    assert mid_item.receivable_amount == Decimal("700")
    assert mid_item.payment_amount == Decimal("0")
    assert mid_item.net == Decimal("700")

    # 缺失月份补 0
    zero_count = sum(
        1 for it in r.items
        if it.receivable_amount == Decimal("0") and it.payment_amount == Decimal("0")
    )
    assert zero_count >= 8  # 12 - 3 个有数据的 = 9，但远期的不算 12 月内

    # 13 个月前的应收（9999）不在 12 月窗口里
    total_recv_12m = sum(it.receivable_amount for it in r.items)
    assert total_recv_12m == Decimal("1400")  # 200 + 500 + 700


# ===========================================================================
# 5. stats（按状态分布）
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_distribution(seeded_db, service):
    """统计：验证各状态分布。"""
    db = seeded_db

    c1 = await _seed_company(db, name="A 公司")
    c2 = await _seed_company(db, name="B 公司")

    # 合同 5 个：1 draft / 1 approved / 2 signed / 1 completed
    await _seed_contract(db, contract_no="CT-D-001", status="draft",
                         total_amount=Decimal("100"))
    await _seed_contract(db, contract_no="CT-A-001", status="approved",
                         total_amount=Decimal("200"), company_id=c1.id)
    await _seed_contract(db, contract_no="CT-S-001", status="signed",
                         total_amount=Decimal("300"), company_id=c1.id)
    await _seed_contract(db, contract_no="CT-S-002", status="signed",
                         total_amount=Decimal("400"), company_id=c2.id)
    await _seed_contract(db, contract_no="CT-C-001", status="completed",
                         total_amount=Decimal("500"), company_id=c2.id)

    # 应收 5 个：2 pending / 1 partial / 1 paid / 1 overdue
    await _seed_receivable(db, node_name="p1", company_id=c1.id,
                           amount=Decimal("100"), paid_amount=Decimal("0"),
                           status="pending")
    await _seed_receivable(db, node_name="p2", company_id=c2.id,
                           amount=Decimal("200"), paid_amount=Decimal("0"),
                           status="pending")
    await _seed_receivable(db, node_name="pt", company_id=c1.id,
                           amount=Decimal("300"), paid_amount=Decimal("100"),
                           status="partial")
    await _seed_receivable(db, node_name="pd", company_id=c2.id,
                           amount=Decimal("400"), paid_amount=Decimal("400"),
                           status="paid")
    await _seed_receivable(db, node_name="od", company_id=c1.id,
                           amount=Decimal("500"), paid_amount=Decimal("200"),
                           status="overdue")

    # 实收 4 个：1 pending / 1 partial / 1 matched / 1 unmatched
    await _seed_payment(db, payment_no="PAY-P", company_id=c1.id,
                        amount=Decimal("100"), status="pending",
                        matched_amount=Decimal("0"))
    await _seed_payment(db, payment_no="PAY-PT", company_id=c1.id,
                        amount=Decimal("200"), status="partial",
                        matched_amount=Decimal("100"))
    await _seed_payment(db, payment_no="PAY-M", company_id=c2.id,
                        amount=Decimal("300"), status="matched",
                        matched_amount=Decimal("300"))
    await _seed_payment(db, payment_no="PAY-U", company_id=c2.id,
                        amount=Decimal("400"), status="unmatched",
                        matched_amount=Decimal("0"))

    await db.commit()

    r = await service.stats(tenant_id=1)

    # ---- 合同分布 ----
    assert r.contracts_by_status["draft"] == 1
    assert r.contracts_by_status["approved"] == 1
    assert r.contracts_by_status["signed"] == 2
    assert r.contracts_by_status["completed"] == 1
    # 合同金额：100+200+300+400+500=1500
    assert sum(r.contracts_amount_by_status.values()) == Decimal("1500")
    assert r.contracts_amount_by_status["signed"] == Decimal("700")
    assert r.contracts_amount_by_status["completed"] == Decimal("500")

    # ---- 应收分布 ----
    assert r.receivables_by_status["pending"] == 2
    assert r.receivables_by_status["partial"] == 1
    assert r.receivables_by_status["paid"] == 1
    assert r.receivables_by_status["overdue"] == 1
    # 应收金额：100+200+300+400+500=1500
    assert sum(r.receivables_amount_by_status.values()) == Decimal("1500")
    # 应收未收金额：(100-0)+(200-0)+(300-100)+(400-400)+(500-200) = 100+200+200+0+300 = 800
    assert r.receivables_outstanding_by_status["pending"] == Decimal("300")
    assert r.receivables_outstanding_by_status["partial"] == Decimal("200")
    assert r.receivables_outstanding_by_status["paid"] == Decimal("0")
    assert r.receivables_outstanding_by_status["overdue"] == Decimal("300")
    assert sum(r.receivables_outstanding_by_status.values()) == Decimal("800")

    # ---- 实收分布 ----
    assert r.payments_by_status["pending"] == 1
    assert r.payments_by_status["partial"] == 1
    assert r.payments_by_status["matched"] == 1
    assert r.payments_by_status["unmatched"] == 1
    # 实收金额：100+200+300+400=1000
    assert sum(r.payments_amount_by_status.values()) == Decimal("1000")
    assert r.payments_amount_by_status["matched"] == Decimal("300")


# ===========================================================================
# 6. outstanding_by_company（按企业未收金额）
# ===========================================================================


@pytest.mark.asyncio
async def test_outstanding_by_company(seeded_db, service):
    """按企业分组未收金额：验证汇总 + 排序。"""
    db = seeded_db

    c1 = await _seed_company(db, name="客户 A")
    c2 = await _seed_company(db, name="客户 B")
    c3 = await _seed_company(db, name="客户 C")

    # 客户 A：2 笔未付清 = 1000 + 500 = 1500
    await _seed_receivable(
        db, node_name="a1", company_id=c1.id,
        amount=Decimal("1000"), paid_amount=Decimal("0"), status="pending",
    )
    await _seed_receivable(
        db, node_name="a2", company_id=c1.id,
        amount=Decimal("800"), paid_amount=Decimal("300"), status="partial",
    )

    # 客户 B：1 笔逾期 = 2000
    await _seed_receivable(
        db, node_name="b1", company_id=c2.id,
        amount=Decimal("2000"), paid_amount=Decimal("0"), status="overdue",
    )

    # 客户 C：1 笔已付清 → 不计
    await _seed_receivable(
        db, node_name="c1", company_id=c3.id,
        amount=Decimal("500"), paid_amount=Decimal("500"), status="paid",
    )

    # 1 笔无企业的应收（应出现在 company_id=None 的桶里）
    await _seed_receivable(
        db, node_name="orphan",
        company_id=None,
        amount=Decimal("300"), paid_amount=Decimal("0"), status="pending",
    )

    await db.commit()

    r = await service.stats(tenant_id=1)

    # 3 个 company_id 桶（B, A, orphan；C 已是 paid 被筛选掉）
    assert len(r.receivables_outstanding_by_company) == 3

    # 排序：按 outstanding_amount 降序
    # B(2000) > A(1500) > orphan(300)
    assert r.receivables_outstanding_by_company[0].company_id == c2.id
    assert r.receivables_outstanding_by_company[0].company_name == "客户 B"
    assert r.receivables_outstanding_by_company[0].outstanding_amount == Decimal("2000")
    assert r.receivables_outstanding_by_company[0].receivable_count == 1

    assert r.receivables_outstanding_by_company[1].company_id == c1.id
    assert r.receivables_outstanding_by_company[1].company_name == "客户 A"
    assert r.receivables_outstanding_by_company[1].outstanding_amount == Decimal("1500")
    assert r.receivables_outstanding_by_company[1].receivable_count == 2

    # 第 3 位：orphan
    assert r.receivables_outstanding_by_company[2].company_id is None
    assert r.receivables_outstanding_by_company[2].company_name is None
    assert r.receivables_outstanding_by_company[2].outstanding_amount == Decimal("300")
    assert r.receivables_outstanding_by_company[2].receivable_count == 1

    # 客户 C：paid 不计入未收，所以不在 list 里
    # 实际上：未付清筛选条件 status in (pending, partial, overdue) 会过滤掉 paid
    # 因此 C 不应在结果里
    company_ids = {it.company_id for it in r.receivables_outstanding_by_company}
    assert c3.id not in company_ids
