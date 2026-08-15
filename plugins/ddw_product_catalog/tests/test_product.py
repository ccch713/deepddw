from __future__ import annotations

"""DDW 产品与插件目录插件测试用例（10 个，覆盖核心 CRUD + 筛选 + 搜索 + 统计）。"""

from decimal import Decimal

import pytest

from plugins.ddw_product_catalog.schemas import ProductCreateReq, ProductUpdateReq

# ===========================================================================
# 1. 创建产品（正常）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_product(service):
    """正常创建产品。"""
    req = ProductCreateReq(
        code="DDW-HUB-PRO",
        name="DDW 智能体底座专业版",
        product_type="package",
        description="面向中大型企业的 AI 智能体底座",
        unit_price=Decimal("188000.00"),
        unit="套/年",
        version="v1.0.0",
        metadata_json={"max_users": 200, "support": "7x24"},
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["code"] == "DDW-HUB-PRO"
    assert result["name"] == "DDW 智能体底座专业版"
    assert result["product_type"] == "package"
    assert result["unit_price"] == Decimal("188000.00")
    assert result["unit"] == "套/年"
    assert result["version"] == "v1.0.0"
    assert result["is_active"] is True
    assert result["metadata_json"]["max_users"] == 200


# ===========================================================================
# 2. 创建产品（重复 code → ValueError）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_product_duplicate_code(service):
    """重复 code 应抛 ValueError。"""
    req1 = ProductCreateReq(
        code="DDW-PLG-CRM",
        name="DDW 销售插件",
        product_type="plugin",
        unit_price=Decimal("60000.00"),
    )
    await service.create(req1)

    req2 = ProductCreateReq(
        code="DDW-PLG-CRM",
        name="DDW 销售插件 (改名)",
        product_type="plugin",
        unit_price=Decimal("60000.00"),
    )
    with pytest.raises(ValueError, match="已存在"):
        await service.create(req2)


# ===========================================================================
# 3. 列表（分页）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_products_paginated(service):
    """分页：插入 25 条，page=2&page_size=10 应返回 10 条。"""
    for i in range(25):
        await service.create(
            ProductCreateReq(
                code=f"PROD-{i:03d}",
                name=f"产品 {i:02d}",
                product_type="plugin",
                unit_price=Decimal("1000.00"),
            )
        )

    page1 = await service.list(page=1, page_size=10)
    page2 = await service.list(page=2, page_size=10)
    page3 = await service.list(page=3, page_size=10)

    assert page1.total == 25
    assert len(page1.items) == 10
    assert page1.page == 1
    assert len(page2.items) == 10
    assert page3.page == 3
    assert len(page3.items) == 5  # 最后一页只有 5 条


# ===========================================================================
# 4. 列表（按 product_type 筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_products_filter_by_type(service):
    """按 product_type 筛选：plugin vs package。"""
    # 3 个 plugin + 2 个 package
    for i in range(3):
        await service.create(
            ProductCreateReq(
                code=f"PLG-{i}",
                name=f"插件 {i}",
                product_type="plugin",
                unit_price=Decimal("1000.00"),
            )
        )
    for i in range(2):
        await service.create(
            ProductCreateReq(
                code=f"PKG-{i}",
                name=f"套餐 {i}",
                product_type="package",
                unit_price=Decimal("5000.00"),
            )
        )

    plugins = await service.list(page=1, page_size=20, product_type="plugin")
    packages = await service.list(page=1, page_size=20, product_type="package")
    services_all = await service.list(page=1, page_size=20, product_type="service")

    assert plugins.total == 3
    assert all(p.product_type == "plugin" for p in plugins.items)
    assert packages.total == 2
    assert all(p.product_type == "package" for p in packages.items)
    # 没有任何 service 类型
    assert services_all.total == 0


# ===========================================================================
# 5. 列表（按 is_active 筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_products_filter_by_active(service):
    """按 is_active 筛选：active / inactive / None。"""
    # 4 个 active
    for i in range(4):
        await service.create(
            ProductCreateReq(
                code=f"ACT-{i}",
                name=f"上架产品 {i}",
                product_type="plugin",
                unit_price=Decimal("100.00"),
            )
        )
    # 2 个 inactive（先创建后软删）
    for i in range(2):
        r = await service.create(
            ProductCreateReq(
                code=f"INA-{i}",
                name=f"下架产品 {i}",
                product_type="plugin",
                unit_price=Decimal("100.00"),
            )
        )
        await service.deactivate(r["id"])

    active = await service.list(page=1, page_size=20, is_active=True)
    inactive = await service.list(page=1, page_size=20, is_active=False)
    all_p = await service.list(page=1, page_size=20, is_active=None)

    assert active.total == 4
    assert all(p.is_active is True for p in active.items)
    assert inactive.total == 2
    assert all(p.is_active is False for p in inactive.items)
    assert all_p.total == 6


# ===========================================================================
# 6. 产品详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_product_detail(service):
    """获取详情。"""
    created = await service.create(
        ProductCreateReq(
            code="DDW-TOK-100K",
            name="Token 套餐 10 万次",
            product_type="token",
            description="API 调用 Token 套餐",
            unit_price=Decimal("980.00"),
            unit="套",
            version="v2.1.0",
        )
    )
    pid = created["id"]

    detail = await service.get(pid)
    assert detail is not None
    assert detail["id"] == pid
    assert detail["code"] == "DDW-TOK-100K"
    assert detail["product_type"] == "token"
    assert detail["unit_price"] == Decimal("980.00")
    assert detail["unit"] == "套"
    assert detail["version"] == "v2.1.0"


# ===========================================================================
# 7. 更新产品
# ===========================================================================


@pytest.mark.asyncio
async def test_update_product(service):
    """更新产品字段。"""
    created = await service.create(
        ProductCreateReq(
            code="DDW-SVC-IMPL",
            name="实施服务 v1",
            product_type="service",
            unit_price=Decimal("3000.00"),
            unit="次",
        )
    )
    pid = created["id"]

    update = ProductUpdateReq(
        name="实施服务 v2（远程）",
        unit_price=Decimal("2500.00"),
        version="v2.0.0",
        metadata_json={"remote": True, "duration_days": 10},
    )
    result = await service.update(pid, update)
    assert result is not None
    assert result["name"] == "实施服务 v2（远程）"
    assert result["unit_price"] == Decimal("2500.00")
    assert result["version"] == "v2.0.0"
    assert result["metadata_json"]["remote"] is True
    # code 未变（不可通过 update 改）
    assert result["code"] == "DDW-SVC-IMPL"


# ===========================================================================
# 8. 软删除产品
# ===========================================================================


@pytest.mark.asyncio
async def test_deactivate_product(service):
    """软删除产品（is_active=False）。"""
    created = await service.create(
        ProductCreateReq(
            code="DDW-PLG-OLD",
            name="旧版 CRM 插件",
            product_type="plugin",
            unit_price=Decimal("50000.00"),
        )
    )
    pid = created["id"]

    result = await service.deactivate(pid)
    assert result is not None
    assert result["is_active"] is False

    # 软删后从默认激活列表中找不到
    active_list = await service.list(page=1, page_size=20, is_active=True)
    assert all(p.id != pid for p in active_list.items)

    # 但在 inactive 列表中能找到
    inactive_list = await service.list(page=1, page_size=20, is_active=False)
    assert any(p.id == pid for p in inactive_list.items)


# ===========================================================================
# 9. 搜索（按 code/name 模糊）
# ===========================================================================


@pytest.mark.asyncio
async def test_search_product(service):
    """按 code/name 模糊搜索：仅返回 is_active=True。"""
    await service.create(
        ProductCreateReq(
            code="DDW-HUB-STD",
            name="DDW 智能体底座标准版",
            product_type="package",
            unit_price=Decimal("88000.00"),
        )
    )
    await service.create(
        ProductCreateReq(
            code="DDW-HUB-ENT",
            name="DDW 智能体底座企业版",
            product_type="package",
            unit_price=Decimal("388000.00"),
        )
    )
    await service.create(
        ProductCreateReq(
            code="DDW-PLG-CRM",
            name="DDW 销售 CRM 插件",
            product_type="plugin",
            unit_price=Decimal("60000.00"),
        )
    )
    # 一个 inactive 的"底座"产品，搜索时不应返回
    old = await service.create(
        ProductCreateReq(
            code="DDW-HUB-OLD",
            name="DDW 智能体底座停售版",
            product_type="package",
            unit_price=Decimal("0.00"),
        )
    )
    await service.deactivate(old["id"])

    by_name = await service.search(q="智能体底座", limit=10)
    # 排除 inactive 的停售版
    assert len(by_name) == 2
    assert all("智能体底座" in p["name"] for p in by_name)
    assert all(p["is_active"] is True for p in by_name)

    by_code = await service.search(q="DDW-HUB", limit=10)
    # 含 STD + ENT（OLD 被软删不返回）
    assert len(by_code) == 2
    assert all("DDW-HUB" in p["code"] for p in by_code)


# ===========================================================================
# 10. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：total/active/inactive + by_product_type。"""
    # 3 active package + 2 active plugin + 1 active service + 1 inactive plugin
    for i in range(3):
        await service.create(
            ProductCreateReq(
                code=f"PKG-{i}",
                name=f"套餐 {i}",
                product_type="package",
                unit_price=Decimal("10000.00"),
            )
        )
    for i in range(2):
        await service.create(
            ProductCreateReq(
                code=f"PLG-{i}",
                name=f"插件 {i}",
                product_type="plugin",
                unit_price=Decimal("1000.00"),
            )
        )
    await service.create(
        ProductCreateReq(
            code="SVC-1",
            name="实施服务",
            product_type="service",
            unit_price=Decimal("3000.00"),
        )
    )
    inactive = await service.create(
        ProductCreateReq(
            code="PLG-OLD",
            name="下架插件",
            product_type="plugin",
            unit_price=Decimal("1000.00"),
        )
    )
    await service.deactivate(inactive["id"])

    stats = await service.stats()
    assert stats.total == 7
    assert stats.active == 6
    assert stats.inactive == 1
    assert stats.by_product_type.get("package") == 3
    assert stats.by_product_type.get("plugin") == 3  # 2 active + 1 inactive
    assert stats.by_product_type.get("service") == 1
