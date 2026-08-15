from __future__ import annotations

"""DDW 企业主体管理插件测试用例（10 个，覆盖核心 CRUD + 边界 + 统计）。"""

import pytest

from plugins.ddw_company_profile.schemas import CompanyCreateReq, CompanyUpdateReq

# ===========================================================================
# 1. 创建企业（正常）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_company_success(service):
    """正常创建企业。"""
    req = CompanyCreateReq(
        name="武汉锐果互动信息技术有限公司",
        credit_code="91420100MA0000000X",
        short_name="锐果互动",
        company_type="有限公司",
        legal_representative="张三",
        registered_address="武汉市光谷大道 1 号",
        industry="软件和信息技术服务业",
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["name"] == "武汉锐果互动信息技术有限公司"
    assert result["credit_code"] == "91420100MA0000000X"
    assert result["status"] == "active"
    assert result["certification_status"] == "pending"


# ===========================================================================
# 2. 创建企业（重复信用代码 → ValueError，router 抛 409）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_company_duplicate_credit_code(service):
    """重复 credit_code 应抛 ValueError。"""
    req1 = CompanyCreateReq(name="A 公司", credit_code="91420100MA1111111X")
    await service.create(req1)

    req2 = CompanyCreateReq(name="B 公司", credit_code="91420100MA1111111X")
    with pytest.raises(ValueError, match="已存在"):
        await service.create(req2)


# ===========================================================================
# 3. 企业列表（分页）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_companies_paginated(service):
    """分页：插入 25 条，page=2&page_size=10 应返回 10 条。"""
    for i in range(25):
        await service.create(CompanyCreateReq(name=f"公司 {i:02d}"))

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
# 4. 企业列表（搜索）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_companies_search(service):
    """按名称模糊搜索。"""
    await service.create(CompanyCreateReq(name="阿里巴巴集团"))
    await service.create(CompanyCreateReq(name="腾讯科技"))
    await service.create(CompanyCreateReq(name="百度在线"))

    result = await service.list(page=1, page_size=20, search="阿里")
    assert result.total == 1
    assert result.items[0].name == "阿里巴巴集团"


# ===========================================================================
# 5. 企业详情（正常）
# ===========================================================================


@pytest.mark.asyncio
async def test_get_company_detail(service):
    """获取详情。"""
    created = await service.create(CompanyCreateReq(name="测试公司 X", credit_code="91420100MA2222222X"))
    cid = created["id"]
    detail = await service.get(cid)
    assert detail is not None
    assert detail["id"] == cid
    assert detail["name"] == "测试公司 X"
    assert detail["credit_code"] == "91420100MA2222222X"


# ===========================================================================
# 6. 企业详情（不存在 → None）
# ===========================================================================


@pytest.mark.asyncio
async def test_get_company_not_found(service):
    """不存在的 ID 返回 None。"""
    result = await service.get(99999)
    assert result is None


# ===========================================================================
# 7. 更新企业
# ===========================================================================


@pytest.mark.asyncio
async def test_update_company(service):
    """更新企业字段。"""
    created = await service.create(CompanyCreateReq(name="老名称", short_name="老简称"))
    cid = created["id"]

    update = CompanyUpdateReq(name="新名称", short_name="新简称", industry="制造业")
    result = await service.update(cid, update)
    assert result is not None
    assert result["name"] == "新名称"
    assert result["short_name"] == "新简称"
    assert result["industry"] == "制造业"


# ===========================================================================
# 8. 归档企业
# ===========================================================================


@pytest.mark.asyncio
async def test_archive_company(service):
    """归档企业（status=archived）。"""
    created = await service.create(CompanyCreateReq(name="待归档公司"))
    cid = created["id"]

    result = await service.archive(cid)
    assert result is not None
    assert result["status"] == "archived"

    # 归档后从默认列表（status=active）中找不到
    page = await service.list(page=1, page_size=20, status="active")
    assert all(c.id != cid for c in page.items)


# ===========================================================================
# 9. 搜索（自动补全）
# ===========================================================================


@pytest.mark.asyncio
async def test_search_autocomplete(service):
    """search 接口：按名称/credit_code 模糊匹配。"""
    await service.create(CompanyCreateReq(name="华为技术有限公司", credit_code="91440300MA3333333X"))
    await service.create(CompanyCreateReq(name="华为云", credit_code="91440300MA4444444X"))
    await service.create(CompanyCreateReq(name="中兴通讯", credit_code="91440300MA5555555X"))

    by_name = await service.search(q="华为", limit=10)
    assert len(by_name) == 2
    assert all("华为" in c["name"] for c in by_name)

    by_code = await service.search(q="MA3333333", limit=10)
    assert len(by_code) == 1
    assert by_code[0]["credit_code"] == "91440300MA3333333X"


# ===========================================================================
# 10. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：total/active/inactive/archived + 各维度分组。"""
    # 4 active + 1 archived + 1 inactive
    for i in range(4):
        await service.create(
            CompanyCreateReq(name=f"活跃公司 {i}", company_type="有限公司", industry="IT")
        )
    c1 = await service.create(CompanyCreateReq(name="待归档 1", company_type="股份公司", industry="金融"))
    await service.archive(c1["id"])
    c2 = await service.create(CompanyCreateReq(name="暂停公司", company_type="有限公司", industry="IT"))
    await service.update(c2["id"], CompanyUpdateReq(status="inactive"))

    stats = await service.stats()
    assert stats.total == 6
    assert stats.active == 4
    assert stats.archived == 1
    assert stats.inactive == 1
    # 5 有限公司 = 4 活跃 + 1 inactive（暂停公司）
    assert stats.by_company_type.get("有限公司") == 5
    assert stats.by_company_type.get("股份公司") == 1
    # 5 IT = 4 活跃 + 1 inactive
    assert stats.by_industry.get("IT") == 5
    assert stats.by_industry.get("金融") == 1
    assert stats.by_certification_status.get("pending") == 6


# ===========================================================================
# 11. 更新企业（不存在）
# ===========================================================================


@pytest.mark.asyncio
async def test_update_company_not_found(service):
    """更新不存在的企业返回 None。"""
    result = await service.update(99999, CompanyUpdateReq(name="X"))
    assert result is None
