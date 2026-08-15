from __future__ import annotations

"""DDW 商机管理插件测试用例（12 个，覆盖核心 CRUD + 阶段流转 + 统计）。"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from plugins.ddw_opportunity.schemas import (
    MarkLostReq,
    OpportunityCreateReq,
    OpportunityUpdateReq,
    StageUpdateReq,
)
from plugins.ddw_opportunity.services import (
    STAGE_CODES,
    STAGE_PROBABILITY_MAP,
    STAGES,
    get_default_probability,
)

# ===========================================================================
# 1. 新建商机（无 company/contact）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_opportunity(service):
    """正常新建商机（外键 company_id/contact_id 留空）。"""
    req = OpportunityCreateReq(
        name="锐果互动 2026 智造平台采购",
        source="直销",
        owner_id=42,
        estimated_amount=Decimal("880000.00"),
        expected_close_date=date(2026, 12, 31),
        description="客户为某汽车零部件上市公司，需要 AI 视觉检测模块",
        tags=["重点客户", "AI视觉"],
        created_by=1,
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["name"] == "锐果互动 2026 智造平台采购"
    assert result["company_id"] is None
    assert result["contact_id"] is None
    assert result["owner_id"] == 42
    assert result["source"] == "直销"
    assert result["estimated_amount"] == Decimal("880000.00")
    assert result["stage"] == "initial_contact"  # 默认
    assert result["probability"] == 10  # 默认
    assert result["status"] == "open"
    assert result["won_at"] is None
    assert result["lost_reason"] is None
    assert result["tags"] == ["重点客户", "AI视觉"]


# ===========================================================================
# 2. 商机列表（分页）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_opportunities_paginated(service):
    """分页：插入 25 条，page=1,2,3 各取 10/10/5。"""
    for i in range(25):
        await service.create(OpportunityCreateReq(name=f"商机 {i:02d}"))

    p1 = await service.list(page=1, page_size=10)
    p2 = await service.list(page=2, page_size=10)
    p3 = await service.list(page=3, page_size=10)

    assert p1.total == 25
    assert len(p1.items) == 10
    assert p1.page == 1
    assert len(p2.items) == 10
    assert p3.page == 3
    assert len(p3.items) == 5  # 最后一页


# ===========================================================================
# 3. 按 owner_id 筛选
# ===========================================================================


@pytest.mark.asyncio
async def test_list_opportunities_filter_by_owner(service):
    """按 owner_id 筛选。"""
    await service.create(OpportunityCreateReq(name="A", owner_id=1))
    await service.create(OpportunityCreateReq(name="B", owner_id=1))
    await service.create(OpportunityCreateReq(name="C", owner_id=2))
    await service.create(OpportunityCreateReq(name="D"))  # owner_id=None

    p = await service.list(page=1, page_size=20, owner_id=1)
    assert p.total == 2
    assert {x.name for x in p.items} == {"A", "B"}


# ===========================================================================
# 4. 按 stage 筛选
# ===========================================================================


@pytest.mark.asyncio
async def test_list_opportunities_filter_by_stage(service):
    """按 stage 筛选：先推几条到不同阶段，再筛。"""
    a = await service.create(OpportunityCreateReq(name="A 商机"))
    b = await service.create(OpportunityCreateReq(name="B 商机"))
    _ = await service.create(OpportunityCreateReq(name="C 商机"))
    await service.update_stage(a["id"], StageUpdateReq(stage="demand_confirmation"))
    await service.update_stage(b["id"], StageUpdateReq(stage="proposal_submitted"))

    p = await service.list(page=1, page_size=20, stage="demand_confirmation")
    assert p.total == 1
    assert p.items[0].name == "A 商机"


# ===========================================================================
# 5. 商机详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_opportunity_detail(service):
    """获取详情。"""
    created = await service.create(
        OpportunityCreateReq(name="详情测试", owner_id=7, estimated_amount=Decimal("100000.00"))
    )
    oid = created["id"]
    detail = await service.get(oid)
    assert detail is not None
    assert detail["id"] == oid
    assert detail["name"] == "详情测试"
    assert detail["owner_id"] == 7
    assert detail["estimated_amount"] == Decimal("100000.00")
    assert detail["stage"] == "initial_contact"


@pytest.mark.asyncio
async def test_get_opportunity_not_found(service):
    """不存在的 ID 返回 None。"""
    result = await service.get(99999)
    assert result is None


# ===========================================================================
# 6. 更新商机
# ===========================================================================


@pytest.mark.asyncio
async def test_update_opportunity(service):
    """更新商机字段。"""
    created = await service.create(
        OpportunityCreateReq(name="老名称", source="直销", owner_id=1)
    )
    oid = created["id"]

    update = OpportunityUpdateReq(
        name="新名称",
        source="转介绍",
        owner_id=2,
        estimated_amount=Decimal("500000.00"),
        probability=50,
    )
    result = await service.update(oid, update)
    assert result is not None
    assert result["name"] == "新名称"
    assert result["source"] == "转介绍"
    assert result["owner_id"] == 2
    assert result["estimated_amount"] == Decimal("500000.00")
    assert result["probability"] == 50


# ===========================================================================
# 7. 【关键】更新 stage 自动同步 probability
# ===========================================================================


@pytest.mark.asyncio
async def test_update_stage_auto_syncs_probability(service):
    """核心业务规则：调用 update_stage 必须按 STAGES 表自动重写 probability。"""
    opp = await service.create(
        OpportunityCreateReq(name="阶段流转测试", probability=99)  # 给个反常的初值
    )
    oid = opp["id"]
    # 创建时如果 caller 显式给 probability，应保留 caller 值
    assert opp["probability"] == 99

    # 推进到 demand_confirmation，应自动改为 20
    r1 = await service.update_stage(oid, StageUpdateReq(stage="demand_confirmation"))
    assert r1["stage"] == "demand_confirmation"
    assert r1["probability"] == 20

    # 推进到 proposal_submitted → 40
    r2 = await service.update_stage(oid, StageUpdateReq(stage="proposal_submitted"))
    assert r2["probability"] == 40

    # 推进到 quotation_sent → 60
    r3 = await service.update_stage(oid, StageUpdateReq(stage="quotation_sent"))
    assert r3["probability"] == 60

    # 推进到 negotiation → 75
    r4 = await service.update_stage(oid, StageUpdateReq(stage="negotiation"))
    assert r4["probability"] == 75

    # 推进到 contract_pending → 90
    r5 = await service.update_stage(oid, StageUpdateReq(stage="contract_pending"))
    assert r5["probability"] == 90

    # won → 100
    r6 = await service.update_stage(oid, StageUpdateReq(stage="won"))
    assert r6["probability"] == 100

    # lost → 0
    r7 = await service.update_stage(oid, StageUpdateReq(stage="lost"))
    assert r7["probability"] == 0

    # 非法 stage → ValueError
    with pytest.raises(ValueError, match="非法 stage"):
        await service.update_stage(oid, StageUpdateReq(stage="not_a_stage"))


def test_stage_table_consistency():
    """STAGES 表自身一致性检查：所有 stage code 都唯一，probability 在 0-100。"""
    codes = [c for c, _l, _p in STAGES]
    assert len(codes) == len(set(codes))  # 唯一
    assert STAGE_CODES == set(codes)
    for code, _label, prob in STAGES:
        assert 0 <= prob <= 100
        assert get_default_probability(code) == prob
    # 未知 stage 返回 0
    assert get_default_probability("xxx") == 0
    # 关键 stage 概率值
    assert STAGE_PROBABILITY_MAP["initial_contact"] == 10
    assert STAGE_PROBABILITY_MAP["contract_pending"] == 90
    assert STAGE_PROBABILITY_MAP["won"] == 100
    assert STAGE_PROBABILITY_MAP["lost"] == 0


# ===========================================================================
# 8. 标记成交
# ===========================================================================


@pytest.mark.asyncio
async def test_mark_won(service):
    """标记成交：status=won, stage=won, probability=100, won_at 自动设置。"""
    opp = await service.create(
        OpportunityCreateReq(
            name="成交测试",
            estimated_amount=Decimal("1200000.00"),
            owner_id=1,
        )
    )
    oid = opp["id"]
    assert opp["won_at"] is None

    result = await service.mark_won(oid)
    assert result is not None
    assert result["status"] == "won"
    assert result["stage"] == "won"
    assert result["probability"] == 100
    assert result["won_at"] is not None
    # won_at 是 UTC now，应该是最近的时间
    assert isinstance(result["won_at"], datetime)
    delta = datetime.utcnow() - result["won_at"]
    assert timedelta(seconds=0) <= delta <= timedelta(seconds=5)


# ===========================================================================
# 9. 标记丢单
# ===========================================================================


@pytest.mark.asyncio
async def test_mark_lost(service):
    """标记丢单：status=lost, stage=lost, probability=0, lost_reason 必填。"""
    opp = await service.create(
        OpportunityCreateReq(name="丢单测试", owner_id=1)
    )
    oid = opp["id"]

    result = await service.mark_lost(
        oid, MarkLostReq(lost_reason="客户预算不足，2026 暂缓")
    )
    assert result is not None
    assert result["status"] == "lost"
    assert result["stage"] == "lost"
    assert result["probability"] == 0
    assert result["lost_reason"] == "客户预算不足，2026 暂缓"

    # 丢单后再次 mark_lost 也会覆盖 lost_reason
    result2 = await service.mark_lost(
        oid, MarkLostReq(lost_reason="改原因：选择了友商")
    )
    assert result2["lost_reason"] == "改原因：选择了友商"


def test_mark_lost_requires_reason():
    """MarkLostReq 必须有 lost_reason（Pydantic 强制）。"""
    with pytest.raises(ValidationError):
        MarkLostReq()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        MarkLostReq(lost_reason="")  # 空字符串也不允许（min_length=1）


# ===========================================================================
# 10. 关闭商机
# ===========================================================================


@pytest.mark.asyncio
async def test_close_opportunity(service):
    """DELETE 走软关闭：status=closed。"""
    opp = await service.create(OpportunityCreateReq(name="待关闭"))
    oid = opp["id"]

    result = await service.close(oid)
    assert result is not None
    assert result["status"] == "closed"
    # stage 不变
    assert result["stage"] == "initial_contact"

    # 关闭后从 status=open 默认列表中找不到
    p = await service.list(page=1, page_size=20, status="open")
    assert all(x["id"] != oid for x in p.items)


# ===========================================================================
# 11. 漏斗统计
# ===========================================================================


@pytest.mark.asyncio
async def test_funnel_stats(service):
    """漏斗按 stage 统计 count + total_amount，管道顺序展示。"""
    # 初始接触 2 条，金额共 100
    await service.create(
        OpportunityCreateReq(name="A", estimated_amount=Decimal("60"))
    )
    await service.create(
        OpportunityCreateReq(name="B", estimated_amount=Decimal("40"))
    )
    # 需求确认 1 条
    c = await service.create(
        OpportunityCreateReq(name="C", estimated_amount=Decimal("200"))
    )
    await service.update_stage(c["id"], StageUpdateReq(stage="demand_confirmation"))
    # 报价已发 1 条
    d = await service.create(
        OpportunityCreateReq(name="D", estimated_amount=Decimal("500"))
    )
    await service.update_stage(d["id"], StageUpdateReq(stage="quotation_sent"))
    # 成交 1 条（funnel 只统计 status=open，所以这条不算）
    e = await service.create(
        OpportunityCreateReq(name="E", estimated_amount=Decimal("999"))
    )
    await service.mark_won(e["id"])

    funnel = await service.funnel()
    # 顺序：按 STAGE_DISPLAY_ORDER
    assert [s.stage for s in funnel.stages] == [
        "initial_contact",
        "demand_confirmation",
        "proposal_submitted",
        "quotation_sent",
        "negotiation",
        "contract_pending",
        "won",
        "lost",
    ]
    assert funnel.total == 4  # 不含已成交
    assert funnel.total_amount == Decimal("800")  # 60+40+200+500
    by_stage = {s.stage: s for s in funnel.stages}
    assert by_stage["initial_contact"].count == 2
    assert by_stage["initial_contact"].total_amount == Decimal("100")
    assert by_stage["demand_confirmation"].count == 1
    assert by_stage["demand_confirmation"].total_amount == Decimal("200")
    assert by_stage["quotation_sent"].count == 1
    assert by_stage["proposal_submitted"].count == 0  # 空阶段也保留
    assert by_stage["proposal_submitted"].total_amount == Decimal("0")
    # 已成交的 won 阶段在 funnel 中是 0（因为 funnel 只看 status=open）
    assert by_stage["won"].count == 0


# ===========================================================================
# 12. 概览统计
# ===========================================================================


@pytest.mark.asyncio
async def test_overview_stats(service):
    """概览：total/open/won/lost/closed + total_amount + won_amount + by_stage + by_source。"""
    # 4 open
    await service.create(
        OpportunityCreateReq(
            name="O1", source="直销", estimated_amount=Decimal("100")
        )
    )
    await service.create(
        OpportunityCreateReq(
            name="O2", source="直销", estimated_amount=Decimal("200")
        )
    )
    await service.create(
        OpportunityCreateReq(
            name="O3", source="官网", estimated_amount=Decimal("300")
        )
    )
    await service.create(
        OpportunityCreateReq(
            name="O4", source="展会", estimated_amount=Decimal("400")
        )
    )
    # 1 won
    w = await service.create(
        OpportunityCreateReq(name="WON", source="直销", estimated_amount=Decimal("1000"))
    )
    await service.mark_won(w["id"])
    # 1 lost
    lost_opp = await service.create(
        OpportunityCreateReq(name="LOST", source="转介绍", estimated_amount=Decimal("500"))
    )
    await service.mark_lost(lost_opp["id"], MarkLostReq(lost_reason="预算不足"))
    # 1 closed
    c = await service.create(OpportunityCreateReq(name="CLOSED"))
    await service.close(c["id"])

    stats = await service.stats()
    assert stats.total == 7
    assert stats.open == 4
    assert stats.won == 1
    assert stats.lost == 1
    assert stats.closed == 1
    # total_amount = 100+200+300+400+1000+500+0 = 2500
    assert stats.total_amount == Decimal("2500")
    # won_amount = 1000
    assert stats.won_amount == Decimal("1000")
    # by_source: 直销=3, 官网=1, 展会=1, 转介绍=1
    assert stats.by_source.get("直销") == 3
    assert stats.by_source.get("官网") == 1
    assert stats.by_source.get("展会") == 1
    assert stats.by_source.get("转介绍") == 1
    # by_stage: initial_contact = 4 open + 1 closed(close 不改 stage) = 5
    # won/lost 各 1（mark_won/mark_lost 改 stage）
    assert stats.by_stage.get("initial_contact") == 5
    assert stats.by_stage.get("won") == 1
    assert stats.by_stage.get("lost") == 1
    # by_status
    assert stats.by_status.get("open") == 4
    assert stats.by_status.get("won") == 1
    assert stats.by_status.get("lost") == 1
    assert stats.by_status.get("closed") == 1
