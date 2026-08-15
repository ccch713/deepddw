from __future__ import annotations

from typing import Optional

"""DDW 销售端 AI 副驾驶插件测试用例（≥7 个）。

设计原则：
- 使用 echo backend LLM（无外部依赖、CI 友好）
- 断言保持宽松：字段存在、类型正确、echo 模式下内容合理
- 因为 echo backend 返回 ``[echo] ...`` 固定格式，**不**对 LLM 输出做严格匹配
- 测试走 service 层（与 P0-5 ddw_sales_dashboard 模式一致；HTTP 层只是 thin wrapper）
- 健康检查通过 TestClient 验证（不需要 DB）
- 跨插件查询：直接 INSERT 种子行到 crm_opportunities / crm_sales_notes /
  crm_quotations / crm_companies / crm_contacts，验证聚合正确
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import update

# 直接 import 模型做种子（与 P0-5 dashboard 测试模式一致）
from plugins.ddw_company_profile.models import Company
from plugins.ddw_contact_hub.models import Contact
from plugins.ddw_opportunity.models import Opportunity
from plugins.ddw_quotation.models import Quotation
from plugins.ddw_sales_note.models import SalesNote

# ---------------------------------------------------------------------------
# 内部 helper：造种子数据
# ---------------------------------------------------------------------------


async def _seed_company(db, **overrides) -> Company:
    """插入一个最小可行 Company。"""
    defaults = {
        "tenant_id": 1,
        "name": "测试客户公司",
        "status": "active",
        "certification_status": "pending",
        "tags": [],
    }
    defaults.update(overrides)
    obj = Company(**defaults)
    db.add(obj)
    await db.flush()
    return obj


async def _seed_contact(db, company_id: Optional[int] = None, **overrides) -> Contact:
    """插入一个最小可行 Contact。"""
    defaults = {
        "tenant_id": 1,
        "name": "测试联系人",
        "status": "active",
        "company_id": company_id,
        "tags": [],
        "groups": [],
    }
    defaults.update(overrides)
    obj = Contact(**defaults)
    db.add(obj)
    await db.flush()
    return obj


async def _seed_opportunity(db, **overrides) -> Opportunity:
    """插入一个最小可行 Opportunity。"""
    defaults = {
        "tenant_id": 1,
        "name": "测试商机",
        "stage": "initial_contact",
        "status": "open",
        "probability": 10,
        "tags": [],
        "estimated_amount": Decimal("100.00"),
        "owner_id": 1,
    }
    defaults.update(overrides)
    obj = Opportunity(**defaults)
    db.add(obj)
    await db.flush()
    return obj


async def _seed_note(db, opportunity_id: int, **overrides) -> SalesNote:
    """插入一个最小可行 SalesNote。"""
    defaults = {
        "tenant_id": 1,
        "opportunity_id": opportunity_id,
        "user_id": 1,
        "note_type": "visit",
        "title": "拜访",
        "content": "拜访沟通内容",
        "tags": [],
        "attachments": [],
    }
    if "visit_date" in overrides:
        defaults["visit_date"] = overrides.pop("visit_date")
    defaults.update(overrides)
    obj = SalesNote(**defaults)
    db.add(obj)
    await db.flush()
    return obj


async def _seed_quotation(db, opportunity_id: Optional[int] = None, **overrides) -> Quotation:
    """插入一个最小可行 Quotation。"""
    defaults = {
        "tenant_id": 1,
        "opportunity_id": opportunity_id,
        "quotation_no": "QT-TEST-001",
        "status": "draft",
        "currency": "CNY",
        "total_amount": Decimal("1000.00"),
        "final_amount": Decimal("1000.00"),
        "discount_rate": Decimal(100),
    }
    defaults.update(overrides)
    obj = Quotation(**defaults)
    db.add(obj)
    await db.flush()
    return obj


# ===========================================================================
# 1. 健康检查（HTTP 层，验证 router 挂载）
# ===========================================================================


@pytest.mark.asyncio
async def test_health(client):
    """/health 返回 200 且字段完整。"""
    resp = await client.get("/api/v1/plugins/ddw-sales-copilot/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plugin"] == "ddw-sales-copilot"
    assert body["version"] == "1.0.0"
    assert body["status"] == "ok"


# ===========================================================================
# 2. 阶段建议
# ===========================================================================


@pytest.mark.asyncio
async def test_stage_suggestion(seeded_db, service):
    """阶段建议：造一个 initial_contact 商机 + 3 条拜访记录，验证返回字段。"""
    db = seeded_db
    opp = await _seed_opportunity(
        db,
        name="锐果 AI 底座采购",
        stage="initial_contact",
        probability=10,
    )
    await _seed_note(db, opp.id, note_type="visit", title="首次拜访", content="介绍产品")
    await _seed_note(db, opp.id, note_type="call", title="电话跟进", content="确认需求")
    await _seed_note(db, opp.id, note_type="meeting", title="技术交流", content="现场 demo")
    await db.commit()

    result = await service.stage_suggestion(opportunity_id=opp.id, tenant_id=1)
    assert result is not None
    # 字段完整性
    assert result.opportunity_id == opp.id
    assert result.opportunity_name == "锐果 AI 底座采购"
    assert result.current_stage == "initial_contact"
    assert result.current_stage_label == "初步接触"
    # 确定性建议：管道下一阶段
    assert result.suggested_stage == "demand_confirmation"
    assert result.suggested_stage_label == "需求确认"
    assert result.probability == 20  # demand_confirmation 默认概率
    # 跨插件查询：拜访记录数
    assert result.recent_notes_count == 3
    # LLM 输出（echo backend）：非空字符串
    assert isinstance(result.reasoning, str)
    assert len(result.reasoning) > 0
    # tenant_id 透传
    assert result.tenant_id == 1


# ===========================================================================
# 3. 风险提示 - low（最近活跃）
# ===========================================================================


@pytest.mark.asyncio
async def test_risk_alert_low(seeded_db, service):
    """低风险：刚 active 的商机 + 阶段靠后（won），stale_days=0 → low。"""
    db = seeded_db
    opp = await _seed_opportunity(
        db,
        name="已成交订单",
        stage="won",
        status="won",
        probability=100,
        won_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    # 加一条最近拜访
    await _seed_note(
        db,
        opp.id,
        note_type="meeting",
        visit_date=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    await db.commit()

    result = await service.risk_alert(opportunity_id=opp.id, tenant_id=1)
    assert result is not None
    assert result.risk_level == "low"
    assert result.risk_score < 0.25
    # 已成交 + 最近有活动 → 无风险因素命中
    # stale_days 容忍 0 或 1（容差）
    assert result.stale_days <= 1
    # LLM alert 非空
    assert isinstance(result.alert, str)
    assert len(result.alert) > 0
    assert result.opportunity_id == opp.id
    assert result.opportunity_name == "已成交订单"


# ===========================================================================
# 4. 风险提示 - high（停滞 18 天 + 早期阶段 + 无拜访）
# ===========================================================================


@pytest.mark.asyncio
async def test_risk_alert_high(seeded_db, service):
    """高风险：18 天未活动 + 早期阶段(initial_contact) + 无拜访记录 → high。"""
    db = seeded_db
    # 插入商机后用 UPDATE 把 updated_at 推到 18 天前
    opp = await _seed_opportunity(
        db,
        name="沉睡商机",
        stage="initial_contact",
        status="open",
        probability=10,
    )
    old_dt = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=18)
    await db.execute(
        update(Opportunity).where(Opportunity.id == opp.id).values(updated_at=old_dt)
    )
    await db.commit()

    result = await service.risk_alert(opportunity_id=opp.id, tenant_id=1)
    assert result is not None
    # 至少 high
    assert result.risk_level == "high"
    # 风险因素至少包含 stale + early_stage
    factors = result.risk_factors
    assert any("stale" in f for f in factors)
    assert any("early_stage" in f for f in factors)
    # 18 天停滞
    assert result.stale_days >= 14
    # 风险分数 >= 0.5
    assert result.risk_score >= 0.5
    # LLM alert 非空
    assert isinstance(result.alert, str)
    assert len(result.alert) > 0


# ===========================================================================
# 5. 行动建议
# ===========================================================================


@pytest.mark.asyncio
async def test_action_suggestion(seeded_db, service):
    """行动建议：商机 + 拜访 + 报价，验证返回 3~5 条 action。"""
    db = seeded_db
    opp = await _seed_opportunity(
        db,
        name="AI 底座采购",
        stage="demand_confirmation",
        status="open",
        probability=20,
        estimated_amount=Decimal("50000.00"),
    )
    await _seed_note(db, opp.id, note_type="visit", content="初次拜访介绍产品")
    await _seed_quotation(
        db,
        opportunity_id=opp.id,
        quotation_no="QT-001",
        status="draft",
    )
    await db.commit()

    result = await service.action_suggestion(opportunity_id=opp.id, tenant_id=1)
    assert result is not None
    assert result.opportunity_id == opp.id
    assert result.current_stage == "demand_confirmation"
    assert result.current_stage_label == "需求确认"
    # 动作清单：1~10 条
    actions = result.actions
    assert isinstance(actions, list)
    assert 1 <= len(actions) <= 10
    assert all(isinstance(a, str) and len(a) > 0 for a in actions)
    # 优先级：合法值
    assert result.priority in ("high", "medium", "low")
    # 上下文摘要
    ctx = result.context_summary
    assert ctx["stage"] == "demand_confirmation"
    assert ctx["quotations_count"] == 1
    assert ctx["notes_count"] == 1
    # LLM reasoning
    assert isinstance(result.reasoning, str)
    assert len(result.reasoning) > 0


# ===========================================================================
# 6. 销售日报
# ===========================================================================


@pytest.mark.asyncio
async def test_daily_report(seeded_db, service):
    """销售日报：owner=1 当日造数据，验证指标聚合 + LLM report 非空。"""
    db = seeded_db
    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # owner=1 当日新增 2 个商机
    for i in range(2):
        await _seed_opportunity(
            db,
            name=f"日报商机 {i}",
            owner_id=1,
            created_at=now,
            updated_at=now,
        )
    # owner=1 当日 3 条沟通
    for i in range(3):
        await _seed_note(
            db,
            opportunity_id=None,
            user_id=1,
            note_type="call" if i % 2 == 0 else "visit",
            content=f"沟通 {i}",
            created_at=now,
        )
    # owner=1 当日 1 个报价
    await _seed_quotation(
        db,
        opportunity_id=None,
        quotation_no="QT-DAY-001",
        created_by=1,
        created_at=now,
    )
    # owner=1 当日 1 个联系人
    await _seed_contact(
        db,
        name="日报新增联系人",
        created_by=1,
        created_at=now,
    )
    # 不属于 owner=1 的对照数据（应该被排除）
    await _seed_opportunity(
        db,
        name="别人商机",
        owner_id=999,
        created_at=now,
    )
    await db.commit()

    result = await service.daily_report(user_id=1, day=today, tenant_id=1)
    assert result.user_id == 1
    assert result.report_date == today
    # 指标：owner=1 当日的数据
    m = result.metrics
    assert m.opportunities_created == 2
    assert m.new_notes == 3
    assert m.new_quotations == 1
    assert m.new_contacts == 1
    # 沟通分类计数：2 call + 1 visit
    assert m.notes_call == 2
    assert m.notes_visit == 1
    # 亮点：至少 2 条
    highlights = result.highlights
    assert isinstance(highlights, list)
    assert len(highlights) >= 2
    # LLM report 非空
    assert isinstance(result.report, str)
    assert len(result.report) > 0
    # tenant_id
    assert result.tenant_id == 1


# ===========================================================================
# 7. 销售周报
# ===========================================================================


@pytest.mark.asyncio
async def test_weekly_report(seeded_db, service):
    """销售周报：owner=1 本周造数据，验证指标聚合 + LLM report。"""
    db = seeded_db
    # 取本周一作为 week_start
    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=today.weekday())  # 本周一
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # owner=1 本周新增 3 个商机
    for i in range(3):
        await _seed_opportunity(
            db,
            name=f"周报商机 {i}",
            owner_id=1,
            created_at=now,
            updated_at=now,
        )
    # owner=1 本周 1 个成交（其 created_at 也落在本周 → 计入 opportunities_created）
    await _seed_opportunity(
        db,
        name="本周成交",
        owner_id=1,
        status="won",
        stage="won",
        probability=100,
        estimated_amount=Decimal("8000.00"),
        won_at=now,
        created_at=now,
        updated_at=now,
    )
    # owner=1 本周 4 条拜访
    for i in range(4):
        await _seed_note(
            db,
            opportunity_id=None,
            user_id=1,
            note_type="visit" if i < 3 else "meeting",
            content=f"周报沟通 {i}",
            created_at=now,
        )
    # owner=1 本周 2 张报价
    for i in range(2):
        await _seed_quotation(
            db,
            opportunity_id=None,
            quotation_no=f"QT-WEEK-{i:03d}",
            created_by=1,
            created_at=now,
        )
    await db.commit()

    result = await service.weekly_report(user_id=1, week_start=week_start, tenant_id=1)
    assert result.user_id == 1
    assert result.week_start == week_start
    # 验证 week_end = week_start + 6 days
    expected_end = week_start + timedelta(days=6)
    assert result.week_end == expected_end
    # 指标
    m = result.metrics
    # 4 = 3 普通新增 + 1 成交（其 created_at 也落在本周）
    assert m.opportunities_created == 4
    assert m.opportunities_won == 1
    assert m.opportunities_lost == 0
    assert m.new_notes == 4
    assert m.new_quotations == 2
    assert m.notes_visit == 3
    assert m.notes_meeting == 1
    # 亮点：包含「成交 1 单」
    highlights = result.highlights
    assert isinstance(highlights, list)
    assert any("成交" in h for h in highlights)
    # LLM report 非空
    assert isinstance(result.report, str)
    assert len(result.report) > 0
    # tenant_id
    assert result.tenant_id == 1
