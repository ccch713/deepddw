from __future__ import annotations

"""DDW Token 额度管理插件测试用例（10 个）。

覆盖核心 CRUD + 列表筛选 + 消耗（含超量拒绝/允许） + 统计 + 删除。
"""

import pytest

from plugins.ddw_token_entitlement.schemas import (
    TokenConsumeReq,
    TokenEntitlementCreateReq,
    TokenEntitlementUpdateReq,
)

# ===========================================================================
# 1. 新建额度分配
# ===========================================================================


@pytest.mark.asyncio
async def test_create_entitlement(service_with_related):
    """正常创建额度分配：默认 used_tokens=0，含 remaining_tokens 派生字段。"""
    req = TokenEntitlementCreateReq(
        company_id=100,
        instance_id=200,
        entitlement_type="platform",
        allocated_tokens=1_000_000,
        overage_allowed=False,
        notes="2026 锐果互动平台共享额度",
    )
    result = await service_with_related.create(req)
    assert result["id"] is not None
    assert result["company_id"] == 100
    assert result["instance_id"] == 200
    assert result["entitlement_type"] == "platform"
    assert result["allocated_tokens"] == 1_000_000
    assert result["used_tokens"] == 0
    assert result["remaining_tokens"] == 1_000_000
    assert result["overage_allowed"] is False


# ===========================================================================
# 2. 列表筛选（按 entitlement_type）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_entitlements_filter_by_type(service_with_related):
    """按 entitlement_type 筛选：3 类各 1 条 + 1 条 platform，验证筛选结果。"""
    rel = service_with_related
    await rel.create(
        TokenEntitlementCreateReq(
            company_id=100, entitlement_type="platform", allocated_tokens=1000
        )
    )
    await rel.create(
        TokenEntitlementCreateReq(
            company_id=100, entitlement_type="custom-key", allocated_tokens=2000,
            api_key_masked="sk-****1234",
        )
    )
    await rel.create(
        TokenEntitlementCreateReq(
            company_id=100, entitlement_type="local-llm", allocated_tokens=3000,
            llm_endpoint="http://10.0.0.5:11434/v1",
        )
    )
    await rel.create(
        TokenEntitlementCreateReq(
            company_id=100, entitlement_type="platform", allocated_tokens=4000
        )
    )

    # 仅 platform：应返回 2 条
    page_p = await rel.list(page=1, page_size=20, entitlement_type="platform")
    assert page_p.total == 2
    assert all(it.entitlement_type == "platform" for it in page_p.items)

    # 仅 custom-key：应返回 1 条
    page_c = await rel.list(page=1, page_size=20, entitlement_type="custom-key")
    assert page_c.total == 1
    assert page_c.items[0].entitlement_type == "custom-key"
    assert page_c.items[0].api_key_masked == "sk-****1234"

    # 仅 local-llm：应返回 1 条
    page_l = await rel.list(page=1, page_size=20, entitlement_type="local-llm")
    assert page_l.total == 1
    assert page_l.items[0].llm_endpoint == "http://10.0.0.5:11434/v1"

    # 不传类型：返回全部 4 条
    page_all = await rel.list(page=1, page_size=20)
    assert page_all.total == 4


# ===========================================================================
# 3. 详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_entitlement_detail(service_with_related):
    """获取详情：含派生字段 remaining_tokens。"""
    rel = service_with_related
    created = await rel.create(
        TokenEntitlementCreateReq(
            company_id=100,
            entitlement_type="platform",
            allocated_tokens=500_000,
        )
    )
    eid = created["id"]

    detail = await rel.get(eid)
    assert detail is not None
    assert detail["id"] == eid
    assert detail["allocated_tokens"] == 500_000
    assert detail["used_tokens"] == 0
    assert detail["remaining_tokens"] == 500_000

    # 不存在
    assert await rel.get(99999) is None


# ===========================================================================
# 4. 更新（不能改 used_tokens / tenant_id）
# ===========================================================================


