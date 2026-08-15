from __future__ import annotations

"""DDW 客户报备与归属插件测试用例（10 个，覆盖 CRUD + 过期自动标记 + 释放 + 冲突 + 统计）。"""

from datetime import datetime, timedelta, timezone

import pytest

from plugins.ddw_lead_claim.models import LeadClaim
from plugins.ddw_lead_claim.schemas import (
    LeadClaimCreateReq,
    LeadClaimUpdateReq,
    ReleaseClaimReq,
)

# ===========================================================================
# 1. 新建报备（验证 expire_at 自动计算）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_claim(service_with_company):
    """新建报备：protection_days=60 时，expire_at = claim_date + 60 天。

    关键校验：expire_at 必须由服务端计算，不能让调用方控制。
    """
    claim_date = datetime(2026, 1, 1, 10, 0, 0)
    req = LeadClaimCreateReq(
        tenant_id=1,
        company_id=100,
        claim_date=claim_date,
        protection_days=60,
        contact_person="张三",
        contact_phone="13800001111",
        opportunity_source="转介绍",
        expected_amount=120000.00,
        follow_up_notes="首次接触，客户对产品有兴趣",
        created_by=1,
    )
    result = await service_with_company.create(req)
    assert result["id"] is not None
    # expire_at = claim_date + 60 days（默认 60 天）
    expected_expire = datetime(2026, 1, 1, 10, 0, 0) + timedelta(days=60)
    assert result["expire_at"] == expected_expire
    assert result["status"] == "active"
    assert result["company_id"] == 100
    assert result["contact_person"] == "张三"
    assert result["opportunity_source"] == "转介绍"
    assert result["protection_days"] == 60


# ===========================================================================
# 2. 自定义保护期
# ===========================================================================


@pytest.mark.asyncio
async def test_create_claim_with_custom_protection_days(service_with_company):
    """自定义保护期（30 天）：expire_at = claim_date + 30 天。"""
    claim_date = datetime(2026, 6, 1, 9, 0, 0)
    req = LeadClaimCreateReq(
        tenant_id=1,
        company_id=100,
        claim_date=claim_date,
        protection_days=30,
        contact_person="李四",
    )
    result = await service_with_company.create(req)
    assert result["protection_days"] == 30
    assert result["expire_at"] == datetime(2026, 6, 1, 9, 0, 0) + timedelta(days=30)
    assert result["status"] == "active"


# ===========================================================================
# 3. 列表（分页）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_claims_paginated(service_with_company):
    """分页：插 12 条 → page=1 取 5 条，page=2 取 5 条，page=3 取 2 条。"""
    for i in range(12):
        await service_with_company.create(
            LeadClaimCreateReq(
                tenant_id=1,
                company_id=100,
                contact_person=f"客户{i}",
                protection_days=60,
            )
        )

    p1 = await service_with_company.list(page=1, page_size=5)
    p2 = await service_with_company.list(page=2, page_size=5)
    p3 = await service_with_company.list(page=3, page_size=5)

    assert p1.total == 12
    assert len(p1.items) == 5
    assert len(p2.items) == 5
    assert len(p3.items) == 2


# ===========================================================================
# 4. 按 partner 筛选
# ===========================================================================


@pytest.mark.asyncio
async def test_list_claims_filter_by_partner(service_full):
    """按 partner_id 筛选：只返回指定渠道的报备。"""
    # partner_id=200 的报备 3 条（不同 company，同一渠道对不同客户独立报备）
    for i in range(3):
        await service_full.create(
            LeadClaimCreateReq(
                tenant_id=1,
                partner_id=200,
                company_id=100 + i,
                contact_person=f"渠道A客户{i}",
            )
        )
    # partner_id=None（直销）的报备 2 条（不同 company）
    for i in range(2):
        await service_full.create(
            LeadClaimCreateReq(
                tenant_id=1,
                company_id=200 + i,
                contact_person=f"直销客户{i}",
            )
        )

    p = await service_full.list(page=1, page_size=20, partner_id=200)
    assert p.total == 3
    assert {x.contact_person for x in p.items} == {
        "渠道A客户0",
        "渠道A客户1",
        "渠道A客户2",
    }


