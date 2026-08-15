from __future__ import annotations

"""DDW 拜访与沟通记录插件测试用例（10 个，覆盖核心 CRUD + 筛选 + 统计 + 硬删除）。"""

from datetime import datetime, timedelta, timezone

import pytest

from plugins.ddw_sales_note.schemas import SalesNoteCreateReq, SalesNoteUpdateReq

# ===========================================================================
# 1. 新建拜访记录
# ===========================================================================


@pytest.mark.asyncio
async def test_create_note_visit(service_with_related):
    """新建拜访记录（visit 类型），所有字段正确填充。"""
    rel = {"company_id": 100, "contact_id": 200, "opportunity_id": 300}
    req = SalesNoteCreateReq(
        tenant_id=1,
        user_id=42,
        company_id=rel["company_id"],
        contact_id=rel["contact_id"],
        opportunity_id=rel["opportunity_id"],
        note_type="visit",
        title="首次拜访",
        content="客户对我方 DDW 底座表示兴趣，约下周技术交流。",
        visit_date=datetime(2026, 8, 1, 10, 30, 0),
        tags=["重要", "首访"],
        attachments=["https://oss.example.com/visit-photo-001.jpg"],
        created_by=42,
    )
    result = await service_with_related.create(req)

    assert result["id"] is not None
    assert result["note_type"] == "visit"
    assert result["title"] == "首次拜访"
    assert result["user_id"] == 42
    assert result["company_id"] == 100
    assert result["contact_id"] == 200
    assert result["opportunity_id"] == 300
    assert result["created_by"] == 42
    assert "重要" in result["tags"]
    assert len(result["attachments"]) == 1
    assert result["visit_date"] is not None


# ===========================================================================
# 2. 新建电话记录
# ===========================================================================


@pytest.mark.asyncio
async def test_create_note_call(service_with_related):
    """新建电话记录（call 类型）。"""
    req = SalesNoteCreateReq(
        tenant_id=1,
        user_id=42,
        company_id=100,
        contact_id=200,
        opportunity_id=300,
        note_type="call",
        title="电话跟进",
        content="与客户 IT 总监电话沟通需求细节。",
    )
    result = await service_with_related.create(req)

    assert result["note_type"] == "call"
    assert result["title"] == "电话跟进"
    assert result["visit_date"] is None  # 未填则为空


# ===========================================================================
# 3. 列表分页
# ===========================================================================


