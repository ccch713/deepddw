from __future__ import annotations

"""DDW 应收管理插件测试用例（12 个，覆盖核心 CRUD + 状态机 + 收款 + 逾期自动标记 + 统计）。"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from plugins.ddw_receivable.schemas import (
    ReceivableCreateReq,
    ReceivableUpdateReq,
    RecordPaymentReq,
)

# ===========================================================================
# 1. 新建应收
# ===========================================================================


@pytest.mark.asyncio
async def test_create_receivable(service):
    """正常创建应收，所有默认值正确：paid_amount=0, status=pending。"""
    req = ReceivableCreateReq(
        company_id=100,
        plan_name="2026 智造项目",
        node_name="首款",
        amount=Decimal("120000.00"),
        due_date=date.today() + timedelta(days=30),
        notes="合同签订后 5 个工作日内",
        created_by=1,
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["node_name"] == "首款"
    assert result["amount"] == Decimal("120000.00")
    assert result["paid_amount"] == Decimal("0")
    assert result["outstanding_amount"] == Decimal("120000.00")
    assert result["status"] == "pending"
    assert result["plan_name"] == "2026 智造项目"
    assert result["company_id"] == 100
    assert result["paid_at"] is None


# ===========================================================================
# 2. 列表（分页 + 筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_receivables(service):
    """分页 + 多维筛选。"""
    for i in range(12):
        await service.create(
            ReceivableCreateReq(
                node_name=f"节点{i}",
                amount=Decimal("1000.00") + Decimal(i),
                due_date=date.today() + timedelta(days=i + 1),
            )
        )

    p1 = await service.list(page=1, page_size=5)
    p2 = await service.list(page=2, page_size=5)
    p3 = await service.list(page=3, page_size=5)

    assert p1.total == 12
    assert len(p1.items) == 5
    assert len(p2.items) == 5
    assert len(p3.items) == 2  # 最后一页

    # 按 due_date 升序：节点 0..11 对应 due_date today+1..today+12
    assert p1.items[0].node_name == "节点0"


# ===========================================================================
# 3. 应收详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_receivable_detail(service):
    """获取详情（含 outstanding 计算字段）。"""
    created = await service.create(
        ReceivableCreateReq(
            node_name="验收款",
            amount=Decimal("50000.00"),
            due_date=date.today() + timedelta(days=60),
        )
    )
    rid = created["id"]

    detail = await service.get(rid)
    assert detail is not None
    assert detail["id"] == rid
    assert detail["node_name"] == "验收款"
    assert detail["amount"] == Decimal("50000.00")
    assert detail["outstanding_amount"] == Decimal("50000.00")
    assert detail["status"] == "pending"

    # 不存在
    assert await service.get(99999) is None


# ===========================================================================
# 4. 更新 pending 状态的应收
# ===========================================================================


@pytest.mark.asyncio
async def test_update_receivable_pending(service):
    """pending 状态允许更新：金额 / 节点 / 备注等。"""
    created = await service.create(
        ReceivableCreateReq(
            node_name="首款",
            amount=Decimal("100000.00"),
            due_date=date.today() + timedelta(days=30),
        )
    )
    rid = created["id"]

    upd = ReceivableUpdateReq(
        node_name="首款（含税）",
        amount=Decimal("113000.00"),  # 含 13% 增值税
        notes="更新为含税金额",
    )
    result = await service.update(rid, upd)
    assert result is not None
    assert result["node_name"] == "首款（含税）"
    assert result["amount"] == Decimal("113000.00")
    assert result["notes"] == "更新为含税金额"


# ===========================================================================
# 5. 部分收款 → status=partial
# ===========================================================================


@pytest.mark.asyncio
async def test_record_partial_payment(service):
    """部分收款：paid_amount=0 < amount, status 变为 partial。"""
    created = await service.create(
        ReceivableCreateReq(
            node_name="部署款",
            amount=Decimal("100000.00"),
            due_date=date.today() + timedelta(days=15),
        )
    )
    rid = created["id"]
    assert created["status"] == "pending"

    result = await service.record_payment(rid, RecordPaymentReq(payment_amount=Decimal("40000.00")))
    assert result is not None
    assert result["paid_amount"] == Decimal("40000.00")
    assert result["outstanding_amount"] == Decimal("60000.00")
    assert result["status"] == "partial"
    assert result["paid_at"] is not None


# ===========================================================================
# 6. 全额收款 → status=paid
# ===========================================================================


@pytest.mark.asyncio
async def test_record_full_payment(service):
    """全额收款：paid_amount == amount, status 变为 paid。"""
    created = await service.create(
        ReceivableCreateReq(
            node_name="验收款",
            amount=Decimal("80000.00"),
            due_date=date.today() + timedelta(days=45),
        )
    )
    rid = created["id"]

    result = await service.record_payment(rid, RecordPaymentReq(payment_amount=Decimal("80000.00")))
    assert result is not None
    assert result["paid_amount"] == Decimal("80000.00")
    assert result["outstanding_amount"] == Decimal("0")
    assert result["status"] == "paid"
    assert result["paid_at"] is not None


# ===========================================================================
# 7. 超额收款（paid_amount > amount）→ 仍 status=paid
# ===========================================================================


@pytest.mark.asyncio
async def test_record_overpayment(service):
    """超额收款：paid_amount > amount 时，状态仍按 paid 处理（业务允许客户多付）。"""
    created = await service.create(
        ReceivableCreateReq(
            node_name="续费款",
            amount=Decimal("50000.00"),
            due_date=date.today() + timedelta(days=90),
        )
    )
    rid = created["id"]

    result = await service.record_payment(rid, RecordPaymentReq(payment_amount=Decimal("55000.00")))
    assert result is not None
    assert result["paid_amount"] == Decimal("55000.00")
    # outstanding 会为负（业务侧理解：客户多付了 5000）
    assert result["outstanding_amount"] == Decimal("-5000.00")
    # 状态仍为 paid（已结清）
    assert result["status"] == "paid"


# ===========================================================================
# 8. 逾期应收自动标记（核心业务规则）
# ===========================================================================


@pytest.mark.asyncio
async def test_overdue_auto_mark(service):
    """due_date < today 的应收，list 调用时应自动被标记为 overdue。"""
    # 插入一个早已过期的应收
    overdue_recv = await service.create(
        ReceivableCreateReq(
            node_name="首款",
            amount=Decimal("50000.00"),
            due_date=date.today() - timedelta(days=10),  # 10 天前到期
        )
    )
    rid = overdue_recv["id"]
    # 创建后 status 仍是 pending（不在 create 时改）
    assert overdue_recv["status"] == "pending"

    # 触发 list 端点（内部会先 _auto_mark_overdue）
    page = await service.list(page=1, page_size=20)
    refreshed = next(x for x in page.items if x.id == rid)
    assert refreshed.status == "overdue"

    # 再次 get 也会拿到 overdue（因为 _auto_mark_overdue 是 write 操作，
    # get 之前不会调用，但上一步已 commit 到 DB，状态已持久化）
    detail = await service.get(rid)
    assert detail["status"] == "overdue"


# ===========================================================================
# 9. 专用 /overdue 端点
# ===========================================================================


@pytest.mark.asyncio
async def test_overdue_endpoint(service):
    """专用 overdue 端点只返回 status=overdue 的应收。"""
    # 3 个应收：1 个过期、1 个未来、1 个过期但已收部分款（仍应被标 overdue）
    await service.create(
        ReceivableCreateReq(
            node_name="过期未收",
            amount=Decimal("10000.00"),
            due_date=date.today() - timedelta(days=30),
        )
    )
    await service.create(
        ReceivableCreateReq(
            node_name="未来应收",
            amount=Decimal("20000.00"),
            due_date=date.today() + timedelta(days=30),
        )
    )
    partial_recv = await service.create(
        ReceivableCreateReq(
            node_name="过期部分",
            amount=Decimal("30000.00"),
            due_date=date.today() - timedelta(days=5),
        )
    )
    await service.record_payment(
        partial_recv["id"], RecordPaymentReq(payment_amount=Decimal("10000.00"))
    )

    overdue = await service.overdue()
    # 2 个应收 status=overdue（"过期未收" + "过期部分"）
    assert overdue.total == 2
    overdue_node_names = {x.node_name for x in overdue.items}
    assert "过期未收" in overdue_node_names
    assert "过期部分" in overdue_node_names
    assert "未来应收" not in overdue_node_names
    # 总额 = sum(amount) = 10000 + 30000 = 40000
    assert overdue.total_overdue_amount == Decimal("40000.00")
    # 未收总额 = sum(amount - paid) = 10000 + (30000 - 10000) = 30000
    assert overdue.total_outstanding_amount == Decimal("30000.00")


# ===========================================================================
# 10. 已付清应收不能改（状态机保护）
# ===========================================================================


@pytest.mark.asyncio
async def test_update_paid_blocked(service):
    """已付清的应收（status=paid）拒绝修改，抛 ValueError。"""
    created = await service.create(
        ReceivableCreateReq(
            node_name="验收款",
            amount=Decimal("60000.00"),
            due_date=date.today() + timedelta(days=30),
        )
    )
    rid = created["id"]
    await service.record_payment(rid, RecordPaymentReq(payment_amount=Decimal("60000.00")))

    upd = ReceivableUpdateReq(notes="试图修改")
    with pytest.raises(ValueError, match="不允许修改"):
        await service.update(rid, upd)


# ===========================================================================
# 11. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：total / 各状态计数 / total_amount / paid_amount / outstanding_amount。

    构造场景：
    - 2 pending（应收 100+200=300）
    - 1 partial（应收 500，收 200）
    - 1 paid（应收 1000，收 1000）
    - 1 overdue（应收 800，paid=0，due<today；list 时被自动标记）
    """
    # 2 pending
    await service.create(
        ReceivableCreateReq(
            node_name="A 首款", amount=Decimal("100.00"),
            due_date=date.today() + timedelta(days=10),
        )
    )
    await service.create(
        ReceivableCreateReq(
            node_name="B 首款", amount=Decimal("200.00"),
            due_date=date.today() + timedelta(days=20),
        )
    )
    # 1 partial
    p = await service.create(
        ReceivableCreateReq(
            node_name="C 部署款", amount=Decimal("500.00"),
            due_date=date.today() + timedelta(days=15),
        )
    )
    await service.record_payment(p["id"], RecordPaymentReq(payment_amount=Decimal("200.00")))
    # 1 paid
    q = await service.create(
        ReceivableCreateReq(
            node_name="D 验收款", amount=Decimal("1000.00"),
            due_date=date.today() + timedelta(days=30),
        )
    )
    await service.record_payment(q["id"], RecordPaymentReq(payment_amount=Decimal("1000.00")))
    # 1 overdue（不主动收款，stats 内部会 _auto_mark_overdue）
    await service.create(
        ReceivableCreateReq(
            node_name="E 续费款", amount=Decimal("800.00"),
            due_date=date.today() - timedelta(days=7),
        )
    )

    stats = await service.stats()
    assert stats.total == 5
    assert stats.pending == 2
    assert stats.partial == 1
    assert stats.paid == 1
    assert stats.overdue == 1
    # total_amount = 100+200+500+1000+800 = 2600
    assert stats.total_amount == Decimal("2600.00")
    # paid_amount = 0+0+200+1000+0 = 1200
    assert stats.paid_amount == Decimal("1200.00")
    # outstanding = 2600 - 1200 = 1400
    assert stats.outstanding_amount == Decimal("1400.00")