# ===========================================================================
# 5. 报备详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_claim_detail(service_with_company):
    """获取详情（含 expire_at 字段）。"""
    created = await service_with_company.create(
        LeadClaimCreateReq(
            tenant_id=1,
            company_id=100,
            contact_person="王五",
            protection_days=90,
            follow_up_notes="详细沟通记录",
        )
    )
    cid = created["id"]

    detail = await service_with_company.get(cid)
    assert detail is not None
    assert detail["id"] == cid
    assert detail["contact_person"] == "王五"
    assert detail["protection_days"] == 90
    assert detail["status"] == "active"
    assert detail["follow_up_notes"] == "详细沟通记录"

    # 不存在
    assert await service_with_company.get(99999) is None


# ===========================================================================
# 6. 更新 active 状态的报备
# ===========================================================================


@pytest.mark.asyncio
async def test_update_claim_active(service_with_company):
    """active 状态允许更新：联系人/手机/备注/最后跟进时间。"""
    created = await service_with_company.create(
        LeadClaimCreateReq(
            tenant_id=1,
            company_id=100,
            contact_person="赵六",
            follow_up_notes="初次接触",
        )
    )
    cid = created["id"]

    last_follow_up = datetime(2026, 6, 15, 14, 0, 0)
    upd = LeadClaimUpdateReq(
        contact_person="赵六（更新）",
        contact_phone="13900002222",
        follow_up_notes="二次沟通，客户确认预算",
        last_follow_up_at=last_follow_up,
        updated_by=1,
    )
    result = await service_with_company.update(cid, upd)
    assert result is not None
    assert result["contact_person"] == "赵六（更新）"
    assert result["contact_phone"] == "13900002222"
    assert result["follow_up_notes"] == "二次沟通，客户确认预算"
    assert result["last_follow_up_at"] == last_follow_up


# ===========================================================================
# 7. 主动释放
# ===========================================================================


@pytest.mark.asyncio
async def test_release_claim(service_with_company):
    """主动释放：status -> released，记录 release_reason 和 released_at。"""
    created = await service_with_company.create(
        LeadClaimCreateReq(tenant_id=1, company_id=100, contact_person="孙七")
    )
    cid = created["id"]
    assert created["status"] == "active"

    result = await service_with_company.release(
        cid, ReleaseClaimReq(release_reason="客户主动放弃，改用其他方案", updated_by=1)
    )
    assert result is not None
    assert result["status"] == "released"
    assert result["release_reason"] == "客户主动放弃，改用其他方案"
    assert result["released_at"] is not None
    # release_at 应为当前时间附近
    released_at = result["released_at"]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((now - released_at).total_seconds()) < 10


# ===========================================================================
# 8. 保护期过期自动标记（核心业务规则）
# ===========================================================================


@pytest.mark.asyncio
async def test_expired_auto_mark(service_with_company):
    """expire_at < now() 的报备，list 调用时应自动被标记为 expired。"""
    # 造一个"已过期"的报备：claim_date 在 100 天前，protection_days=30 → 已过期
    old_claim_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=100)
    expired_claim = await service_with_company.create(
        LeadClaimCreateReq(
            tenant_id=1,
            company_id=100,
            contact_person="过期报备",
            claim_date=old_claim_date,
            protection_days=30,
        )
    )
    cid = expired_claim["id"]
    # 创建后 status 仍是 active（不在 create 时改）
    assert expired_claim["status"] == "active"

    # 触发 list 端点（内部会先 _auto_mark_expired）
    page = await service_with_company.list(page=1, page_size=20)
    refreshed = next(x for x in page.items if x.id == cid)
    assert refreshed.status == "expired"

    # 再次 get 也会拿到 expired（因为 _auto_mark_expired 是 write 操作，状态已持久化）
    detail = await service_with_company.get(cid)
    assert detail["status"] == "expired"


# ===========================================================================
# 9. 冲突查询
# ===========================================================================


