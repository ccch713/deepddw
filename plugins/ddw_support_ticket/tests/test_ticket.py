from __future__ import annotations

"""DDW 售后工单插件测试用例（11 个，覆盖核心 CRUD + 单号生成 + 状态机 + 统计）。"""

import re
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from plugins.ddw_support_ticket.schemas import (
    STATUSES,
    TicketAssignReq,
    TicketCreateReq,
    TicketResolveReq,
    TicketUpdateReq,
)
from plugins.ddw_support_ticket.services import (
    ALLOWED_TRANSITIONS,
    generate_ticket_no,
    validate_transition,
)

# ===========================================================================
# 1. 创建工单（正常）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_ticket(service):
    """正常创建工单，状态默认 open，单号自动生成。"""
    req = TicketCreateReq(
        title="登录页面 500 错误",
        description="客户反馈登录后跳转 dashboard 时 500",
        category="bug",
        priority="high",
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["title"] == "登录页面 500 错误"
    assert result["category"] == "bug"
    assert result["priority"] == "high"
    assert result["status"] == "open"
    # 单号格式校验
    assert result["ticket_no"].startswith("TKT-")
    assert result["resolved_at"] is None
    assert result["resolution"] is None


# ===========================================================================
# 2. 工单号自动生成（格式 TKT-YYYYMMDD-NNN）
# ===========================================================================


@pytest.mark.asyncio
async def test_ticket_no_auto_generation(service):
    """连续创建 3 张工单，单号递增 001 → 003，格式符合 TKT-YYYYMMDD-NNN。"""
    today = date.today().strftime("%Y%m%d")
    pattern = re.compile(rf"^TKT-{today}-(\d{{3}})$")

    for i in range(3):
        req = TicketCreateReq(
            title=f"测试工单 {i + 1}",
            description="测试描述",
        )
        result = await service.create(req)
        m = pattern.match(result["ticket_no"])
        assert m is not None, f"单号格式不符: {result['ticket_no']}"
        assert m.group(1) == f"{i + 1:03d}"


# ===========================================================================
# 3. 列表（分页）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_tickets_paginated(service):
    """分页：插入 25 条，page=2&page_size=10 应返回 10 条。"""
    for i in range(25):
        await service.create(
            TicketCreateReq(title=f"工单 {i:02d}", description="测试")
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
# 4. 列表（按 status 筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_tickets_filter_by_status(service):
    """按 status 筛选。"""
    # 2 open
    t1 = await service.create(TicketCreateReq(title="A", description="a"))
    t2 = await service.create(TicketCreateReq(title="B", description="b"))
    # 1 in_progress
    t3 = await service.create(TicketCreateReq(title="C", description="c"))
    await service.start(t3["id"])

    opens = await service.list(page=1, page_size=20, status="open")
    assert opens.total == 2

    in_prog = await service.list(page=1, page_size=20, status="in_progress")
    assert in_prog.total == 1
    assert in_prog.items[0].id == t3["id"]
    assert in_prog.items[0].title == "C"

    # 关闭
    _ = (t1, t2)


# ===========================================================================
# 5. 列表（按 priority 筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_tickets_filter_by_priority(service):
    """按 priority 筛选。"""
    await service.create(TicketCreateReq(title="P1", description="p", priority="urgent"))
    await service.create(TicketCreateReq(title="P2", description="p", priority="urgent"))
    await service.create(TicketCreateReq(title="P3", description="p", priority="high"))
    await service.create(TicketCreateReq(title="P4", description="p", priority="normal"))

    urgent = await service.list(page=1, page_size=20, priority="urgent")
    assert urgent.total == 2
    assert all(t.priority == "urgent" for t in urgent.items)

    high = await service.list(page=1, page_size=20, priority="high")
    assert high.total == 1

    normal = await service.list(page=1, page_size=20, priority="normal")
    assert normal.total == 1

    # 不传 priority：返回所有
    all_t = await service.list(page=1, page_size=20)
    assert all_t.total == 4


# ===========================================================================
# 6. 详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_ticket_detail(service):
    """获取详情。"""
    created = await service.create(
        TicketCreateReq(
            title="详情测试",
            description="详细描述内容",
            category="question",
            priority="low",
        )
    )
    tid = created["id"]
    detail = await service.get(tid)
    assert detail is not None
    assert detail["id"] == tid
    assert detail["title"] == "详情测试"
    assert detail["category"] == "question"
    assert detail["priority"] == "low"


# ===========================================================================
# 7. 更新工单
# ===========================================================================


@pytest.mark.asyncio
async def test_update_ticket(service):
    """更新工单字段（status 不在 update 内）。"""
    created = await service.create(
        TicketCreateReq(title="旧标题", description="旧描述", priority="low")
    )
    tid = created["id"]

    upd = TicketUpdateReq(
        title="新标题",
        description="新描述",
        priority="high",
        category="bug",
    )
    result = await service.update(tid, upd)
    assert result is not None
    assert result["title"] == "新标题"
    assert result["description"] == "新描述"
    assert result["priority"] == "high"
    assert result["category"] == "bug"
    # status 不变
    assert result["status"] == "open"


# ===========================================================================
# 8. 分配处理人
# ===========================================================================


@pytest.mark.asyncio
async def test_assign_ticket(service):
    """分配处理人：写入 assigned_to，不影响 status。"""
    created = await service.create(
        TicketCreateReq(title="待分配", description="d")
    )
    tid = created["id"]
    assert created["assigned_to"] is None

    result = await service.assign(tid, TicketAssignReq(assigned_to=42))
    assert result["assigned_to"] == 42
    assert result["status"] == "open"  # 状态不变

    # 列表按 assigned_to 筛选
    page = await service.list(page=1, page_size=20, assigned_to=42)
    assert page.total == 1
    assert page.items[0].id == tid


# ===========================================================================
# 9. 状态机：完整工作流 open → in_progress → resolved → closed
# ===========================================================================


@pytest.mark.asyncio
async def test_state_machine_workflow(service):
    """完整状态流：open → in_progress → resolved → closed，时间戳正确填充。"""
    created = await service.create(
        TicketCreateReq(title="状态流测试", description="d")
    )
    tid = created["id"]
    assert created["status"] == "open"
    assert created["resolved_at"] is None

    r1 = await service.start(tid)
    assert r1["status"] == "in_progress"

    r2 = await service.resolve(tid, TicketResolveReq(resolution="已修复"))
    assert r2["status"] == "resolved"
    assert r2["resolution"] == "已修复"
    assert r2["resolved_at"] is not None
    # 时间戳与现在应非常接近（< 5 秒）
    delta = (
        datetime.now(timezone.utc) - r2["resolved_at"].replace(tzinfo=timezone.utc)
    )
    assert delta.total_seconds() < 5

    r3 = await service.close(tid)
    assert r3["status"] == "closed"
    # closed 之后 resolved_at 不被清空
    assert r3["resolved_at"] is not None


# ===========================================================================
# 10. 状态机：非法跳转 open → closed 应被拒绝
# ===========================================================================


@pytest.mark.asyncio
async def test_state_machine_invalid_skip(service):
    """非法跳转：open → closed 抛 ValueError。"""
    created = await service.create(
        TicketCreateReq(title="跳步测试", description="d")
    )
    tid = created["id"]

    # 直接 close（应该失败）
    with pytest.raises(ValueError, match="invalid transition: open -> closed"):
        await service.close(tid)

    # 再试一个跳步：open → resolved 也应失败
    with pytest.raises(ValueError, match="invalid transition: open -> resolved"):
        validate_transition("open", "resolved")

    # 验证白盒：合法路径必须存在
    assert "in_progress" in ALLOWED_TRANSITIONS["open"]
    assert "resolved" in ALLOWED_TRANSITIONS["in_progress"]
    assert "closed" in ALLOWED_TRANSITIONS["resolved"]
    assert ALLOWED_TRANSITIONS["closed"] == set()  # closed 是终止态

    # 合法 status 集合
    assert STATUSES == ["open", "in_progress", "resolved", "closed"]


# ===========================================================================
# 11. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：各状态计数 + by_category + by_priority。"""
    # 2 open bug
    await service.create(
        TicketCreateReq(title="t1", description="d", category="bug", priority="high")
    )
    await service.create(
        TicketCreateReq(title="t2", description="d", category="bug", priority="urgent")
    )
    # 1 in_progress question
    t3 = await service.create(
        TicketCreateReq(title="t3", description="d", category="question", priority="normal")
    )
    await service.start(t3["id"])
    # 1 resolved feature
    t4 = await service.create(
        TicketCreateReq(title="t4", description="d", category="feature", priority="low")
    )
    await service.start(t4["id"])
    await service.resolve(t4["id"], TicketResolveReq(resolution="已交付"))
    # 1 closed complaint
    t5 = await service.create(
        TicketCreateReq(title="t5", description="d", category="complaint", priority="high")
    )
    await service.start(t5["id"])
    await service.resolve(t5["id"], TicketResolveReq(resolution="已回复"))
    await service.close(t5["id"])

    stats = await service.stats()
    assert stats.total == 5
    assert stats.open == 2
    assert stats.in_progress == 1
    assert stats.resolved == 1
    assert stats.closed == 1

    # by_category
    assert stats.by_category.get("bug") == 2
    assert stats.by_category.get("question") == 1
    assert stats.by_category.get("feature") == 1
    assert stats.by_category.get("complaint") == 1

    # by_priority
    assert stats.by_priority.get("high") == 2  # t1 + t5
    assert stats.by_priority.get("urgent") == 1
    assert stats.by_priority.get("normal") == 1
    assert stats.by_priority.get("low") == 1


# ===========================================================================
# 附赠：合法 category / priority 校验
# ===========================================================================


@pytest.mark.asyncio
async def test_create_invalid_category_rejected(service):
    """非法 category 应抛 ValueError。"""
    req = TicketCreateReq(title="x", description="d", category="not_a_category")
    with pytest.raises(ValueError, match="invalid category"):
        await service.create(req)


@pytest.mark.asyncio
async def test_create_invalid_priority_rejected(service):
    """非法 priority 应抛 ValueError。"""
    req = TicketCreateReq(title="x", description="d", priority="critical")
    with pytest.raises(ValueError, match="invalid priority"):
        await service.create(req)


@pytest.mark.asyncio
async def test_resolve_requires_resolution(service):
    """解决工单：resolution 必填（Pydantic 强制）。"""
    # 空 resolution → ValidationError
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TicketResolveReq(resolution="")

    created = await service.create(TicketCreateReq(title="待解决", description="d"))
    await service.start(created["id"])

    # 正常 resolution
    result = await service.resolve(
        created["id"], TicketResolveReq(resolution="修复方案 v2")
    )
    assert result["status"] == "resolved"
    assert result["resolution"] == "修复方案 v2"


@pytest.mark.asyncio
async def test_ticket_no_uniqueness(service, seeded_db):
    """unique 约束保证 ticket_no 不重复（直接 ORM 插入重复值应抛 IntegrityError）。"""
    from plugins.ddw_support_ticket.models import SupportTicket

    no = await generate_ticket_no(seeded_db)
    t1 = SupportTicket(
        tenant_id=1,
        ticket_no=no,
        title="x",
        category="other",
        priority="normal",
        description="d",
        status="open",
    )
    seeded_db.add(t1)
    await seeded_db.commit()

    # 直接插入同号 → 触发 unique 约束
    t2 = SupportTicket(
        tenant_id=1,
        ticket_no=no,
        title="y",
        category="other",
        priority="normal",
        description="d",
        status="open",
    )
    seeded_db.add(t2)
    with pytest.raises(IntegrityError):
        await seeded_db.commit()
    await seeded_db.rollback()
