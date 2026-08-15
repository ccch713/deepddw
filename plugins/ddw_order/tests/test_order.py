from __future__ import annotations

"""DDW 订单管理插件测试用例（15 个，覆盖核心 CRUD + 单号生成 + 金额计算 + 状态机 + 取消 + 统计）。"""

import re
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from plugins.ddw_order.models import Order
from plugins.ddw_order.schemas import (
    OrderCancelReq,
    OrderCreateReq,
    OrderItemReq,
    OrderUpdateReq,
)
from plugins.ddw_order.services import generate_order_no, validate_transition

# ===========================================================================
# 1. 新建订单
# ===========================================================================


@pytest.mark.asyncio
async def test_create_order(service):
    """新建订单：默认 status=pending、自动生成单号、items 透传。"""
    req = OrderCreateReq(
        title="DDW 底座 + 1 个插件",
        items=[
            OrderItemReq(product_name="DDW 底座", quantity=1, unit_price=Decimal("120000.00")),
            OrderItemReq(product_name="销售 CRM 插件群", quantity=1, unit_price=Decimal("60000.00")),
        ],
    )
    result = await service.create(req)

    assert result["id"] is not None
    assert result["title"] == "DDW 底座 + 1 个插件"
    assert result["status"] == "pending"
    assert result["order_no"].startswith("ORD-")
    assert len(result["items"]) == 2
    assert {i["product_name"] for i in result["items"]} == {"DDW 底座", "销售 CRM 插件群"}
    # total_amount = 120000 + 60000 = 180000
    assert result["total_amount"] == Decimal("180000.00")


# ===========================================================================
# 2. 订单号自动生成（格式 ORD-YYYYMMDD-NNN）
# ===========================================================================


@pytest.mark.asyncio
async def test_order_no_auto_generation(service):
    """连续创建 3 张单，单号递增 001 → 003，格式符合 ORD-YYYYMMDD-NNN。"""
    today = date.today().strftime("%Y%m%d")
    pattern = re.compile(rf"^ORD-{today}-(\d{{3}})$")

    for i in range(3):
        req = OrderCreateReq(
            title=f"订单 {i + 1}",
            items=[OrderItemReq(product_name="商品 A", unit_price=Decimal("100"))],
        )
        result = await service.create(req)
        m = pattern.match(result["order_no"])
        assert m is not None, f"单号格式不符: {result['order_no']}"
        assert m.group(1) == f"{i + 1:03d}"


# ===========================================================================
# 3. 订单号唯一性
# ===========================================================================


@pytest.mark.asyncio
async def test_order_no_uniqueness(service, seeded_db):
    """unique 约束保证单号不重复（直接 ORM 插入重复值应抛 IntegrityError）。"""
    no = await generate_order_no(seeded_db)
    o1 = Order(tenant_id=1, order_no=no, status="pending")
    seeded_db.add(o1)
    await seeded_db.commit()

    # 直接插入同号 → 触发 unique 约束
    o2 = Order(tenant_id=1, order_no=no, status="pending")
    seeded_db.add(o2)
    with pytest.raises(IntegrityError):
        await seeded_db.commit()
    await seeded_db.rollback()


# ===========================================================================
# 4. total_amount 按 items 累加
# ===========================================================================


@pytest.mark.asyncio
async def test_total_amount_with_items(service):
    """total_amount = sum(item.amount or quantity × unit_price)。"""
    req = OrderCreateReq(
        items=[
            OrderItemReq(product_name="A", quantity=2, unit_price=Decimal("100.00")),
            OrderItemReq(product_name="B", quantity=3, unit_price=Decimal("50.50")),
            OrderItemReq(product_name="C", quantity=1, amount=Decimal("999.00")),  # 显式 amount
        ],
    )
    result = await service.create(req)
    # 2*100 + 3*50.50 + 999 = 200 + 151.50 + 999 = 1350.50
    assert result["total_amount"] == Decimal("1350.50")


