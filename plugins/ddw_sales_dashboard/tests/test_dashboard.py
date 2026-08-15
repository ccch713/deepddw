from __future__ import annotations

from typing import Optional

"""DDW 销售看板插件测试用例（≥7 个）。

覆盖：overview（空/有数据）、funnel、trend、ranking、recent、stage_distribution。
"""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import update

from plugins.ddw_company_profile.models import Company
from plugins.ddw_contact_hub.models import Contact
from plugins.ddw_opportunity.models import Opportunity
from plugins.ddw_opportunity.services import STAGE_DISPLAY_ORDER
from plugins.ddw_quotation.models import Quotation

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


async def _seed_contact(db, company_id: Optional[int] = None, **overrides) -> Contact:
    """插入一个最小可行 Contact。"""
    defaults = dict(
        tenant_id=1,
        name="测试联系人",
        status="active",
        company_id=company_id,
        tags=[],
    )
    defaults.update(overrides)
    obj = Contact(**defaults)
    db.add(obj)
    await db.flush()
    return obj


async def _seed_opportunity(db, **overrides) -> Opportunity:
    """插入一个最小可行 Opportunity。"""
    defaults = dict(
        tenant_id=1,
        name="测试商机",
        stage="initial_contact",
        status="open",
        probability=10,
        tags=[],
        estimated_amount=Decimal("100.00"),
        owner_id=1,
    )
    defaults.update(overrides)
    obj = Opportunity(**defaults)
    db.add(obj)
    await db.flush()
    return obj


async def _seed_quotation(db, **overrides) -> Quotation:
    """插入一个最小可行 Quotation（无 items 子表）。"""
    from plugins.ddw_quotation.models import QuotationItem  # noqa: F401  触发建表

    defaults = dict(
        tenant_id=1,
        quotation_no="QT-TEST-001",
        status="draft",
        currency="CNY",
        total_amount=Decimal("1000.00"),
        final_amount=Decimal("1000.00"),
        discount_rate=Decimal("100"),
    )
    defaults.update(overrides)
    obj = Quotation(**defaults)
    db.add(obj)
    await db.flush()
    return obj


# ===========================================================================
# 1. overview（空库）
# ===========================================================================


@pytest.mark.asyncio
async def test_overview_empty(service):
    """空数据下总览：所有计数为 0，金额为 0。"""
    result = await service.overview(tenant_id=1)
    assert result.tenant_id == 1
    assert result.companies == 0
    assert result.contacts == 0
    assert result.opportunities == 0
    assert result.quotations == 0
    assert result.estimated_amount == Decimal("0")
    assert result.won_amount == Decimal("0")
    assert result.won_customers == 0
    assert result.open_opportunities == 0
    assert result.won_opportunities == 0
    assert result.lost_opportunities == 0
    assert result.accepted_quotations == 0
    assert result.accepted_amount == Decimal("0")


# ===========================================================================
# 2. overview（造数据后）
# ===========================================================================


@pytest.mark.asyncio
async def test_overview_with_data(seeded_db):
    """造数据后总览：验证计数、金额、去重成交客户。"""
    db = seeded_db
    # 3 个企业
    c1 = await _seed_company(db, name="A 公司")
    c2 = await _seed_company(db, name="B 公司")
    c3 = await _seed_company(db, name="C 公司")
    # 4 个联系人
    for i in range(4):
        await _seed_contact(db, name=f"联系人 {i}")
    # 5 个商机：3 open / 1 won (c1) / 1 lost (c2)
    await _seed_opportunity(
        db, name="op1", company_id=c1.id, status="open",
        stage="initial_contact", estimated_amount=Decimal("100")
    )
    await _seed_opportunity(
        db, name="op2", company_id=c2.id, status="open",
        stage="proposal_submitted", estimated_amount=Decimal("200")
    )
    await _seed_opportunity(
        db, name="op3", company_id=c3.id, status="open",
        stage="negotiation", estimated_amount=Decimal("300")
    )
    await _seed_opportunity(
        db, name="op4-won", company_id=c1.id, status="won",
        stage="won", estimated_amount=Decimal("1000"),
        won_at=datetime(2026, 1, 15, 10, 0, 0),
    )
    await _seed_opportunity(
        db, name="op5-lost", company_id=c2.id, status="lost",
        stage="lost", estimated_amount=Decimal("500"),
    )
    # 2 个报价单：1 draft / 1 accepted
    await _seed_quotation(db, quotation_no="QT-001", status="draft",
                          total_amount=Decimal("100"), final_amount=Decimal("100"))
    await _seed_quotation(db, quotation_no="QT-002", status="accepted",
                          total_amount=Decimal("500"), final_amount=Decimal("450"))
    await db.commit()

    from plugins.ddw_sales_dashboard.services import DashboardService

    svc = DashboardService(db)
    r = await svc.overview(tenant_id=1)
    assert r.companies == 3
    assert r.contacts == 4
    assert r.opportunities == 5
    assert r.quotations == 2
    # 3 个 open 商机：100+200+300=600
    assert r.estimated_amount == Decimal("600")
    # won 商机：1000
    assert r.won_amount == Decimal("1000")
    # 成交客户：c1 一家（c4 不存在）
    assert r.won_customers == 1
    assert r.open_opportunities == 3
    assert r.won_opportunities == 1
    assert r.lost_opportunities == 1
    assert r.accepted_quotations == 1
    assert r.accepted_amount == Decimal("450")


