from __future__ import annotations

from typing import Optional

"""DDW 续费与预警插件测试用例（≥6 个）。

覆盖：expiring 30/60/90、overdue、quote、stats。
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from plugins.ddw_company_profile.models import Company
from plugins.ddw_contract_core.models import Contract
from plugins.ddw_license_core.models import License

# ---------------------------------------------------------------------------
# 内部 helper
# ---------------------------------------------------------------------------


def _today() -> date:
    """今天（naive UTC）。"""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).date()


async def _seed_company(db, **overrides) -> Company:
    """插入一个最小可行 Company。"""
    defaults = {
        "tenant_id": 1,
        "name": "测试客户公司",
        "status": "active",
        "certification_status": "pending",
        "tags": [],
    }
    defaults.update(overrides)
    obj = Company(**defaults)
    db.add(obj)
    await db.flush()
    return obj


async def _seed_license(
    db,
    company_id: Optional[int] = None,
    idx: str = "X",
    **overrides,
) -> License:
    """插入一个最小可行 License。

    默认：formal / active / 365 天有效 / 10 用户 / 1 节点。
    ``idx`` 用于生成唯一的 license_no（不是主键）。
    """
    today = _today()
    defaults = {
        "tenant_id": 1,
        "license_no": f"LIC-TEST-{idx}",
        "license_type": "formal",
        "plugin_entitlements": ["ddw-crm-core"],
        "max_users": 10,
        "max_nodes": 1,
        "valid_from": today,
        "valid_to": today + timedelta(days=365),
        "status": "active",
        "product_ids": [101],
    }
    defaults.update(overrides)
    if company_id is not None:
        defaults["company_id"] = company_id
    obj = License(**defaults)
    db.add(obj)
    await db.flush()
    return obj


async def _seed_contract(
    db,
    company_id: int,
    total_amount: Decimal,
    days: int = 365,
    idx: str = "X",
    **overrides,
) -> Contract:
    """插入一个最小可行 Contract（active 状态）。"""
    today = _today()
    defaults = {
        "tenant_id": 1,
        "company_id": company_id,
        "contract_no": f"CT-TEST-{idx}",
        "title": "历史合同",
        "contract_type": "standard",
        "total_amount": total_amount,
        "currency": "CNY",
        "effective_from": today - timedelta(days=days),
        "effective_to": today,
        "status": "active",
    }
    defaults.update(overrides)
    obj = Contract(**defaults)
    db.add(obj)
    await db.flush()
    return obj


# ===========================================================================
# 1. expiring（30 天窗口）
# ===========================================================================


@pytest.mark.asyncio
async def test_expiring_30_days(seeded_db):
    """30 天窗口：只返回 active 且 0 <= days_remaining <= 30 的许可证。"""
    db = seeded_db
    c1 = await _seed_company(db, name="A 公司")

    today = _today()
    # 15 天后到期：应被 30/60/90 全部命中
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-15",
        valid_from=today - timedelta(days=350),
        valid_to=today + timedelta(days=15),
    )
    # 45 天后到期：30 天窗口不命中，60/90 命中
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-45",
        valid_from=today - timedelta(days=320),
        valid_to=today + timedelta(days=45),
    )
    # 100 天后到期：30/60/90 都不命中
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-100",
        valid_from=today - timedelta(days=265),
        valid_to=today + timedelta(days=100),
    )
    # 5 天前已过期：30 窗口不命中（已逾期，走 /overdue）
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-EXPIRED",
        valid_from=today - timedelta(days=370),
        valid_to=today - timedelta(days=5),
    )
    # suspended 状态 20 天后到期：30 窗口不命中（非 active）
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-SUSPENDED",
        valid_from=today - timedelta(days=345),
        valid_to=today + timedelta(days=20),
        status="suspended",
    )
    await db.commit()

    from plugins.ddw_renewal.services import RenewalService

    svc = RenewalService(db)
    r = await svc.expiring(tenant_id=1, days=30)
    assert r.tenant_id == 1
    assert r.window_days == 30
    assert r.today == today
    assert r.total == 1
    assert len(r.items) == 1
    # 命中的是 15 天后到期的
    it = r.items[0]
    assert it.license_no == "LIC-15"
    assert it.company_id == c1.id
    assert it.company_name == "A 公司"
    assert it.days_remaining == 15
    assert it.status == "active"


# ===========================================================================
# 2. expiring（60 天窗口）
# ===========================================================================


@pytest.mark.asyncio
async def test_expiring_60_days(seeded_db):
    """60 天窗口：返回 0 <= days_remaining <= 60 的 active 许可证。"""
    db = seeded_db
    c1 = await _seed_company(db, name="B 公司")

    today = _today()
    # 10 天后到期
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-10",
        valid_to=today + timedelta(days=10),
    )
    # 50 天后到期
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-50",
        valid_to=today + timedelta(days=50),
    )
    # 80 天后到期：60 窗口不命中，90 窗口才命中
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-80",
        valid_to=today + timedelta(days=80),
    )
    await db.commit()

    from plugins.ddw_renewal.services import RenewalService

    svc = RenewalService(db)
    r = await svc.expiring(tenant_id=1, days=60)
    assert r.window_days == 60
    assert r.total == 2
    # 按 valid_to 升序：10 天 < 50 天
    assert r.items[0].license_no == "LIC-10"
    assert r.items[1].license_no == "LIC-50"
    # 边界检查：0 天（当天到期）也应命中
    assert r.items[0].days_remaining == 10
    assert r.items[1].days_remaining == 50


# ===========================================================================
# 3. expiring（90 天窗口）
# ===========================================================================


@pytest.mark.asyncio
async def test_expiring_90_days(seeded_db):
    """90 天窗口：返回 0 <= days_remaining <= 90 的 active 许可证。"""
    db = seeded_db
    c1 = await _seed_company(db, name="C 公司")

    today = _today()
    # 30 天后到期
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-30",
        valid_to=today + timedelta(days=30), max_users=20,
    )
    # 70 天后到期
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-70",
        valid_to=today + timedelta(days=70), max_users=30, max_nodes=2,
    )
    # 90 天后到期（边界包含）
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-90",
        valid_to=today + timedelta(days=90), max_users=5, max_nodes=1,
    )
    # 91 天后到期：90 窗口不命中
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-91",
        valid_to=today + timedelta(days=91),
    )
    await db.commit()

    from plugins.ddw_renewal.services import RenewalService

    svc = RenewalService(db)
    r = await svc.expiring(tenant_id=1, days=90)
    assert r.window_days == 90
    assert r.total == 3
    by_no = {it.license_no: it for it in r.items}
    assert "LIC-30" in by_no
    assert "LIC-70" in by_no
    assert "LIC-90" in by_no
    assert "LIC-91" not in by_no
    # 验证 LEFT JOIN 拿到企业名
    assert r.items[0].company_name == "C 公司"
    # 验证 max_users / max_nodes 透传
    assert by_no["LIC-70"].max_users == 30
    assert by_no["LIC-70"].max_nodes == 2


# ===========================================================================
# 4. overdue（已逾期）
# ===========================================================================


@pytest.mark.asyncio
async def test_overdue(seeded_db):
    """已逾期：status IN (active, expired) 且 valid_to < today。"""
    db = seeded_db
    c1 = await _seed_company(db, name="D 公司")

    today = _today()
    # 10 天前到期（status=active：业务上「该过期但没自动标记」）
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-OVD-10",
        valid_to=today - timedelta(days=10),
        status="active",
    )
    # 60 天前到期（status=expired：已被自动标记）
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-OVD-60",
        valid_to=today - timedelta(days=60),
        status="expired",
    )
    # 30 天后到期：未逾期，不应出现
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-FUTURE",
        valid_to=today + timedelta(days=30),
    )
    # 已吊销（revoked）即使过期也不算「业务逾期」：按 spec 不应出现
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-REVOKED",
        valid_to=today - timedelta(days=20),
        status="revoked",
    )
    await db.commit()

    from plugins.ddw_renewal.services import RenewalService

    svc = RenewalService(db)
    r = await svc.overdue(tenant_id=1)
    assert r.tenant_id == 1
    assert r.today == today
    assert r.total == 2
    # 按 valid_to 升序：60 天前 < 10 天前
    assert r.items[0].license_no == "LIC-OVD-60"
    assert r.items[1].license_no == "LIC-OVD-10"
    # 验证 days_overdue
    assert r.items[0].days_overdue == 60
    assert r.items[1].days_overdue == 10
    # LEFT JOIN 拿企业名
    assert r.items[0].company_name == "D 公司"
    # revoked 不应出现
    nos = {it.license_no for it in r.items}
    assert "LIC-REVOKED" not in nos
    assert "LIC-FUTURE" not in nos


# ===========================================================================
# 5. quote（续费报价估算）
# ===========================================================================


@pytest.mark.asyncio
async def test_quote(service_with_company_and_contract):
    """续费报价：基于历史合同单价 × 续费天数。

    场景：
    - 1 个 company (id=100)
    - 1 张历史合同：total=36500 CNY, 365 天 → 单价 100 CNY/天
    - 1 个 license：valid_to - valid_from = 365 天（用历史时长）
    - 估算：100 * 365 = 36500 CNY
    """
    db, license_id = service_with_company_and_contract
    from plugins.ddw_renewal.services import RenewalService

    svc = RenewalService(db)
    quote = await svc.quote(tenant_id=1, license_id=license_id, renewal_unit_days=365)
    assert quote.tenant_id == 1
    assert quote.license_id == license_id
    assert quote.company_id == 100
    assert quote.company_name == "测试客户公司"
    assert quote.currency == "CNY"
    # 36500 CNY
    assert quote.estimated_amount == Decimal("36500.00")
    # breakdown
    assert quote.breakdown.renewal_unit_days == 365
    assert quote.breakdown.historical_unit_price == Decimal("100.0000")
    assert quote.breakdown.historical_contract_id is not None
    assert quote.breakdown.historical_contract_no is not None
    assert quote.breakdown.historical_contract_total == Decimal("36500.00")
    assert quote.breakdown.historical_contract_days == 365
    assert quote.breakdown.fallback_used is False
    # license 透传
    assert quote.license_type == "formal"


@pytest.mark.asyncio
async def test_quote_no_history_fallback(service):
    """无历史合同时：fallback_used=True，估算金额=0。"""
    from plugins.ddw_renewal.services import RenewalService

    db = service.db
    today = _today()
    # 没插 contract，只插 license
    lic = await _seed_license(
        db, company_id=None, license_no="LIC-NO-HIST",
        valid_to=today + timedelta(days=200),
    )
    await db.commit()

    svc = RenewalService(db)
    quote = await svc.quote(tenant_id=1, license_id=lic.id, renewal_unit_days=180)
    assert quote.license_id == lic.id
    assert quote.breakdown.fallback_used is True
    assert quote.breakdown.historical_unit_price == Decimal("0.0000")
    assert quote.breakdown.historical_contract_id is None
    assert quote.estimated_amount == Decimal("0.00")
    assert quote.breakdown.renewal_unit_days == 180


@pytest.mark.asyncio
async def test_quote_revoked_blocked(service):
    """已吊销（revoked）的 license 不允许续费。"""
    from plugins.ddw_renewal.services import RenewalService

    db = service.db
    today = _today()
    lic = await _seed_license(
        db, license_no="LIC-REV",
        valid_to=today + timedelta(days=100),
        status="revoked",
    )
    await db.commit()

    svc = RenewalService(db)
    with pytest.raises(ValueError, match="已吊销"):
        await svc.quote(tenant_id=1, license_id=lic.id, renewal_unit_days=365)


@pytest.mark.asyncio
async def test_quote_not_found(service):
    """license 不存在：ValueError。"""
    from plugins.ddw_renewal.services import RenewalService

    svc = RenewalService(service.db)
    with pytest.raises(ValueError, match="不存在"):
        await svc.quote(tenant_id=1, license_id=99999)


# ===========================================================================
# 6. stats（续费统计概览）
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(seeded_db):
    """续费统计：active / overdue / renewed_total / 续费率 + 30/60/90 窗口。

    构造场景：
    - 3 active 30 天内到期（容量 10+20+30=60 users, 1+2+3=6 nodes）
    - 2 active 60 天内到期（不含 30 天内）
    - 1 active 90 天内到期（不含 60 天内）
    - 1 active 200 天后到期（不在 30/60/90 窗口）
    - 1 expired（已过期）
    - 1 renewed（已续费）
    - 续费率 = 1 / (1 + 1) = 0.5
    """
    db = seeded_db
    c1 = await _seed_company(db, name="E 公司")
    today = _today()

    # 30 天内到期：3 条
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-30-1",
        valid_to=today + timedelta(days=10), max_users=10, max_nodes=1,
    )
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-30-2",
        valid_to=today + timedelta(days=20), max_users=20, max_nodes=2,
    )
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-30-3",
        valid_to=today + timedelta(days=30), max_users=30, max_nodes=3,
    )
    # 60 天内（不含 30 天内）：2 条
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-60-1",
        valid_to=today + timedelta(days=45), max_users=5, max_nodes=1,
    )
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-60-2",
        valid_to=today + timedelta(days=60), max_users=5, max_nodes=1,
    )
    # 90 天内（不含 60 天内）：1 条
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-90-1",
        valid_to=today + timedelta(days=90), max_users=7, max_nodes=2,
    )
    # 200 天后到期：不在窗口
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-FAR",
        valid_to=today + timedelta(days=200), max_users=99, max_nodes=9,
    )
    # 1 expired
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-EXP",
        valid_to=today - timedelta(days=5), status="expired",
    )
    # 1 renewed
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-REN",
        valid_to=today + timedelta(days=180), status="renewed",
        max_users=1, max_nodes=1,
    )
    # 1 已逾期但还是 active 状态（业务上「该过期没自动标记」）
    await _seed_license(
        db, company_id=c1.id, license_no="LIC-OVD-ACT",
        valid_to=today - timedelta(days=15), status="active",
    )
    await db.commit()

    from plugins.ddw_renewal.services import RenewalService

    svc = RenewalService(db)
    s = await svc.stats(tenant_id=1)
    assert s.tenant_id == 1
    assert s.today == today
    # active 总数 = 3 + 2 + 1 + 1(OVD) = 7（renewed 不算 active，200 天后那条算 active）
    # 等等：200 天后到期的是 active → 7 active
    # 重新算：active 状态 = 3(30天) + 2(60天) + 1(90天) + 1(200天) + 1(15天前OVD) = 8
    assert s.active == 8
    # overdue = active 且 valid_to<today + expired 且 valid_to<today = 1 + 1 = 2
    assert s.overdue == 2
    # renewed = 1
    assert s.renewed_total == 1
    # 续费率 = 1 / (1 + 1) = 0.5
    assert s.renewal_rate == 0.5
    # 30 天窗口：3 条
    assert s.expiring_30 == 3
    # 60 天窗口：3 + 2 = 5
    assert s.expiring_60 == 5
    # 90 天窗口：3 + 2 + 1 = 6
    assert s.expiring_90 == 6
    # 90 天内许可证容量合计：10+20+30 (30天) + 5+5 (60天) + 7 (90天) = 77 users
    assert s.total_users_at_risk == 77
    # 1+2+3 + 1+1 + 2 = 10 nodes
    assert s.total_nodes_at_risk == 10
    # windows 列表
    assert len(s.windows) == 3
    by_w = {w.window_days: w for w in s.windows}
    assert by_w[30].expiring == 3
    assert by_w[30].total_users == 60
    assert by_w[30].total_nodes == 6
    assert by_w[60].expiring == 5
    assert by_w[60].total_users == 70
    assert by_w[60].total_nodes == 8  # 30天内 6 + 60天内新增 1+1 = 8
    assert by_w[90].expiring == 6
    assert by_w[90].total_users == 77
    assert by_w[90].total_nodes == 10  # 60天 8 + 90天内新增 2 = 10


@pytest.mark.asyncio
async def test_stats_empty(service):
    """空库下 stats：全 0，续费率 = 0.0。"""
    from plugins.ddw_renewal.services import RenewalService

    svc = RenewalService(service.db)
    s = await svc.stats(tenant_id=1)
    assert s.active == 0
    assert s.overdue == 0
    assert s.renewed_total == 0
    assert s.renewal_rate == 0.0
    assert s.expiring_30 == 0
    assert s.expiring_60 == 0
    assert s.expiring_90 == 0
    assert s.total_users_at_risk == 0
    assert s.total_nodes_at_risk == 0
    assert len(s.windows) == 3
    for w in s.windows:
        assert w.expiring == 0
        assert w.total_users == 0
        assert w.total_nodes == 0