# ===========================================================================
# 5. 列表（分页 + 搜索 + 多维筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_orders(service, seeded_company):
    """分页 + 模糊搜索 + 按 status / company_id 筛选。"""
    # 4 张订单关联到 company=100，1 张独立订单
    for i in range(4):
        await service.create(
            OrderCreateReq(
                title=f"制造业订单 {i:02d}",
                company_id=100,
                items=[OrderItemReq(product_name="DDW 底座")],
            )
        )
    await service.create(
        OrderCreateReq(
            title="金融 CRM 试点",
            items=[OrderItemReq(product_name="金融插件")],
        )
    )

    # 全量
    page1 = await service.list(page=1, page_size=2)
    assert page1.total == 5
    assert len(page1.items) == 2
    page3 = await service.list(page=3, page_size=2)
    assert len(page3.items) == 1

    # 搜索
    hit = await service.list(page=1, page_size=20, search="金融")
    assert hit.total == 1
    assert hit.items[0].title == "金融 CRM 试点"

    # 状态过滤
    drafts = await service.list(page=1, page_size=20, status="pending")
    assert drafts.total == 5

    # 公司过滤
    by_company = await service.list(page=1, page_size=20, company_id=100)
    assert by_company.total == 4

    # 组合：公司 + 状态
    combo = await service.list(
        page=1, page_size=20, company_id=100, status="pending"
    )
    assert combo.total == 4


# ===========================================================================
# 6. 订单详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_order_detail(service):
    """get 返回完整字段（含 items、status、时间戳为 None）。"""
    created = await service.create(
        OrderCreateReq(
            title="详情单",
            items=[
                OrderItemReq(product_name="A", quantity=2, unit_price=Decimal("100")),
                OrderItemReq(product_name="B", quantity=1, unit_price=Decimal("300")),
            ],
        )
    )
    oid = created["id"]
    detail = await service.get(oid)
    assert detail is not None
    assert detail["id"] == oid
    assert detail["title"] == "详情单"
    assert detail["status"] == "pending"
    assert detail["total_amount"] == Decimal("500.00")
    assert len(detail["items"]) == 2
    # 时间戳字段均为 None（仅 pending）
    assert detail["confirmed_at"] is None
    assert detail["delivered_at"] is None
    assert detail["completed_at"] is None
    assert detail["cancelled_at"] is None
    assert detail["cancel_reason"] is None

    # 不存在 → None
    assert await service.get(99999) is None


# ===========================================================================
# 7. 更新 pending 订单（含 items 整体替换 + total 重算）
# ===========================================================================


@pytest.mark.asyncio
async def test_update_order_pending(service):
    """更新 pending 订单：字段级更新、items 整体替换、total 重算。"""
    created = await service.create(
        OrderCreateReq(
            title="旧标题",
            items=[
                OrderItemReq(product_name="旧 A", quantity=1, unit_price=Decimal("100")),
                OrderItemReq(product_name="旧 B", quantity=1, unit_price=Decimal("200")),
            ],
        )
    )
    oid = created["id"]
    # 原始 total = 300
    assert created["total_amount"] == Decimal("300.00")

    # 更新：换标题 + 换 items
    upd = OrderUpdateReq(
        title="新标题",
        items=[
            OrderItemReq(product_name="新 A", quantity=2, unit_price=Decimal("150")),
            OrderItemReq(product_name="新 B", quantity=1, unit_price=Decimal("100")),
        ],
    )
    result = await service.update(oid, upd)
    assert result is not None
    assert result["title"] == "新标题"
    # 新 total = 2*150 + 1*100 = 400
    assert result["total_amount"] == Decimal("400.00")
    assert len(result["items"]) == 2
    assert {i["product_name"] for i in result["items"]} == {"新 A", "新 B"}

    # 仅改 notes（不传 items）→ total 不变
    upd2 = OrderUpdateReq(notes="加急")
    result2 = await service.update(oid, upd2)
    assert result2["notes"] == "加急"
    assert result2["total_amount"] == Decimal("400.00")

    # 清空 items → total = 0
    upd3 = OrderUpdateReq(items=[])
    result3 = await service.update(oid, upd3)
    assert result3["items"] == []
    assert result3["total_amount"] == Decimal("0.00")

    # 不存在 → None
    assert await service.update(99999, OrderUpdateReq(notes="x")) is None


