from __future__ import annotations

"""DDW 联系人管理插件测试用例（11 个，覆盖核心 CRUD + 边界 + 统计）。"""

import pytest

from plugins.ddw_contact_hub.schemas import ContactCreateReq, ContactUpdateReq

# ===========================================================================
# 1. 创建联系人（无 company）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_contact_success(service):
    """正常创建独立联系人（无 company_id）。"""
    req = ContactCreateReq(
        name="张三",
        phone="13800138001",
        email="zhangsan@example.com",
        position="技术总监",
        department="研发中心",
        wechat="zhangsan_wx",
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["name"] == "张三"
    assert result["phone"] == "13800138001"
    assert result["email"] == "zhangsan@example.com"
    assert result["company_id"] is None
    assert result["is_primary"] is False
    assert result["status"] == "active"
    assert result["tags"] == []
    assert result["groups"] == []


# ===========================================================================
# 2. 创建联系人（关联 company_id）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_contact_with_company(service):
    """创建联系人并指定 company_id + is_primary + tags。"""
    req = ContactCreateReq(
        company_id=1001,
        name="李四",
        phone="13800138002",
        position="CEO",
        is_primary=True,
        tags=["VIP", "决策人"],
        groups=["管理层"],
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["name"] == "李四"
    assert result["company_id"] == 1001
    assert result["is_primary"] is True
    assert result["tags"] == ["VIP", "决策人"]
    assert result["groups"] == ["管理层"]


# ===========================================================================
# 3. 联系人列表（分页）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_contacts_paginated(service):
    """分页：插入 25 条，page=2&page_size=10 应返回 10 条。"""
    for i in range(25):
        await service.create(ContactCreateReq(name=f"联系人 {i:02d}"))

    page1 = await service.list(page=1, page_size=10)
    page2 = await service.list(page=2, page_size=10)
    page3 = await service.list(page=3, page_size=10)

    assert page1.total == 25
    assert len(page1.items) == 10
    assert page1.page == 1
    assert len(page2.items) == 10
    assert page2.page == 2
    assert page3.page == 3
    assert len(page3.items) == 5  # 最后一页只有 5 条


# ===========================================================================
# 4. 联系人列表（按 company 筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_contacts_by_company(service):
    """按 company_id 筛选。"""
    for i in range(3):
        await service.create(ContactCreateReq(company_id=2001, name=f"A 企业-{i}"))
    for i in range(2):
        await service.create(ContactCreateReq(company_id=2002, name=f"B 企业-{i}"))
    await service.create(ContactCreateReq(name="独立联系人"))

    r2001 = await service.list(company_id=2001)
    assert r2001.total == 3
    assert all(c.company_id == 2001 for c in r2001.items)

    r2002 = await service.list(company_id=2002)
    assert r2002.total == 2


# ===========================================================================
# 5. 联系人列表（搜索）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_contacts_search(service):
    """按姓名/手机/邮箱/职位/部门模糊搜索。"""
    await service.create(ContactCreateReq(name="王五", phone="13900000001"))
    await service.create(ContactCreateReq(name="赵六", email="zhaoliu@test.com"))
    await service.create(ContactCreateReq(name="孙七", position="产品经理"))

    # 按姓名
    by_name = await service.list(search="王")
    assert by_name.total == 1
    assert by_name.items[0].name == "王五"

    # 按手机
    by_phone = await service.list(search="13900000001")
    assert by_phone.total == 1

    # 按邮箱
    by_email = await service.list(search="zhaoliu")
    assert by_email.total == 1
    assert by_email.items[0].name == "赵六"

    # 按职位
    by_pos = await service.list(search="产品经理")
    assert by_pos.total == 1
    assert by_pos.items[0].name == "孙七"


# ===========================================================================
# 6. 联系人详情（正常）
# ===========================================================================


@pytest.mark.asyncio
async def test_get_contact_detail(service):
    """获取详情。"""
    created = await service.create(
        ContactCreateReq(
            name="详情测试",
            phone="13800000000",
            position="测试工程师",
            notes="备注内容",
        )
    )
    cid = created["id"]
    detail = await service.get(cid)
    assert detail is not None
    assert detail["id"] == cid
    assert detail["name"] == "详情测试"
    assert detail["phone"] == "13800000000"
    assert detail["position"] == "测试工程师"
    assert detail["notes"] == "备注内容"


# ===========================================================================
# 7. 联系人详情（不存在 → None）
# ===========================================================================


@pytest.mark.asyncio
async def test_get_contact_not_found(service):
    """不存在的 ID 返回 None。"""
    result = await service.get(99999)
    assert result is None


# ===========================================================================
# 8. 更新联系人
# ===========================================================================


@pytest.mark.asyncio
async def test_update_contact(service):
    """更新联系人字段。"""
    created = await service.create(ContactCreateReq(name="原始姓名", position="旧职位"))
    cid = created["id"]

    update = ContactUpdateReq(name="新姓名", position="新职位", is_primary=True)
    result = await service.update(cid, update)
    assert result is not None
    assert result["name"] == "新姓名"
    assert result["position"] == "新职位"
    assert result["is_primary"] is True


# ===========================================================================
# 9. 硬删除联系人
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_contact(service):
    """硬删除联系人：删除后 get 返回 None。"""
    created = await service.create(ContactCreateReq(name="待删除"))
    cid = created["id"]

    ok = await service.delete(cid)
    assert ok is True

    # 二次 get 应返回 None
    after = await service.get(cid)
    assert after is None

    # 列表中也不应出现
    lst = await service.list()
    assert all(c["id"] != cid for c in lst.items)

    # 二次 delete 返回 False
    again = await service.delete(cid)
    assert again is False


# ===========================================================================
# 10. by-company 端点
# ===========================================================================


@pytest.mark.asyncio
async def test_get_by_company(service):
    """by-company 端点：返回该企业所有联系人，主联系人排在前。"""
    # A 企业 3 个联系人，其中 1 个主联系人
    await service.create(ContactCreateReq(company_id=3001, name="A-普通-1"))
    await service.create(ContactCreateReq(company_id=3001, name="A-主联系人", is_primary=True))
    await service.create(ContactCreateReq(company_id=3001, name="A-普通-2"))
    # 另一个企业 1 个
    await service.create(ContactCreateReq(company_id=3002, name="B-1"))
    # 独立 1 个
    await service.create(ContactCreateReq(name="独立"))

    items = await service.list_by_company(3001)
    assert len(items) == 3
    # 主联系人应在第一位
    assert items[0]["name"] == "A-主联系人"
    assert items[0]["is_primary"] is True


# ===========================================================================
# 11. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：total/active/inactive/archived + primary + with_company + independent + by_company。

    构造 8 条：
    - 3 个独立 active（活跃-0/1/2）
    - 1 个独立 inactive（暂停，update 状态）
    - 1 个独立 archived（归档，update 状态）
    - 企业 5001：甲-1（普通）+ 甲-主（主联系人）= 2 个
    - 企业 5002：乙-1 = 1 个
    """
    # 3 个独立 active
    for i in range(3):
        await service.create(ContactCreateReq(name=f"活跃-{i}"))
    # 1 个独立，update 成 inactive
    c_inactive = await service.create(ContactCreateReq(name="暂停"))
    await service.update(c_inactive["id"], ContactUpdateReq(status="inactive"))
    # 1 个独立，update 成 archived
    c_archived = await service.create(ContactCreateReq(name="归档"))
    await service.update(c_archived["id"], ContactUpdateReq(status="archived"))
    # 企业 5001：2 个
    await service.create(ContactCreateReq(company_id=5001, name="甲-1"))
    await service.create(ContactCreateReq(company_id=5001, name="甲-主", is_primary=True))
    # 企业 5002：1 个
    await service.create(ContactCreateReq(company_id=5002, name="乙-1"))

    stats = await service.stats()
    assert stats.total == 8
    assert stats.active == 6  # 3 个独立 + 甲-1 + 甲-主 + 乙-1
    assert stats.inactive == 1
    assert stats.archived == 1
    assert stats.primary == 1
    assert stats.with_company == 3  # 甲-1 / 甲-主 / 乙-1
    assert stats.independent == 5  # 活跃-0/1/2 + 暂停 + 归档
    assert stats.by_company == {"5001": 2, "5002": 1}


# ===========================================================================
# 12. 更新不存在的联系人
# ===========================================================================


@pytest.mark.asyncio
async def test_update_contact_not_found(service):
    """更新不存在的联系人返回 None。"""
    result = await service.update(99999, ContactUpdateReq(name="X"))
    assert result is None
