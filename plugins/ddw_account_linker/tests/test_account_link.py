from __future__ import annotations

"""DDW 账号/租户/实例映射插件测试用例（8 个：覆盖创建、唯一性、列表、筛选、按企、详情、软删、统计）。"""

import pytest

from plugins.ddw_account_linker.schemas import (
    AccountLinkCreateReq,
)

# ===========================================================================
# 1. 创建账号链接（正常）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_account_link(seeded_company, service):
    """新建账号链接：含全部字段，关联企业。"""
    req = AccountLinkCreateReq(
        company_id=seeded_company,
        link_type="saas_tenant",
        external_id="tenant-abc-001",
        external_name="锐果云租户",
        metadata_json={"region": "cn-hangzhou", "plan": "pro"},
        created_by=1,
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["tenant_id"] == 1
    assert result["company_id"] == seeded_company
    assert result["link_type"] == "saas_tenant"
    assert result["external_id"] == "tenant-abc-001"
    assert result["external_name"] == "锐果云租户"
    assert result["metadata_json"] == {"region": "cn-hangzhou", "plan": "pro"}
    assert result["status"] == "active"
    assert result["created_by"] == 1


# ===========================================================================
# 2. 唯一性：同 link_type 内 external_id 重复 → ValueError
# ===========================================================================


@pytest.mark.asyncio
async def test_create_account_link_duplicate_external_id(service):
    """同 (link_type, external_id) 重复应抛 ValueError。"""
    req1 = AccountLinkCreateReq(link_type="user", external_id="user-001")
    await service.create(req1)

    # 同 link_type + 同 external_id → 必重复
    req2 = AccountLinkCreateReq(link_type="user", external_id="user-001", external_name="另一个")
    with pytest.raises(ValueError, match="已存在"):
        await service.create(req2)

    # 不同 link_type + 相同 external_id → 不冲突
    req3 = AccountLinkCreateReq(link_type="saas_tenant", external_id="user-001")
    result3 = await service.create(req3)
    assert result3["id"] is not None
    assert result3["link_type"] == "saas_tenant"
    assert result3["external_id"] == "user-001"


# ===========================================================================
# 3. 列表（分页）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_account_links_paginated(service):
    """插入 25 条，page=2&page_size=10 应返回 10 条。"""
    for i in range(25):
        await service.create(
            AccountLinkCreateReq(link_type="user", external_id=f"u-{i:03d}")
        )

    page1 = await service.list(page=1, page_size=10)
    page2 = await service.list(page=2, page_size=10)
    page3 = await service.list(page=3, page_size=10)

    assert page1.total == 25
    assert len(page1.items) == 10
    assert page1.page == 1
    assert len(page2.items) == 10
    # 最后一页只剩 5 条
    assert len(page3.items) == 5
    assert page3.page == 3


# ===========================================================================
# 4. 列表（按 link_type 筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_account_links_filter_by_type(service):
    """按 link_type 筛选：3 user + 2 saas_tenant + 1 on_premise_instance，筛 saas_tenant 应得 2。"""
    for i in range(3):
        await service.create(AccountLinkCreateReq(link_type="user", external_id=f"u-{i:03d}"))
    for i in range(2):
        await service.create(
            AccountLinkCreateReq(link_type="saas_tenant", external_id=f"st-{i:03d}")
        )
    await service.create(
        AccountLinkCreateReq(link_type="on_premise_instance", external_id="op-001")
    )

    only_user = await service.list(page=1, page_size=50, link_type="user")
    assert only_user.total == 3
    assert all(a.link_type == "user" for a in only_user.items)

    only_saas = await service.list(page=1, page_size=50, link_type="saas_tenant")
    assert only_saas.total == 2
    assert all(a.link_type == "saas_tenant" for a in only_saas.items)

    only_op = await service.list(page=1, page_size=50, link_type="on_premise_instance")
    assert only_op.total == 1
    assert only_op.items[0].external_id == "op-001"


# ===========================================================================
# 5. 按企业获取所有链接
# ===========================================================================


@pytest.mark.asyncio
async def test_get_by_company(seeded_company, seeded_company2, service):
    """by-company：返回某企业的所有链接（含各种 link_type），验证多企业隔离。"""
    # company_id=100: 2 user + 1 saas_tenant
    await service.create(
        AccountLinkCreateReq(company_id=seeded_company, link_type="user", external_id="u-100-1")
    )
    await service.create(
        AccountLinkCreateReq(company_id=seeded_company, link_type="user", external_id="u-100-2")
    )
    await service.create(
        AccountLinkCreateReq(company_id=seeded_company, link_type="saas_tenant", external_id="st-100-1")
    )
    # 另一家企业
    await service.create(
        AccountLinkCreateReq(
            company_id=seeded_company2, link_type="user", external_id="u-999-1"
        )
    )

    links_100 = await service.get_by_company(seeded_company)
    assert len(links_100) == 3
    assert all(a["company_id"] == seeded_company for a in links_100)
    # 验证两种 link_type 都在
    types = {a["link_type"] for a in links_100}
    assert types == {"user", "saas_tenant"}

    # 另一家企业也能查（隔离）
    links_999 = await service.get_by_company(seeded_company2)
    assert len(links_999) == 1
    assert links_999[0]["company_id"] == seeded_company2


# ===========================================================================
# 6. 详情（正常 + 不存在）
# ===========================================================================


@pytest.mark.asyncio
async def test_get_account_link_detail(seeded_company, service):
    """获取详情：含 metadata_json。"""
    req = AccountLinkCreateReq(
        company_id=seeded_company,
        link_type="on_premise_instance",
        external_id="op-instance-007",
        external_name="客户机房实例",
        metadata_json={"host": "10.0.0.7", "version": "v2.3.1"},
    )
    created = await service.create(req)
    lid = created["id"]

    detail = await service.get(lid)
    assert detail is not None
    assert detail["id"] == lid
    assert detail["link_type"] == "on_premise_instance"
    assert detail["external_id"] == "op-instance-007"
    assert detail["external_name"] == "客户机房实例"
    assert detail["metadata_json"] == {"host": "10.0.0.7", "version": "v2.3.1"}
    assert detail["status"] == "active"

    # 不存在
    miss = await service.get(99999)
    assert miss is None


# ===========================================================================
# 7. 软删除（停用：status=inactive）
# ===========================================================================


@pytest.mark.asyncio
async def test_deactivate_account_link(service):
    """停用账号链接（软删除：status=inactive）。"""
    created = await service.create(
        AccountLinkCreateReq(link_type="user", external_id="u-deact-001")
    )
    lid = created["id"]
    assert created["status"] == "active"

    result = await service.deactivate(lid)
    assert result is not None
    assert result["status"] == "inactive"

    # 默认列表（不带 status）应仍能查到（含 inactive）
    all_list = await service.list(page=1, page_size=50)
    assert any(a.id == lid for a in all_list.items)
    assert next(a for a in all_list.items if a.id == lid).status == "inactive"

    # 按 status=active 筛选应过滤掉
    active_only = await service.list(page=1, page_size=50, status="active")
    assert all(a.id != lid for a in active_only.items)

    # 不存在
    miss = await service.deactivate(99999)
    assert miss is None


# ===========================================================================
# 8. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：total/active/inactive + by_link_type。

    数据：
    - 3 user (2 active + 1 inactive)
    - 2 saas_tenant (全 active)
    - 1 on_premise_instance (active)
    - 共 6 条；active=5, inactive=1
    """
    # 3 user
    await service.create(AccountLinkCreateReq(link_type="user", external_id="u-001"))
    await service.create(AccountLinkCreateReq(link_type="user", external_id="u-002"))
    u3 = await service.create(AccountLinkCreateReq(link_type="user", external_id="u-003"))
    # 2 saas_tenant
    await service.create(AccountLinkCreateReq(link_type="saas_tenant", external_id="st-001"))
    await service.create(AccountLinkCreateReq(link_type="saas_tenant", external_id="st-002"))
    # 1 on_premise_instance
    await service.create(
        AccountLinkCreateReq(link_type="on_premise_instance", external_id="op-001")
    )
    # 停用 u-003
    await service.deactivate(u3["id"])

    stats = await service.stats()
    assert stats.total == 6
    assert stats.active == 5
    assert stats.inactive == 1
    # by_link_type: user=3 / saas_tenant=2 / on_premise_instance=1
    assert stats.by_link_type.get("user") == 3
    assert stats.by_link_type.get("saas_tenant") == 2
    assert stats.by_link_type.get("on_premise_instance") == 1