# ===========================================================================
# 8. 状态机合法迁移完整流程
# ===========================================================================


@pytest.mark.asyncio
async def test_state_machine_valid_transitions(service):
    """完整路径：pending → confirmed → delivered → completed。"""
    created = await service.create(
        OrderCreateReq(items=[OrderItemReq(product_name="商品 A")])
    )
    oid = created["id"]
    assert created["status"] == "pending"
    assert created["confirmed_at"] is None

    # pending → confirmed
    c = await service.confirm(oid)
    assert c is not None
    assert c["status"] == "confirmed"
    assert c["confirmed_at"] is not None

    # confirmed → delivered
    d = await service.deliver(oid)
    assert d is not None
    assert d["status"] == "delivered"
    assert d["delivered_at"] is not None

    # delivered → completed
    done = await service.complete(oid)
    assert done is not None
    assert done["status"] == "completed"
    assert done["completed_at"] is not None

    # completed 终态：再 confirm 应抛错
    with pytest.raises(ValueError, match="不允许迁移"):
        await service.confirm(oid)


# ===========================================================================
# 9. 状态机非法迁移
# ===========================================================================


@pytest.mark.asyncio
async def test_state_machine_invalid_transition(service):
    """非法迁移（pending → completed 跳过中间态）抛 ValueError。"""
    created = await service.create(
        OrderCreateReq(items=[OrderItemReq(product_name="商品 A")])
    )
    oid = created["id"]

    # pending 不允许直接 deliver
    with pytest.raises(ValueError, match="不允许迁移"):
        await service.deliver(oid)
    # pending 不允许直接 complete
    with pytest.raises(ValueError, match="不允许迁移"):
        await service.complete(oid)

    # confirmed 后再 confirm 应抛错
    await service.confirm(oid)
    with pytest.raises(ValueError, match="不允许迁移"):
        await service.confirm(oid)
    # confirmed 后 complete 应抛错（必须先 deliver）
    with pytest.raises(ValueError, match="不允许迁移"):
        await service.complete(oid)

    # validate_transition 直接调用也抛错
    with pytest.raises(ValueError):
        validate_transition("pending", "completed")
    with pytest.raises(ValueError):
        validate_transition("cancelled", "pending")
    with pytest.raises(ValueError):
        validate_transition("unknown_state", "confirmed")


# ===========================================================================
# 10. 确认订单
# ===========================================================================


@pytest.mark.asyncio
async def test_confirm_order(service):
    """confirm：pending → confirmed，confirmed_at 自动填充。"""
    created = await service.create(
        OrderCreateReq(items=[OrderItemReq(product_name="商品 A")])
    )
    oid = created["id"]

    confirmed = await service.confirm(oid)
    assert confirmed is not None
    assert confirmed["status"] == "confirmed"
    assert confirmed["confirmed_at"] is not None
    # 其他时间戳仍为 None
    assert confirmed["delivered_at"] is None
    assert confirmed["completed_at"] is None
    assert confirmed["cancelled_at"] is None

    # 不存在 → None
    assert await service.confirm(99999) is None


# ===========================================================================
# 11. 交付订单
# ===========================================================================


@pytest.mark.asyncio
async def test_deliver_order(service):
    """deliver：confirmed → delivered，delivered_at 自动填充。"""
    created = await service.create(
        OrderCreateReq(items=[OrderItemReq(product_name="商品 A")])
    )
    oid = created["id"]
    await service.confirm(oid)

    delivered = await service.deliver(oid)
    assert delivered is not None
    assert delivered["status"] == "delivered"
    assert delivered["delivered_at"] is not None
    # confirmed_at 仍在
    assert delivered["confirmed_at"] is not None

    # 不存在 → None
    assert await service.deliver(99999) is None


# ===========================================================================
# 12. 完成订单
# ===========================================================================