# ===========================================================================
# 3. funnel
# ===========================================================================


@pytest.mark.asyncio
async def test_funnel_data(seeded_db):
    """漏斗：造不同阶段 / 状态的商机，验证分组 + 顺序。"""
    db = seeded_db
    # 5 个商机横跨 5 个阶段（其中 1 won / 1 lost）
    await _seed_opportunity(db, name="a", stage="initial_contact",
                            estimated_amount=Decimal("10"), status="open")
    await _seed_opportunity(db, name="b", stage="demand_confirmation",
                            estimated_amount=Decimal("20"), status="open")
    await _seed_opportunity(db, name="c", stage="quotation_sent",
                            estimated_amount=Decimal("30"), status="open")
    await _seed_opportunity(db, name="d", stage="won",
                            estimated_amount=Decimal("100"), status="won")
    await _seed_opportunity(db, name="e", stage="lost",
                            estimated_amount=Decimal("0"), status="lost")
    await db.commit()

    from plugins.ddw_sales_dashboard.services import DashboardService

    svc = DashboardService(db)
    f = await svc.funnel(tenant_id=1)
    # 严格按 STAGE_DISPLAY_ORDER 输出 8 个阶段
    assert [it.stage for it in f.stages] == STAGE_DISPLAY_ORDER
    assert len(f.stages) == 8
    # 验证 count
    by_stage = {it.stage: it for it in f.stages}
    assert by_stage["initial_contact"].count == 1
    assert by_stage["demand_confirmation"].count == 1
    assert by_stage["quotation_sent"].count == 1
    assert by_stage["won"].count == 1
    assert by_stage["lost"].count == 1
    # 验证 amount
    assert by_stage["initial_contact"].total_amount == Decimal("10")
    assert by_stage["won"].total_amount == Decimal("100")
    # 没有数据的阶段（如 proposal_submitted）count=0, amount=0
    assert by_stage["proposal_submitted"].count == 0
    assert by_stage["proposal_submitted"].total_amount == Decimal("0")
    # 验证 stage_label 已填
    assert by_stage["won"].stage_label == "成交"
    assert by_stage["lost"].stage_label == "丢单"
    # total
    assert f.total == 5
    assert f.total_amount == Decimal("160")  # 10+20+30+100+0


# ===========================================================================
# 4. trend
# ===========================================================================