@pytest.mark.asyncio
async def test_list_notes_paginated(service):
    """分页：插入 25 条，page=2&page_size=10 应返回 10 条。"""
    for i in range(25):
        await service.create(
            SalesNoteCreateReq(
                tenant_id=1,
                note_type="visit",
                title=f"拜访 {i:02d}",
                content=f"拜访内容 {i:02d}",
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
    assert len(page3.items) == 5  # 最后一页 5 条


# ===========================================================================
# 4. 按 note_type 筛选
# ===========================================================================


@pytest.mark.asyncio
async def test_list_notes_filter_by_type(service):
    """按 note_type 筛选：插入混合类型，仅筛 call 应只返回 call。"""
    for _ in range(3):
        await service.create(
            SalesNoteCreateReq(tenant_id=1, note_type="visit", content="拜访")
        )
    for _ in range(5):
        await service.create(
            SalesNoteCreateReq(tenant_id=1, note_type="call", content="电话")
        )
    await service.create(
        SalesNoteCreateReq(tenant_id=1, note_type="meeting", content="会议")
    )

    result = await service.list(page=1, page_size=20, note_type="call")
    assert result.total == 5
    assert all(n.note_type == "call" for n in result.items)

    result_meet = await service.list(page=1, page_size=20, note_type="meeting")
    assert result_meet.total == 1
    assert result_meet.items[0].note_type == "meeting"


# ===========================================================================
# 5. 按 visit_date 范围筛选
# ===========================================================================


@pytest.mark.asyncio
async def test_list_notes_filter_by_date_range(service):
    """按 visit_date 范围筛选。"""
    await service.create(
        SalesNoteCreateReq(
            tenant_id=1,
            note_type="visit",
            content="7 月拜访",
            visit_date=datetime(2026, 7, 1, 10, 0, 0),
        )
    )
    await service.create(
        SalesNoteCreateReq(
            tenant_id=1,
            note_type="visit",
            content="8 月拜访",
            visit_date=datetime(2026, 8, 15, 14, 0, 0),
        )
    )
    await service.create(
        SalesNoteCreateReq(
            tenant_id=1,
            note_type="visit",
            content="9 月拜访",
            visit_date=datetime(2026, 9, 1, 9, 0, 0),
        )
    )
    await service.create(
        SalesNoteCreateReq(
            tenant_id=1,
            note_type="call",
            content="无日期电话",
        )
    )

    # 8 月份范围
    result = await service.list(
        page=1,
        page_size=20,
        visit_date_from=datetime(2026, 8, 1, 0, 0, 0),
        visit_date_to=datetime(2026, 8, 31, 23, 59, 59),
    )
    assert result.total == 1
    assert result.items[0].content == "8 月拜访"

    # 大于 7 月 31 日
    result2 = await service.list(
        page=1,
        page_size=20,
        visit_date_from=datetime(2026, 8, 1, 0, 0, 0),
    )
    assert result2.total == 2  # 8 月 + 9 月


# ===========================================================================
# 6. 按商机获取记录
# ===========================================================================


@pytest.mark.asyncio
async def test_get_notes_by_opportunity(service_with_related):
    """按商机获取记录：3 条挂商机 300，1 条挂商机 0。"""
    for i in range(3):
        await service_with_related.create(
            SalesNoteCreateReq(
                tenant_id=1,
                note_type="visit" if i % 2 == 0 else "call",
                content=f"商机 300 沟通 {i}",
                opportunity_id=300,
                visit_date=datetime(2026, 8, 1 + i, 10, 0, 0),
            )
        )
    await service_with_related.create(
        SalesNoteCreateReq(
            tenant_id=1,
            note_type="email",
            content="不挂商机的邮件",
        )
    )

    notes = await service_with_related.list_by_opportunity(300)
    assert len(notes) == 3
    assert all(n["opportunity_id"] == 300 for n in notes)
    # 按 visit_date desc，9 月应在最前
    assert "商机 300 沟通 2" in notes[0]["content"]


# ===========================================================================
# 7. 记录详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_note_detail(service):
    """获取单条记录详情。"""
    created = await service.create(
        SalesNoteCreateReq(
            tenant_id=1,
            user_id=99,
            note_type="meeting",
            title="方案讨论会",
            content="与客户技术团队对齐接口方案。",
            tags=["方案"],
        )
    )
    nid = created["id"]

    detail = await service.get(nid)
    assert detail is not None
    assert detail["id"] == nid
    assert detail["title"] == "方案讨论会"
    assert detail["user_id"] == 99
    assert "方案" in detail["tags"]

    # 不存在的 ID
    missing = await service.get(99999)
    assert missing is None


# ===========================================================================
# 8. 更新记录
# ===========================================================================


@pytest.mark.asyncio
async def test_update_note(service_with_related):
    """更新记录字段。"""
    created = await service_with_related.create(
        SalesNoteCreateReq(
            tenant_id=1,
            note_type="visit",
            title="原标题",
            content="原内容",
            tags=["原始"],
        )
    )
    nid = created["id"]

    update = SalesNoteUpdateReq(
        title="新标题",
        content="新内容",
        tags=["更新", "重要"],
    )
    result = await service_with_related.update(nid, update)
    assert result is not None
    assert result["title"] == "新标题"
    assert result["content"] == "新内容"
    assert "更新" in result["tags"]
    assert "重要" in result["tags"]
    assert "原始" not in result["tags"]

    # 不存在的 ID
    missing = await service_with_related.update(99999, SalesNoteUpdateReq(title="X"))
    assert missing is None


# ===========================================================================
# 9. 硬删除记录
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_note(service):
    """硬删除记录：删后 get 返回 None，列表不再可见。"""
    created = await service.create(
        SalesNoteCreateReq(
            tenant_id=1,
            note_type="wechat",
            content="微信沟通记录",
        )
    )
    nid = created["id"]

    # 删前可查到
    before = await service.get(nid)
    assert before is not None

    # 删除
    ok = await service.delete(nid)
    assert ok is True

    # 删后查不到
    after = await service.get(nid)
    assert after is None

    # 列表中也找不到
    page = await service.list(page=1, page_size=20)
    assert all(n.id != nid for n in page.items)

    # 重复删除返回 False
    ok2 = await service.delete(nid)
    assert ok2 is False


# ===========================================================================
# 10. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：total + by_note_type + 最近 30 天。"""
    # 2 visit + 3 call + 1 meeting
    for _ in range(2):
        await service.create(
            SalesNoteCreateReq(tenant_id=1, note_type="visit", content="v")
        )
    for _ in range(3):
        await service.create(
            SalesNoteCreateReq(tenant_id=1, note_type="call", content="c")
        )
    await service.create(
        SalesNoteCreateReq(tenant_id=1, note_type="meeting", content="m")
    )

    # 加一条近期（5 天前）visit_date 的记录，应进 recent_30d
    recent = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=5)
    await service.create(
        SalesNoteCreateReq(
            tenant_id=1,
            note_type="visit",
            content="近期拜访",
            visit_date=recent,
        )
    )

    # 加一条很早（60 天前）的记录，不应进 recent_30d
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=60)
    await service.create(
        SalesNoteCreateReq(
            tenant_id=1,
            note_type="visit",
            content="远古拜访",
            visit_date=old,
        )
    )

    stats = await service.stats()
    assert stats.total == 8  # 2 visit + 3 call + 1 meeting + 1 recent visit + 1 old visit
    assert stats.by_note_type.get("visit") == 4  # 2 + 1 recent + 1 old
    assert stats.by_note_type.get("call") == 3
    assert stats.by_note_type.get("meeting") == 1
    # 30 天内 visit_date 非空：仅 1 条（recent）
    assert stats.recent_30d == 1