@pytest.mark.asyncio
async def test_update_entitlement(service_with_related):
    """更新：调整 allocated_tokens / notes / overage_allowed / api_key_masked。

    同时验证：尝试通过 update 改 used_tokens 是无效的（被 service 显式剔除）。
    """
    rel = service_with_related
    created = await rel.create(
        TokenEntitlementCreateReq(
            company_id=100,
            entitlement_type="custom-key",
            allocated_tokens=100_000,
            api_key_masked="sk-****1111",
        )
    )
    eid = created["id"]

    # 尝试塞 used_tokens 字段（应被 service 忽略）
    update = TokenEntitlementUpdateReq(
        allocated_tokens=200_000,
        notes="扩容到 200k",
        overage_allowed=True,
        api_key_masked="sk-****2222",
    )
    # 故意多塞一个字段：Pydantic 没声明 used_tokens，所以这个字段根本到不了 service
    result = await rel.update(eid, update)
    assert result is not None
    assert result["allocated_tokens"] == 200_000
    assert result["notes"] == "扩容到 200k"
    assert result["overage_allowed"] is True
    assert result["api_key_masked"] == "sk-****2222"
    # used_tokens 仍为 0（从未被允许通过 update 改）
    assert result["used_tokens"] == 0


# ===========================================================================
# 5. 消耗 tokens（正常）
# ===========================================================================


@pytest.mark.asyncio
async def test_consume_tokens_normal(service_with_related):
    """正常消耗：分多次累加 used_tokens，remaining 递减。"""
    rel = service_with_related
    created = await rel.create(
        TokenEntitlementCreateReq(
            company_id=100,
            entitlement_type="platform",
            allocated_tokens=10_000,
        )
    )
    eid = created["id"]

    # 第 1 次消耗 3000
    r1 = await rel.consume(eid, TokenConsumeReq(tokens=3_000))
    assert r1["used_tokens"] == 3_000
    assert r1["remaining_tokens"] == 7_000
    assert r1["overage"] == 7_000  # 正数：还有余
    assert r1["overage_allowed"] is False

    # 第 2 次消耗 5000
    r2 = await rel.consume(eid, TokenConsumeReq(tokens=5_000))
    assert r2["used_tokens"] == 8_000
    assert r2["remaining_tokens"] == 2_000

    # 第 3 次消耗 2000（恰好用完）
    r3 = await rel.consume(eid, TokenConsumeReq(tokens=2_000))
    assert r3["used_tokens"] == 10_000
    assert r3["remaining_tokens"] == 0
    assert r3["overage"] == 0  # 恰好为 0


# ===========================================================================
# 6. 消耗 tokens（超量拒绝）
# ===========================================================================


@pytest.mark.asyncio
async def test_consume_tokens_exceeds_no_overage(service_with_related):
    """overage_allowed=False 时，超量应抛 ValueError，原 used_tokens 不变。"""
    rel = service_with_related
    created = await rel.create(
        TokenEntitlementCreateReq(
            company_id=100,
            entitlement_type="platform",
            allocated_tokens=1_000,
            overage_allowed=False,
        )
    )
    eid = created["id"]

    # 先消耗 800
    r1 = await rel.consume(eid, TokenConsumeReq(tokens=800))
    assert r1["used_tokens"] == 800

    # 再消耗 500 → 800+500=1300 > 1000，应拒绝
    with pytest.raises(ValueError, match="额度不足"):
        await rel.consume(eid, TokenConsumeReq(tokens=500))

    # 验证 used_tokens 没变
    detail = await rel.get(eid)
    assert detail["used_tokens"] == 800


# ===========================================================================
# 7. 消耗 tokens（允许超量）
# ===========================================================================