@pytest.mark.asyncio
async def test_complete_order(service):
    """complete：delivered → completed，completed_at 自动填充。"""
    created = await service.create(
        OrderCreateReq(items=[OrderItemReq(product_name="商品 A")])
    )
    oid = created["id"]
    await service.confirm(oid)
    await service.deliver(oid)

    done = await service.complete(oid)
    assert done is not None
    assert done["status"] == "completed"
    assert done["completed_at"] is not None
    # 前序时间戳仍在
    assert done["confirmed_at"] is not None
    assert done["delivered_at"] is not None

    # 不存在 → None
    assert await service.complete(99999) is None


# ===========================================================================
# 13. 取消订单（pending / confirmed 都可取消）
# ===========================================================================


@pytest.mark.asyncio
async def test_cancel_order(service):
    """cancel：pending/confirmed → cancelled，cancelled_at + cancel_reason 写入。"""
    # 取消 pending
    o1 = await service.create(
        OrderCreateReq(items=[OrderItemReq(product_name="商品 A")])
    )
    cancelled1 = await service.cancel(o1["id"], OrderCancelReq(reason="客户放弃"))
    assert cancelled1 is not None
    assert cancelled1["status"] == "cancelled"
    assert cancelled1["cancelled_at"] is not None
    assert cancelled1["cancel_reason"] == "客户放弃"

    # 取消 confirmed
    o2 = await service.create(
        OrderCreateReq(items=[OrderItemReq(product_name="商品 B")])
    )
    await service.confirm(o2["id"])
    cancelled2 = await service.cancel(o2["id"], OrderCancelReq(reason="预算砍"))
    assert cancelled2 is not None
    assert cancelled2["status"] == "cancelled"
    assert cancelled2["cancelled_at"] is not None
    assert cancelled2["cancel_reason"] == "预算砍"

    # 不存在 → None
    assert (
        await service.cancel(99999, OrderCancelReq(reason="n/a")) is None
    )


# ===========================================================================
# 14. 取消必填 reason（schema 校验）
# ===========================================================================


@pytest.mark.asyncio
async def test_cancel_requires_reason():
    """OrderCancelReq.reason 必填且非空（min_length=1）。"""
    # 缺 reason → ValidationError
    with pytest.raises(Exception) as exc_info:
        OrderCancelReq()  # type: ignore[call-arg]
    # 空字符串 → ValidationError
    with pytest.raises(Exception) as exc_info2:
        OrderCancelReq(reason="")
    # reason 是核心校验点，确认异常存在
    assert exc_info.value is not None
    assert exc_info2.value is not None

    # 正常 reason 可构造
    req = OrderCancelReq(reason="客户主动放弃")
    assert req.reason == "客户主动放弃"


# ===========================================================================
# 15. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：各状态计数 + 总金额 + 已完成金额。"""
    # pending × 2
    await service.create(
        OrderCreateReq(
            items=[OrderItemReq(product_name="P1", unit_price=Decimal("100"))]
        )
    )
    await service.create(
        OrderCreateReq(
            items=[OrderItemReq(product_name="P2", unit_price=Decimal("200"))]
        )
    )
    # confirmed × 1
    o_cf = await service.create(
        OrderCreateReq(
            items=[OrderItemReq(product_name="C1", unit_price=Decimal("500"))]
        )
    )
    await service.confirm(o_cf["id"])
    # completed × 1（先 confirm → deliver → complete）
    o_done = await service.create(
        OrderCreateReq(
            items=[OrderItemReq(product_name="D1", unit_price=Decimal("1000"))]
        )
    )
    await service.confirm(o_done["id"])
    await service.deliver(o_done["id"])
    await service.complete(o_done["id"])
    # cancelled × 1
    o_cx = await service.create(
        OrderCreateReq(
            items=[OrderItemReq(product_name="X1", unit_price=Decimal("50"))]
        )
    )
    await service.cancel(o_cx["id"], OrderCancelReq(reason="客户放弃"))

    stats = await service.stats()
    assert stats.total == 5
    assert stats.pending == 2
    assert stats.confirmed == 1
    assert stats.delivered == 0
    assert stats.completed == 1
    assert stats.cancelled == 1
    # total_amount = 100 + 200 + 500 + 1000 + 50 = 1850
    assert stats.total_amount == Decimal("1850.00")
    # completed_amount = 1000
    assert stats.completed_amount == Decimal("1000.00")