# ===========================================================================
# 12. 按企业筛选
# ===========================================================================


@pytest.mark.asyncio
async def test_filter_by_company(service_with_company):
    """按 company_id 筛选：只返回关联该企业的应收。"""
    svc = service_with_company
    # 关联企业 100
    await svc.create(
        ReceivableCreateReq(
            company_id=100, node_name="首款",
            amount=Decimal("100.00"), due_date=date.today() + timedelta(days=10),
        )
    )
    await svc.create(
        ReceivableCreateReq(
            company_id=100, node_name="尾款",
            amount=Decimal("200.00"), due_date=date.today() + timedelta(days=20),
        )
    )
    # 关联企业 200（其他企业）
    await svc.create(
        ReceivableCreateReq(
            company_id=200, node_name="其他客户首款",
            amount=Decimal("999.00"), due_date=date.today() + timedelta(days=10),
        )
    )
    # 无关联企业
    await svc.create(
        ReceivableCreateReq(
            node_name="无关联",
            amount=Decimal("50.00"), due_date=date.today() + timedelta(days=5),
        )
    )

    p = await svc.list(page=1, page_size=20, company_id=100)
    assert p.total == 2
    assert {x.node_name for x in p.items} == {"首款", "尾款"}

    # 同时按 status 过滤：企业 100 的都不是 overdue/partial/paid，应全是 pending
    p2 = await svc.list(page=1, page_size=20, company_id=100, status="pending")
    assert p2.total == 2