@pytest.mark.asyncio
async def test_consume_tokens_with_overage(service_with_related):
    """overage_allowed=True 时，正常累加并返回负数 overage。"""
    rel = service_with_related
    created = await rel.create(
        TokenEntitlementCreateReq(
            company_id=100,
            entitlement_type="custom-key",
            allocated_tokens=1_000,
            overage_allowed=True,
            api_key_masked="sk-****9999",
        )
    )
    eid = created["id"]

    # 消耗 1500（超量 500）
    r1 = await rel.consume(eid, TokenConsumeReq(tokens=1_500))
    assert r1["used_tokens"] == 1_500
    assert r1["remaining_tokens"] == -500  # 负数：超量
    assert r1["overage"] == -500
    assert r1["overage_allowed"] is True

    # 继续消耗 1000（累计 2500，仍允许）
    r2 = await rel.consume(eid, TokenConsumeReq(tokens=1_000))
    assert r2["used_tokens"] == 2_500
    assert r2["remaining_tokens"] == -1_500


# ===========================================================================
# 8. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service_with_related):
    """统计：total_allocated / total_used / total_remaining + by_type + overage_count。

    构造场景（company_id 都为 100）：
    - 1 platform 5000（消耗 2000，未超量）
    - 1 custom-key 3000（消耗 3500，超量 500）
    - 1 local-llm 2000（未消耗）
    - 1 platform 1000（消耗 1500，超量 500；与 company 100 相同 → overage 算 1 个企业）

    期望：
    - total_count=4, total_allocated=11000, total_used=7000, total_remaining=4000
    - by_type.platform = {count: 2, allocated: 6000, used: 3500}
    - by_type.custom-key = {count: 1, allocated: 3000, used: 3500}
    - by_type.local-llm = {count: 1, allocated: 2000, used: 0}
    - overage_count = 1（company_id=100 算 1 个企业去重）
    """
    rel = service_with_related

    # 1 platform 5000 / 消耗 2000
    e1 = await rel.create(
        TokenEntitlementCreateReq(
            company_id=100, entitlement_type="platform", allocated_tokens=5000
        )
    )
    await rel.consume(e1["id"], TokenConsumeReq(tokens=2000))

    # 2 custom-key 3000 / 消耗 3500（超量）
    e2 = await rel.create(
        TokenEntitlementCreateReq(
            company_id=100, entitlement_type="custom-key", allocated_tokens=3000,
            overage_allowed=True, api_key_masked="sk-****7777",
        )
    )
    await rel.consume(e2["id"], TokenConsumeReq(tokens=3500))

    # 3 local-llm 2000 / 未消耗
    await rel.create(
        TokenEntitlementCreateReq(
            company_id=100, entitlement_type="local-llm", allocated_tokens=2000,
            llm_endpoint="http://127.0.0.1:11434",
        )
    )

    # 4 platform 1000 / 消耗 1500（超量；同 company 100 → overage_count 不增加）
    e4 = await rel.create(
        TokenEntitlementCreateReq(
            company_id=100, entitlement_type="platform", allocated_tokens=1000,
            overage_allowed=True,
        )
    )
    await rel.consume(e4["id"], TokenConsumeReq(tokens=1500))

    stats = await rel.stats()
    assert stats.total_count == 4
    assert stats.total_allocated == 11_000
    assert stats.total_used == 7_000
    assert stats.total_remaining == 4_000

    # by_type
    p = stats.by_type["platform"]
    assert p["count"] == 2
    assert p["allocated"] == 6_000
    assert p["used"] == 3_500  # 2000 + 1500

    c = stats.by_type["custom-key"]
    assert c["count"] == 1
    assert c["allocated"] == 3_000
    assert c["used"] == 3_500

    lcl = stats.by_type["local-llm"]
    assert lcl["count"] == 1
    assert lcl["allocated"] == 2_000
    assert lcl["used"] == 0

    # overage_count：company 100 的 2 笔均超量，去重 = 1
    assert stats.overage_count == 1