@pytest.mark.asyncio
async def test_conflict_query(service_full):
    """冲突查询：返回 company_id=100 的所有报备 + active 计数。

    场景：
    - 2 个 active 报备（不同 partner）
    - 1 个已 released 报备
    - 1 个已 expired 报备（造一个 claim_date 在很久以前 + 短 protection）
    → total=4, active_count=2
    """
    # 2 个 active 报备
    await service_full.create(
        LeadClaimCreateReq(
            tenant_id=1, partner_id=200, company_id=100, contact_person="A"
        )
    )
    # 用不同的 partner 再建一个（避开 partner+company 唯一性）
    # 注：crm_partners stub 只有 id=200；这里用 partner_id=None 模拟直销伙伴
    await service_full.create(
        LeadClaimCreateReq(tenant_id=1, company_id=100, contact_person="B")
    )
    # 释放其中一个
    conflict = await service_full.conflict(company_id=100)
    assert conflict.total == 2
    assert conflict.active_count == 2
    released_id = conflict.items[0].id
    await service_full.release(released_id, ReleaseClaimReq(release_reason="测试"))

    # 新增 1 个已 expired 报备
    old_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=200)
    await service_full.create(
        LeadClaimCreateReq(
            tenant_id=1, company_id=100, contact_person="C",
            claim_date=old_date, protection_days=10,
        )
    )
    # 触发 list 自动标记 expired
    await service_full.list(page=1, page_size=50)

    # 再次查询冲突：4 条 total（2 active + 1 released + 1 expired），active_count=1
    conflict2 = await service_full.conflict(company_id=100)
    assert conflict2.total == 3
    assert conflict2.active_count == 1
    statuses = {x.status for x in conflict2.items}
    assert statuses == {"active", "released", "expired"}


# ===========================================================================
# 10. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service_full):
    """统计：total / active / expired / won / lost / released / by_partner。

    场景：
    - partner=200 active: 2 条
    - partner=None active: 1 条
    - 释放 1 条 → released=1
    - 1 条造过期 → expired=1
    - 1 条直接造 won → won=1（手动改 status）
    - 1 条直接造 lost → lost=1（手动改 status）
    → total=6, active=2, expired=1, won=1, lost=1, released=1
    → by_partner = {"200": 2, "unknown": 1}（仅 active 报备按 partner 分组）
    """
    # partner=200 active: 2 条（不同 company）
    await service_full.create(
        LeadClaimCreateReq(tenant_id=1, partner_id=200, company_id=100, contact_person="P200-A")
    )
    await service_full.create(
        LeadClaimCreateReq(tenant_id=1, partner_id=200, company_id=101, contact_person="P200-B")
    )
    # partner=None active: 1 条
    await service_full.create(
        LeadClaimCreateReq(tenant_id=1, company_id=200, contact_person="直销-1")
    )
    # 释放 1 条（用 P200-A）
    p200_a = (await service_full.list(partner_id=200, page=1, page_size=20)).items[0]
    await service_full.release(p200_a.id, ReleaseClaimReq(release_reason="测试"))

    # 1 条造过期（不同 company）
    old_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=200)
    await service_full.create(
        LeadClaimCreateReq(
            tenant_id=1, company_id=102, contact_person="过期-1",
            claim_date=old_date, protection_days=10,
        )
    )
    # 1 条造 won（不同 company）
    won_claim = await service_full.create(
        LeadClaimCreateReq(tenant_id=1, company_id=103, contact_person="赢单-1")
    )
    # 直接改 status 为 won
    won_obj = await service_full.db.get(LeadClaim, won_claim["id"])
    won_obj.status = "won"
    await service_full.db.commit()
    # 1 条造 lost（不同 company）
    lost_claim = await service_full.create(
        LeadClaimCreateReq(tenant_id=1, company_id=104, contact_person="丢单-1")
    )
    lost_obj = await service_full.db.get(LeadClaim, lost_claim["id"])
    lost_obj.status = "lost"
    await service_full.db.commit()

    # 触发 list 自动标记过期
    await service_full.list(page=1, page_size=50)

    stats = await service_full.stats()
    assert stats.total == 6
    assert stats.active == 2
    assert stats.expired == 1
    assert stats.won == 1
    assert stats.lost == 1
    assert stats.released == 1
    # by_partner: 仅 active 报备按 partner 分组（partner=200 active=1, partner=None active=1）
    assert stats.by_partner == {"200": 1, "unknown": 1}
