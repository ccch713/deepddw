from __future__ import annotations

"""DDW 合同中心插件测试用例（16 个，覆盖核心 CRUD + 单号生成 + 状态机 + 统计）。"""

import re
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from plugins.ddw_contract_core.schemas import (
    ContractCreateReq,
    ContractUpdateReq,
    RejectReq,
    TerminateReq,
)
from plugins.ddw_contract_core.services import (
    ALLOWED_TRANSITIONS,
    validate_transition,
)

# ===========================================================================
# 1. 创建合同（正常）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_contract(service):
    """正常创建合同，状态默认 draft，单号自动生成。"""
    req = ContractCreateReq(
        title="DDW 底座采购合同",
        contract_type="standard",
        total_amount=Decimal("120000.00"),
        currency="CNY",
        payment_terms="合同签订后 30 日内一次性付款",
        deliverables="DDW 底座 + 5 个 CRM 插件",
        sla="99.5%",
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["title"] == "DDW 底座采购合同"
    assert result["contract_type"] == "standard"
    assert result["total_amount"] == Decimal("120000.00")
    assert result["currency"] == "CNY"
    assert result["status"] == "draft"
    assert result["version"] == 1
    # 单号格式校验
    assert result["contract_no"].startswith("CT-")
    assert result["attachments"] == []


# ===========================================================================
# 2. 合同号自动生成（格式 CT-YYYYMMDD-NNN）
# ===========================================================================


@pytest.mark.asyncio
async def test_contract_no_auto_generation(service):
    """连续创建 3 份合同，单号递增 001 → 003，格式符合 CT-YYYYMMDD-NNN。"""
    today = date.today().strftime("%Y%m%d")
    pattern = re.compile(rf"^CT-{today}-(\d{{3}})$")

    for i in range(3):
        req = ContractCreateReq(title=f"测试合同 {i + 1}")
        result = await service.create(req)
        m = pattern.match(result["contract_no"])
        assert m is not None, f"单号格式不符: {result['contract_no']}"
        assert m.group(1) == f"{i + 1:03d}"


# ===========================================================================
# 3. 合同号唯一性
# ===========================================================================


@pytest.mark.asyncio
async def test_contract_no_uniqueness(service, seeded_db):
    """unique 约束保证单号不重复（直接 ORM 插入重复值应抛 IntegrityError）。"""
    from plugins.ddw_contract_core.models import Contract
    from plugins.ddw_contract_core.services import generate_contract_no

    no = await generate_contract_no(seeded_db)
    c1 = Contract(tenant_id=1, contract_no=no, contract_type="standard", version=1)
    seeded_db.add(c1)
    await seeded_db.commit()

    # 直接插入同号 → 触发 unique 约束
    c2 = Contract(tenant_id=1, contract_no=no, contract_type="standard", version=1)
    seeded_db.add(c2)
    with pytest.raises(IntegrityError):
        await seeded_db.commit()
    await seeded_db.rollback()


# ===========================================================================
# 4. 列表（分页）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_contracts_paginated(service):
    """分页：插入 25 条，page=2&page_size=10 应返回 10 条。"""
    for i in range(25):
        await service.create(ContractCreateReq(title=f"合同 {i:02d}"))

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
# 5. 列表（按状态筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_contracts_filter_by_status(service):
    """按 status 筛选。"""
    # 2 draft
    await service.create(ContractCreateReq(title="A"))
    await service.create(ContractCreateReq(title="B"))
    # 1 pending_approval
    c = await service.create(ContractCreateReq(title="C"))
    await service.submit_approval(c["id"])

    drafts = await service.list(page=1, page_size=20, status="draft")
    assert drafts.total == 2

    pending = await service.list(page=1, page_size=20, status="pending_approval")
    assert pending.total == 1
    assert pending.items[0].title == "C"


# ===========================================================================
# 6. 详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_contract_detail(service):
    """获取详情。"""
    created = await service.create(
        ContractCreateReq(
            title="详情测试",
            contract_type="framework",
            total_amount=Decimal("500000"),
        )
    )
    cid = created["id"]
    detail = await service.get(cid)
    assert detail is not None
    assert detail["id"] == cid
    assert detail["title"] == "详情测试"
    assert detail["contract_type"] == "framework"
    assert detail["total_amount"] == Decimal("500000.00")  # Decimal 序列化精度


# ===========================================================================
# 7. 更新合同（draft 状态可改）
# ===========================================================================


@pytest.mark.asyncio
async def test_update_contract_draft(service):
    """更新 draft 状态的合同，所有字段正确更新。"""
    created = await service.create(ContractCreateReq(title="旧标题"))
    cid = created["id"]
    assert created["status"] == "draft"

    upd = ContractUpdateReq(
        title="新标题",
        total_amount=Decimal("99999.00"),
        payment_terms="分期付款",
    )
    result = await service.update(cid, upd)
    assert result is not None
    assert result["title"] == "新标题"
    assert result["total_amount"] == Decimal("99999.00")
    assert result["payment_terms"] == "分期付款"


# ===========================================================================
# 8. 更新合同（active 状态应被阻止）
# ===========================================================================


@pytest.mark.asyncio
async def test_update_contract_active_blocked(service):
    """更新已激活的合同应抛 ValueError（HTTP 400）。"""
    created = await service.create(ContractCreateReq(title="待激活"))
    cid = created["id"]
    # 走到 active 状态
    await service.submit_approval(cid)
    await service.approve(cid)
    await service.sign(cid)
    await service.activate(cid)

    detail = await service.get(cid)
    assert detail["status"] == "active"

    # 尝试更新 → 应抛 ValueError
    with pytest.raises(ValueError, match="不允许修改"):
        await service.update(cid, ContractUpdateReq(title="X"))


# ===========================================================================
# 9. 状态机：合法迁移
# ===========================================================================


@pytest.mark.asyncio
async def test_state_machine_valid_transitions(service):
    """完整状态流：draft → pending_approval → approved → signed → active → completed。"""
    created = await service.create(ContractCreateReq(title="状态流测试"))
    cid = created["id"]

    r1 = await service.submit_approval(cid)
    assert r1["status"] == "pending_approval"

    r2 = await service.approve(cid)
    assert r2["status"] == "approved"
    assert r2["approved_at"] is not None

    r3 = await service.sign(cid)
    assert r3["status"] == "signed"
    assert r3["signed_at"] is not None

    r4 = await service.activate(cid)
    assert r4["status"] == "active"
    assert r4["activated_at"] is not None

    r5 = await service.complete(cid)
    assert r5["status"] == "completed"
    assert r5["completed_at"] is not None


# ===========================================================================
# 10. 状态机：非法迁移
# ===========================================================================


def test_state_machine_invalid_transition():
    """非法迁移：draft → signed 应抛 ValueError。"""
    with pytest.raises(ValueError, match="invalid transition: draft -> signed"):
        validate_transition("draft", "signed")


def test_state_machine_invalid_transition_completed_to_active():
    """终止态不能迁移：completed → active。"""
    with pytest.raises(ValueError, match="invalid transition: completed -> active"):
        validate_transition("completed", "active")


def test_state_machine_invalid_target_status():
    """未知目标状态。"""
    with pytest.raises(ValueError, match="invalid target status"):
        validate_transition("draft", "unknown_status")


def test_state_machine_allowed_table_contains_all_paths():
    """白盒：确认所有合法迁移路径都在 ALLOWED_TRANSITIONS 表中。"""
    # 关键合法迁移必须存在
    assert "pending_approval" in ALLOWED_TRANSITIONS["draft"]
    assert "approved" in ALLOWED_TRANSITIONS["pending_approval"]
    assert "rejected" in ALLOWED_TRANSITIONS["pending_approval"]
    assert "signed" in ALLOWED_TRANSITIONS["approved"]
    assert "active" in ALLOWED_TRANSITIONS["signed"]
    assert "terminated" in ALLOWED_TRANSITIONS["signed"]
    assert "completed" in ALLOWED_TRANSITIONS["active"]
    assert "terminated" in ALLOWED_TRANSITIONS["active"]
    assert "draft" in ALLOWED_TRANSITIONS["rejected"]
    # 终止态不能迁移
    assert ALLOWED_TRANSITIONS["completed"] == set()
    assert ALLOWED_TRANSITIONS["terminated"] == set()


# ===========================================================================
# 11. 提交审批
# ===========================================================================


@pytest.mark.asyncio
async def test_submit_approval(service):
    """提交审批：draft → pending_approval。"""
    created = await service.create(ContractCreateReq(title="待提交"))
    cid = created["id"]
    assert created["status"] == "draft"

    result = await service.submit_approval(cid)
    assert result["status"] == "pending_approval"

    # 重复提交应抛 ValueError（pending_approval 不能再次 submit）
    with pytest.raises(ValueError, match="invalid transition"):
        await service.submit_approval(cid)


# ===========================================================================
# 12. 审批通过
# ===========================================================================


@pytest.mark.asyncio
async def test_approve(service):
    """审批通过：pending_approval → approved，approved_at 自动填充。"""
    created = await service.create(ContractCreateReq(title="待审批"))
    cid = created["id"]
    await service.submit_approval(cid)
    assert (await service.get(cid))["approved_at"] is None

    result = await service.approve(cid)
    assert result["status"] == "approved"
    assert result["approved_at"] is not None
    # 时间戳与现在应非常接近（< 5 秒）
    delta = datetime.now(timezone.utc) - result["approved_at"].replace(tzinfo=timezone.utc)
    assert delta.total_seconds() < 5


# ===========================================================================
# 13. 审批驳回（reason 必填）
# ===========================================================================


@pytest.mark.asyncio
async def test_reject_requires_reason(service):
    """驳回：pending_approval → rejected，reason 必填（Pydantic 强制），写入 reject_reason。"""
    # Pydantic 校验：空 reason → ValidationError
    with pytest.raises(Exception):  # pydantic.ValidationError
        RejectReq(reason="")

    created = await service.create(ContractCreateReq(title="待驳回"))
    cid = created["id"]
    await service.submit_approval(cid)

    result = await service.reject(cid, RejectReq(reason="商务条款需调整"))
    assert result["status"] == "rejected"
    assert result["reject_reason"] == "商务条款需调整"
    assert result["rejected_at"] is not None


# ===========================================================================
# 14. 标记已签（验证 signed_at 时间戳）
# ===========================================================================


@pytest.mark.asyncio
async def test_sign_approved(service):
    """标记已签：approved → signed，signed_at 自动填充。"""
    created = await service.create(ContractCreateReq(title="待签"))
    cid = created["id"]
    await service.submit_approval(cid)
    await service.approve(cid)
    assert (await service.get(cid))["signed_at"] is None

    result = await service.sign(cid)
    assert result["status"] == "signed"
    assert result["signed_at"] is not None
    # 时间戳是 naive（SQLite 不存时区），但能解析为当前时间
    signed_dt = result["signed_at"]
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = (now_naive - signed_dt).total_seconds()
    assert 0 <= delta < 5


# ===========================================================================
# 15. 激活合同
# ===========================================================================


@pytest.mark.asyncio
async def test_activate_signed(service):
    """激活合同：signed → active，activated_at 自动填充。"""
    created = await service.create(ContractCreateReq(title="待激活"))
    cid = created["id"]
    await service.submit_approval(cid)
    await service.approve(cid)
    await service.sign(cid)
    assert (await service.get(cid))["activated_at"] is None

    result = await service.activate(cid)
    assert result["status"] == "active"
    assert result["activated_at"] is not None


# ===========================================================================
# 16. 终止合同
# ===========================================================================


@pytest.mark.asyncio
async def test_terminate_active(service):
    """终止合同：active → terminated，reason 必填，terminate_reason 写入。"""
    # Pydantic 校验：空 reason → ValidationError
    with pytest.raises(Exception):
        TerminateReq(reason="")

    created = await service.create(ContractCreateReq(title="待终止"))
    cid = created["id"]
    await service.submit_approval(cid)
    await service.approve(cid)
    await service.sign(cid)
    await service.activate(cid)

    result = await service.terminate(cid, TerminateReq(reason="客户预算削减"))
    assert result["status"] == "terminated"
    assert result["terminate_reason"] == "客户预算削减"
    assert result["terminated_at"] is not None


# ===========================================================================
# 17. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：各状态计数 + by_type + 金额汇总。"""
    # 3 draft
    for i in range(3):
        await service.create(
            ContractCreateReq(
                title=f"草稿 {i}",
                contract_type="standard",
                total_amount=Decimal("10000"),
            )
        )
    # 1 framework 待审批
    c_pending = await service.create(
        ContractCreateReq(
            title="框架合同",
            contract_type="framework",
            total_amount=Decimal("50000"),
        )
    )
    await service.submit_approval(c_pending["id"])
    # 1 supplementary 已激活
    c_active = await service.create(
        ContractCreateReq(
            title="补充协议",
            contract_type="supplementary",
            total_amount=Decimal("8000"),
        )
    )
    await service.submit_approval(c_active["id"])
    await service.approve(c_active["id"])
    await service.sign(c_active["id"])
    await service.activate(c_active["id"])
    # 1 已完成
    c_done = await service.create(
        ContractCreateReq(
            title="完成合同",
            contract_type="standard",
            total_amount=Decimal("20000"),
        )
    )
    await service.submit_approval(c_done["id"])
    await service.approve(c_done["id"])
    await service.sign(c_done["id"])
    await service.activate(c_done["id"])
    await service.complete(c_done["id"])

    stats = await service.stats()
    assert stats.total == 6
    assert stats.draft == 3
    assert stats.pending_approval == 1
    assert stats.approved == 0
    assert stats.signed == 0
    assert stats.active == 1
    assert stats.completed == 1
    assert stats.terminated == 0
    assert stats.rejected == 0
    # by_type
    assert stats.by_type.get("standard") == 4  # 3 draft + 1 completed
    assert stats.by_type.get("framework") == 1
    assert stats.by_type.get("supplementary") == 1
    # 金额：3*10000 + 50000 + 8000 + 20000 = 108000
    assert stats.total_amount == Decimal("108000.00")
    # active 金额：8000
    assert stats.active_amount == Decimal("8000.00")
    # completed 金额：20000
    assert stats.completed_amount == Decimal("20000.00")