@pytest.mark.asyncio
async def test_trend_data(seeded_db):
    """趋势：造不同月份的商机，验证按月聚合 + 缺失月份补 0。"""
    db = seeded_db
    # 当月 2 条
    now = datetime.now()
    cur = now.replace(microsecond=0)
    cur_last = now.replace(day=28, hour=10, minute=0, second=0, microsecond=0)
    await _seed_opportunity(db, name="cur1", created_at=cur,
                            estimated_amount=Decimal("100"), status="open")
    await _seed_opportunity(db, name="cur2", created_at=cur_last,
                            estimated_amount=Decimal("200"), status="open")
    # 3 个月前 1 条
    o_old = await _seed_opportunity(db, name="old1",
                                     estimated_amount=Decimal("500"), status="open")
    # 直接 UPDATE created_at 到 3 个月前
    if now.month >= 4:
        old_dt = now.replace(year=now.year, month=now.month - 3, day=15, hour=10, minute=0, second=0, microsecond=0)
    else:
        old_dt = now.replace(year=now.year - 1, month=now.month + 9, day=15, hour=10, minute=0, second=0, microsecond=0)
    await db.execute(
        update(Opportunity).where(Opportunity.id == o_old.id).values(created_at=old_dt)
    )
    # 5 个月前 1 条（已成交）
    o_won = await _seed_opportunity(db, name="won-old",
                                    estimated_amount=Decimal("999"),
                                    status="won", stage="won")
    if now.month >= 6:
        won_dt = now.replace(year=now.year, month=now.month - 5, day=10, hour=10, minute=0, second=0, microsecond=0)
    else:
        won_dt = now.replace(year=now.year - 1, month=now.month + 7, day=10, hour=10, minute=0, second=0, microsecond=0)
    await db.execute(
        update(Opportunity).where(Opportunity.id == o_won.id).values(
            created_at=won_dt, won_at=won_dt
        )
    )
    await db.commit()

    from plugins.ddw_sales_dashboard.services import DashboardService

    svc = DashboardService(db)
    t = await svc.trend(tenant_id=1, months=12)
    assert t.months == 12
    assert len(t.items) == 12
    # 当前月：2 条，金额 100+200=300，won=0
    cur_item = t.items[-1]
    assert cur_item.new_opportunities == 2
    assert cur_item.total_amount == Decimal("300")
    assert cur_item.won_amount == Decimal("0")
    # 3 个月前：1 条
    # 找到 3 个月前那个月
    from datetime import date as _date

    target_month = _date(old_dt.year, old_dt.month, 1)
    anchor_month = _date(now.year, now.month, 1)
    # 距离 anchor 几个月
    diff_months = (anchor_month.year - target_month.year) * 12 + (anchor_month.month - target_month.month)
    target_item = t.items[12 - 1 - diff_months]  # 倒推
    assert target_item.new_opportunities == 1
    assert target_item.total_amount == Decimal("500")
    # 5 个月前：1 条（已成交，按 won_at 归入此月）
    target_won_month = _date(won_dt.year, won_dt.month, 1)
    diff_won = (anchor_month.year - target_won_month.year) * 12 + (anchor_month.month - target_won_month.month)
    won_item = t.items[12 - 1 - diff_won]
    assert won_item.new_opportunities == 1
    assert won_item.total_amount == Decimal("999")
    assert won_item.won_amount == Decimal("999")
    # 月份连续：所有 month 字段都形如 YYYY-MM
    import re

    pat = re.compile(r"^\d{4}-\d{2}$")
    assert all(pat.match(it.month) for it in t.items)
    # 月份升序
    months_sorted = sorted(t.items, key=lambda x: x.month)
    assert [it.month for it in t.items] == [it.month for it in months_sorted]


# ===========================================================================
# 5. ranking
# ===========================================================================


@pytest.mark.asyncio
async def test_ranking(seeded_db):
    """销售排行：造不同 owner_id 的商机，验证排序和 win_rate。"""
    db = seeded_db
    # owner=10：3 个 open + 1 won + 1 lost
    for i in range(3):
        await _seed_opportunity(db, name=f"10-op{i}", owner_id=10,
                                status="open", stage="initial_contact",
                                estimated_amount=Decimal("100"))
    await _seed_opportunity(db, name="10-won", owner_id=10, status="won",
                            stage="won", estimated_amount=Decimal("500"))
    await _seed_opportunity(db, name="10-lost", owner_id=10, status="lost",
                            stage="lost", estimated_amount=Decimal("0"))
    # owner=20：2 个 open
    await _seed_opportunity(db, name="20-op1", owner_id=20, status="open",
                            stage="negotiation", estimated_amount=Decimal("400"))
    await _seed_opportunity(db, name="20-op2", owner_id=20, status="open",
                            stage="proposal_submitted", estimated_amount=Decimal("300"))
    # owner=30：1 个 open（最弱）
    await _seed_opportunity(db, name="30-op1", owner_id=30, status="open",
                            stage="initial_contact", estimated_amount=Decimal("50"))
    # owner=NULL：不参与排行
    await _seed_opportunity(db, name="no-owner", owner_id=None,
                            status="open", stage="initial_contact",
                            estimated_amount=Decimal("9999"))
    await db.commit()

    from plugins.ddw_sales_dashboard.services import DashboardService

    svc = DashboardService(db)
    r = await svc.ranking(tenant_id=1)
    # 排除 owner=NULL → 3 个 owner
    assert r.total_owners == 3
    assert [it.owner_id for it in r.items] == [10, 20, 30]
    # owner=10: 3 open + 1 won + 1 lost → total=5, est=100*3+500+0=800, won=500, wcnt=1, lcnt=1
    o10 = r.items[0]
    assert o10.total_opportunities == 5
    assert o10.estimated_amount == Decimal("800")
    assert o10.won_amount == Decimal("500")
    assert o10.won_count == 1
    assert o10.lost_count == 1
    assert o10.win_rate == 0.5  # 1 / (1+1)
    # owner=20: 2 open, est=700
    o20 = r.items[1]
    assert o20.total_opportunities == 2
    assert o20.estimated_amount == Decimal("700")
    assert o20.won_count == 0
    assert o20.lost_count == 0
    assert o20.win_rate == 0.0  # 没有终止态 → 0
    # owner=30: 1 open
    o30 = r.items[2]
    assert o30.total_opportunities == 1
    assert o30.estimated_amount == Decimal("50")
    # 排序：800 > 700 > 50 ✓