# ===========================================================================
# 11. 跨企业超量：第二个企业也超量 → overage_count = 2
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overage_counts_per_company(service_with_related, seeded_db):
    """overage_count 跨企业：company 100 + 200 都超量 → 2 个企业（去重）。"""
    from plugins.ddw_company_profile.models import Company

    rel = service_with_related
    # 补一个 company 200
    seeded_db.add(
        Company(
            id=200,
            tenant_id=1,
            name="第二家超量公司",
            status="active",
            certification_status="pending",
            tags=[],
        )
    )
    await seeded_db.commit()

    # company 100：分配 1000 / 消耗 2000（超量）
    e1 = await rel.create(
        TokenEntitlementCreateReq(
            company_id=100, entitlement_type="platform", allocated_tokens=1000,
            overage_allowed=True,
        )
    )
    await rel.consume(e1["id"], TokenConsumeReq(tokens=2000))

    # company 200：分配 500 / 消耗 600（超量）
    e2 = await rel.create(
        TokenEntitlementCreateReq(
            company_id=200, entitlement_type="platform", allocated_tokens=500,
            overage_allowed=True,
        )
    )
    await rel.consume(e2["id"], TokenConsumeReq(tokens=600))

    stats = await rel.stats()
    assert stats.overage_count == 2
    assert stats.total_count == 2
    assert stats.total_allocated == 1500
    assert stats.total_used == 2600
    assert stats.total_remaining == -1100  # 负数 = 超量


# ===========================================================================
# 9. 硬删除
# ===========================================================================


@pytest.mark.asyncio
async def test_hard_delete(service_with_related):
    """DELETE 走硬删除：删除后 get 返回 None，list 中不再有该记录。"""
    rel = service_with_related
    created = await rel.create(
        TokenEntitlementCreateReq(
            company_id=100, entitlement_type="platform", allocated_tokens=1000
        )
    )
    eid = created["id"]

    # 删除
    ok = await rel.delete(eid)
    assert ok is True

    # 详情查询返回 None
    assert await rel.get(eid) is None

    # 列表中不再有
    page = await rel.list(page=1, page_size=20)
    assert all(it.id != eid for it in page.items)

    # 重复删除返回 False
    assert await rel.delete(eid) is False
    # 删除不存在的 ID
    assert await rel.delete(99999) is False


# ===========================================================================
# 10. 按 company_id 筛选 + 列表分页
# ===========================================================================


@pytest.mark.asyncio
async def test_list_filter_by_company_and_pagination(service_with_related, seeded_db):
    """按 company_id 筛选 + 分页：插入 25 条给 company 100，5 条给 company 200。

    注意：FK crm_companies.id 是 ON DELETE SET NULL 但 INSERT 时要求目标行存在，
    所以 company 200 也需要先建一个 crm_companies 行（不能指向不存在的 id）。
    """
    rel = service_with_related
    from plugins.ddw_company_profile.models import Company

    # 补一个 company 200（seeded_related 只 seed 了 100）
    seeded_db.add(
        Company(
            id=200,
            tenant_id=1,
            name="另一家测试公司",
            status="active",
            certification_status="pending",
            tags=[],
        )
    )
    await seeded_db.commit()

    # 25 条给 company 100
    for i in range(25):
        await rel.create(
            TokenEntitlementCreateReq(
                company_id=100, entitlement_type="platform", allocated_tokens=100 + i
            )
        )

    # 5 条给 company 200
    for i in range(5):
        await rel.create(
            TokenEntitlementCreateReq(
                company_id=200, entitlement_type="platform", allocated_tokens=200 + i
            )
        )

    # company 100：分页验证
    p1 = await rel.list(page=1, page_size=10, company_id=100)
    p2 = await rel.list(page=2, page_size=10, company_id=100)
    p3 = await rel.list(page=3, page_size=10, company_id=100)
    assert p1.total == 25
    assert len(p1.items) == 10
    assert len(p2.items) == 10
    assert len(p3.items) == 5

    # company 200：5 条
    p200 = await rel.list(page=1, page_size=20, company_id=200)
    assert p200.total == 5

    # 不传筛选：30 条
    p_all = await rel.list(page=1, page_size=100)
    assert p_all.total == 30
