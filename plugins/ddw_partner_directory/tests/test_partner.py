from __future__ import annotations

"""DDW 经销商开户插件测试用例（9 个：覆盖开户、列表、筛选、详情、更新、暂停、统计）。"""

import pytest

from plugins.ddw_partner_directory.schemas import (
    PartnerCreateReq,
    PartnerUpdateReq,
)

# ===========================================================================
# 1. 开户（正常，含全部字段）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_partner(service):
    """新建经销商：含全部可选字段。"""
    req = PartnerCreateReq(
        partner_type="reseller",
        level="gold",
        region="华东",
        industry="软件和信息技术服务业",
        allowed_products=["ddw-llm-gateway", "ddw-token-manager"],
        product_discount=75,
        plugin_discount=80,
        service_discount=85,
        agreement_start="2026-01-01",  # type: ignore[arg-type]
        agreement_end="2026-12-31",  # type: ignore[arg-type]
        contact_person="张三",
        contact_phone="13800138000",
        notes="战略合作经销商",
        created_by=1,
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["tenant_id"] == 1
    assert result["partner_type"] == "reseller"
    assert result["level"] == "gold"
    assert result["region"] == "华东"
    assert result["industry"] == "软件和信息技术服务业"
    assert result["allowed_products"] == ["ddw-llm-gateway", "ddw-token-manager"]
    # 百分数 75 / 80 / 85
    assert float(result["product_discount"]) == 75.0
    assert float(result["plugin_discount"]) == 80.0
    assert float(result["service_discount"]) == 85.0
    assert str(result["agreement_start"]) == "2026-01-01"
    assert str(result["agreement_end"]) == "2026-12-31"
    assert result["contact_person"] == "张三"
    assert result["contact_phone"] == "13800138000"
    assert result["notes"] == "战略合作经销商"
    assert result["status"] == "active"
    assert result["company_id"] is None
    assert result["created_by"] == 1


# ===========================================================================
# 2. 开户（关联企业）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_partner_with_company(seeded_company, service):
    """新建经销商并挂靠已有企业。"""
    req = PartnerCreateReq(
        company_id=seeded_company,
        partner_type="distributor",
        level="strategic",
        contact_person="李四",
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["company_id"] == seeded_company
    assert result["partner_type"] == "distributor"
    assert result["level"] == "strategic"
    assert result["contact_person"] == "李四"


# ===========================================================================
# 3. 列表（分页）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_partners_paginated(service):
    """插入 25 条，按 page=1/2/3 + page_size=10 验证分页。"""
    for i in range(25):
        await service.create(PartnerCreateReq(contact_person=f"联系人 {i:02d}"))

    page1 = await service.list(page=1, page_size=10)
    page2 = await service.list(page=2, page_size=10)
    page3 = await service.list(page=3, page_size=10)

    assert page1.total == 25
    assert len(page1.items) == 10
    assert page1.page == 1
    assert len(page2.items) == 10
    assert page2.page == 2
    # 最后一页只剩 5 条
    assert len(page3.items) == 5
    assert page3.page == 3


# ===========================================================================
# 4. 列表（按 partner_type 筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_partners_filter_by_type(service):
    """按 partner_type 筛选：3 reseller + 2 agent + 1 distributor，筛 reseller 应得 3。"""
    for _ in range(3):
        await service.create(PartnerCreateReq(partner_type="reseller"))
    for _ in range(2):
        await service.create(PartnerCreateReq(partner_type="agent"))
    await service.create(PartnerCreateReq(partner_type="distributor"))

    only_reseller = await service.list(page=1, page_size=50, partner_type="reseller")
    assert only_reseller.total == 3
    assert all(p.partner_type == "reseller" for p in only_reseller.items)

    only_agent = await service.list(page=1, page_size=50, partner_type="agent")
    assert only_agent.total == 2
    assert all(p.partner_type == "agent" for p in only_agent.items)

    only_dist = await service.list(page=1, page_size=50, partner_type="distributor")
    assert only_dist.total == 1


# ===========================================================================
# 5. 列表（按 level 筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_partners_filter_by_level(service):
    """按 level 筛选：2 normal + 3 silver + 1 gold + 1 strategic，筛 gold 应得 1。"""
    for _ in range(2):
        await service.create(PartnerCreateReq(level="normal"))
    for _ in range(3):
        await service.create(PartnerCreateReq(level="silver"))
    await service.create(PartnerCreateReq(level="gold"))
    await service.create(PartnerCreateReq(level="strategic"))

    only_gold = await service.list(page=1, page_size=50, level="gold")
    assert only_gold.total == 1
    assert only_gold.items[0].level == "gold"

    only_silver = await service.list(page=1, page_size=50, level="silver")
    assert only_silver.total == 3
    assert all(p.level == "silver" for p in only_silver.items)


# ===========================================================================
# 6. 详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_partner_detail(service):
    """获取经销商详情：含关联企业。"""
    req = PartnerCreateReq(
        partner_type="agent",
        level="silver",
        region="华南",
        industry="金融",
        contact_person="王五",
        notes="核心代理",
    )
    created = await service.create(req)
    pid = created["id"]

    detail = await service.get(pid)
    assert detail is not None
    assert detail["id"] == pid
    assert detail["partner_type"] == "agent"
    assert detail["level"] == "silver"
    assert detail["region"] == "华南"
    assert detail["industry"] == "金融"
    assert detail["contact_person"] == "王五"
    assert detail["notes"] == "核心代理"
    assert detail["status"] == "active"

    # 不存在
    missing = await service.get(99999)
    assert missing is None


# ===========================================================================
# 7. 更新
# ===========================================================================


@pytest.mark.asyncio
async def test_update_partner(service):
    """更新经销商：等级/折扣/联系人/区域/状态。"""
    created = await service.create(
        PartnerCreateReq(
            partner_type="reseller",
            level="normal",
            contact_person="旧联系人",
        )
    )
    pid = created["id"]

    update = PartnerUpdateReq(
        level="gold",
        product_discount=70,
        contact_person="新联系人",
        region="华中",
        notes="升级为金牌",
    )
    result = await service.update(pid, update)
    assert result is not None
    assert result["level"] == "gold"
    assert float(result["product_discount"]) == 70.0
    assert result["contact_person"] == "新联系人"
    assert result["region"] == "华中"
    assert result["notes"] == "升级为金牌"
    # 未改字段保持原值
    assert result["partner_type"] == "reseller"


# ===========================================================================
# 8. 软删除（暂停）
# ===========================================================================


@pytest.mark.asyncio
async def test_suspend_partner(service):
    """暂停经销商（软删除：status=suspended）。"""
    created = await service.create(PartnerCreateReq(contact_person="待暂停"))
    pid = created["id"]
    assert created["status"] == "active"

    result = await service.suspend(pid)
    assert result is not None
    assert result["status"] == "suspended"

    # 默认列表（不带 status）应仍能查到（按 id.desc 排序，含所有状态）
    all_list = await service.list(page=1, page_size=50)
    assert any(p.id == pid for p in all_list.items)
    assert next(p for p in all_list.items if p.id == pid).status == "suspended"

    # 按 status=active 筛选应过滤掉
    active_only = await service.list(page=1, page_size=50, status="active")
    assert all(p.id != pid for p in active_only.items)

    # 不存在
    miss = await service.suspend(99999)
    assert miss is None


# ===========================================================================
# 9. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：total/active/inactive/suspended + by_type/level/region。

    数据：2 reseller / 1 agent / 1 distributor
         1 gold / 2 silver / 1 normal
         2 华东 / 1 华南 / 1 华中
    1 个 suspended。
    """
    # 2 reseller: 1 gold(华东) + 1 silver(华南)
    await service.create(
        PartnerCreateReq(partner_type="reseller", level="gold", region="华东")
    )
    await service.create(
        PartnerCreateReq(partner_type="reseller", level="silver", region="华南")
    )
    # 1 agent: silver(华东)
    await service.create(
        PartnerCreateReq(partner_type="agent", level="silver", region="华东")
    )
    # 1 distributor: normal(华中)
    await service.create(
        PartnerCreateReq(partner_type="distributor", level="normal", region="华中")
    )

    # 暂停其中一个
    to_suspend = await service.create(
        PartnerCreateReq(partner_type="reseller", level="normal", region="华中")
    )
    await service.suspend(to_suspend["id"])

    stats = await service.stats()
    assert stats.total == 5
    assert stats.active == 4
    assert stats.suspended == 1
    assert stats.inactive == 0

    # by_partner_type: reseller=3（含 suspended）/ agent=1 / distributor=1
    assert stats.by_partner_type.get("reseller") == 3
    assert stats.by_partner_type.get("agent") == 1
    assert stats.by_partner_type.get("distributor") == 1

    # by_level: normal=2 / silver=2 / gold=1
    assert stats.by_level.get("normal") == 2
    assert stats.by_level.get("silver") == 2
    assert stats.by_level.get("gold") == 1

    # by_region: 华东=2 / 华南=1 / 华中=2
    assert stats.by_region.get("华东") == 2
    assert stats.by_region.get("华南") == 1
    assert stats.by_region.get("华中") == 2