# ===========================================================================
# 6. recent
# ===========================================================================


@pytest.mark.asyncio
async def test_recent_opportunities(seeded_db):
    """最近商机：造 15 条，取最近 10 条，按 updated_at 倒序。"""
    db = seeded_db
    # 1 个企业供 LEFT JOIN
    c1 = await _seed_company(db, name="锐果互动")

    base = datetime(2026, 1, 1, 0, 0, 0)
    inserted = []
    for i in range(15):
        # 每条商机 created_at 递增 1 天 → updated_at 也递增
        ts = base.replace(day=1 + i) if i < 28 else base.replace(month=2, day=i - 27)
        o = Opportunity(
            tenant_id=1,
            name=f"商机 #{i:02d}",
            stage="initial_contact",
            status="open",
            probability=10,
            estimated_amount=Decimal("100"),
            company_id=c1.id,
            created_at=ts,
            updated_at=ts,
        )
        db.add(o)
        inserted.append(o)
    await db.commit()

    from plugins.ddw_sales_dashboard.services import DashboardService

    svc = DashboardService(db)
    r = await svc.recent(tenant_id=1, limit=10)
    assert r.limit == 10
    assert len(r.items) == 10
    # 按 updated_at 倒序：最后插入的 updated_at 更大 → 应在前面
    # 最后插入的 name 是 商机 #14
    assert r.items[0].name == "商机 #14"
    # 倒数第二个是 #13
    assert r.items[1].name == "商机 #13"
    # LEFT JOIN 拿到企业名
    assert r.items[0].company_name == "锐果互动"
    assert r.items[0].company_id == c1.id
    # stage_label 已填
    assert r.items[0].stage_label == "初步接触"
    # estimated_amount 类型
    assert r.items[0].estimated_amount == Decimal("100")


# ===========================================================================
# 7. stage_distribution
# ===========================================================================


@pytest.mark.asyncio
async def test_stage_distribution(seeded_db):
    """阶段分布：造不同阶段的商机，验证饼图数据结构。"""
    db = seeded_db
    # 3 个 initial_contact，2 个 won
    for i in range(3):
        await _seed_opportunity(db, name=f"ic{i}", stage="initial_contact",
                                status="open", estimated_amount=Decimal("10"))
    for i in range(2):
        await _seed_opportunity(db, name=f"w{i}", stage="won", status="won",
                                estimated_amount=Decimal("100"))
    await db.commit()

    from plugins.ddw_sales_dashboard.services import DashboardService

    svc = DashboardService(db)
    r = await svc.stage_distribution(tenant_id=1)
    assert r.total_count == 5
    assert r.total_amount == Decimal("230")  # 30+200
    # 严格按 STAGE_DISPLAY_ORDER 输出
    assert [it.stage for it in r.items] == STAGE_DISPLAY_ORDER
    by_stage = {it.stage: it for it in r.items}
    assert by_stage["initial_contact"].count == 3
    assert by_stage["initial_contact"].amount == Decimal("30")
    assert by_stage["won"].count == 2
    assert by_stage["won"].amount == Decimal("200")
    assert by_stage["won"].stage_label == "成交"
    # 没有数据的阶段 amount=0
    assert by_stage["lost"].count == 0
    assert by_stage["lost"].amount == Decimal("0")