# ===========================================================================
# 边界：收款 API 不存在的应收
# ===========================================================================


@pytest.mark.asyncio
async def test_record_payment_not_found(service):
    """对不存在的应收 id 收款应返回 None。"""
    result = await service.record_payment(99999, RecordPaymentReq(payment_amount=Decimal("1.00")))
    assert result is None


@pytest.mark.asyncio
async def test_filter_by_due_date_range(service):
    """按应收日期范围过滤（due_before / due_after）。"""
    # 3 个应收，日期分散
    await service.create(
        ReceivableCreateReq(
            node_name="早期", amount=Decimal("100.00"),
            due_date=date(2026, 1, 15),
        )
    )
    await service.create(
        ReceivableCreateReq(
            node_name="中期", amount=Decimal("200.00"),
            due_date=date(2026, 6, 15),
        )
    )
    await service.create(
        ReceivableCreateReq(
            node_name="晚期", amount=Decimal("300.00"),
            due_date=date(2026, 12, 15),
        )
    )

    # due_after=2026-04-01, due_before=2026-09-30：只命中"中期"
    p = await service.list(
        page=1, page_size=20, due_after=date(2026, 4, 1), due_before=date(2026, 9, 30)
    )
    assert p.total == 1
    assert p.items[0].node_name == "中期"
