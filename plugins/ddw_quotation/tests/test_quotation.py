from __future__ import annotations

"""DDW 报价单管理插件测试用例（12 个，覆盖核心 CRUD + 单号生成 + 金额计算 + 状态机 + 统计 + 级联）。"""

import re
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from plugins.ddw_quotation.models import Quotation, QuotationItem
from plugins.ddw_quotation.schemas import (
    QuotationCreateReq,
    QuotationItemReq,
    QuotationUpdateReq,
)

# ===========================================================================
# 1. 创建报价单（含多个明细）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_quotation_with_items(service_with_related):
    """创建含 2 条明细的报价单，所有字段正确填充（含外键关联）。"""
    service = service_with_related
    req = QuotationCreateReq(
        title="DDW 底座 + 1 个插件试点",
        company_id=100,
        contact_id=200,
        opportunity_id=300,
        items=[
            QuotationItemReq(
                product_name="DDW 底座（年度）",
                product_type="plugin",
                product_code="DDW-BASE-1Y",
                quantity=1,
                unit="套",
                unit_price=Decimal("120000.00"),
                sort_order=1,
            ),
            QuotationItemReq(
                product_name="销售 CRM 插件群",
                product_type="plugin",
                product_code="DDW-CRM-S",
                quantity=1,
                unit="套",
                unit_price=Decimal("60000.00"),
                description="含企业 / 联系人 / 报价单 / 商机",
                sort_order=2,
            ),
        ],
    )
    result = await service.create(req)

    assert result["id"] is not None
    assert result["title"] == "DDW 底座 + 1 个插件试点"
    assert result["company_id"] == 100
    assert result["contact_id"] == 200
    assert result["opportunity_id"] == 300
    assert result["status"] == "draft"
    assert result["currency"] == "CNY"
    assert result["discount_rate"] == Decimal("100")
    # 2 条明细都进了
    assert len(result["items"]) == 2
    item_names = {i["product_name"] for i in result["items"]}
    assert "DDW 底座（年度）" in item_names
    assert "销售 CRM 插件群" in item_names
    # 按 sort_order 升序
    assert result["items"][0]["sort_order"] == 1
    assert result["items"][1]["sort_order"] == 2


# ===========================================================================
# 2. 报价单号自动生成（格式 QT-YYYYMMDD-NNN）
# ===========================================================================


@pytest.mark.asyncio
async def test_quotation_no_auto_generation(service):
    """连续创建 3 张单，单号递增 001 → 003，格式符合 QT-YYYYMMDD-NNN。"""
    today = date.today().strftime("%Y%m%d")
    pattern = re.compile(rf"^QT-{today}-(\d{{3}})$")

    for i in range(3):
        req = QuotationCreateReq(
            title=f"测试单 {i + 1}",
            items=[QuotationItemReq(product_name="商品 A", unit_price=Decimal("100"))],
        )
        result = await service.create(req)
        m = pattern.match(result["quotation_no"])
        assert m is not None, f"单号格式不符: {result['quotation_no']}"
        assert m.group(1) == f"{i + 1:03d}"


# ===========================================================================
# 3. 报价单号唯一性
# ===========================================================================


@pytest.mark.asyncio
async def test_quotation_no_uniqueness(service, seeded_db):
    """unique 约束保证单号不重复（直接 ORM 插入重复值应抛 IntegrityError）。"""
    from plugins.ddw_quotation.services import generate_quotation_no

    no = await generate_quotation_no(seeded_db)
    q1 = Quotation(tenant_id=1, quotation_no=no, currency="CNY", discount_rate=Decimal("100"))
    seeded_db.add(q1)
    await seeded_db.commit()

    # 直接插入同号 → 触发 unique 约束
    q2 = Quotation(tenant_id=1, quotation_no=no, currency="CNY", discount_rate=Decimal("100"))
    seeded_db.add(q2)
    with pytest.raises(IntegrityError):
        await seeded_db.commit()
    await seeded_db.rollback()


# ===========================================================================
# 4. 总金额自动计算
# ===========================================================================


@pytest.mark.asyncio
async def test_total_amount_auto_calculated(service):
    """total_amount = sum(item.quantity × item.unit_price)。"""
    req = QuotationCreateReq(
        items=[
            QuotationItemReq(
                product_name="商品 A", quantity=2, unit_price=Decimal("100"), sort_order=1
            ),
            QuotationItemReq(
                product_name="商品 B", quantity=3, unit_price=Decimal("50"), sort_order=2
            ),
            QuotationItemReq(
                product_name="商品 C", quantity=1, unit_price=Decimal("200.50"), sort_order=3
            ),
        ],
    )
    result = await service.create(req)
    # 2*100 + 3*50 + 1*200.50 = 200 + 150 + 200.50 = 550.50
    assert result["total_amount"] == Decimal("550.50")
    # 没打折，final == total
    assert result["final_amount"] == Decimal("550.50")


# ===========================================================================
# 5. 折后金额（折扣率生效）
# ===========================================================================


@pytest.mark.asyncio
async def test_final_amount_with_discount(service):
    """final_amount = total × discount_rate / 100。"""
    req = QuotationCreateReq(
        discount_rate=Decimal("80"),
        items=[
            QuotationItemReq(
                product_name="商品 A", quantity=1, unit_price=Decimal("1000")
            ),
            QuotationItemReq(
                product_name="商品 B", quantity=2, unit_price=Decimal("500")
            ),
        ],
    )
    result = await service.create(req)
    # total = 1000 + 1000 = 2000
    assert result["total_amount"] == Decimal("2000.00")
    # final = 2000 * 80 / 100 = 1600
    assert result["final_amount"] == Decimal("1600.00")
    assert result["discount_rate"] == Decimal("80")


# ===========================================================================
# 6. 列表（分页 + 搜索）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_quotations(service):
    """分页 + 模糊搜索（按单号 / 标题）。"""
    for i in range(5):
        await service.create(
            QuotationCreateReq(
                title=f"智能制造项目 {i:02d}",
                items=[QuotationItemReq(product_name="DDW 底座")],
            )
        )
    await service.create(
        QuotationCreateReq(
            title="金融 CRM 试点",
            items=[QuotationItemReq(product_name="金融插件")],
        )
    )

    # 全量
    page1 = await service.list(page=1, page_size=3)
    assert page1.total == 6
    assert page1.page == 1
    assert len(page1.items) == 3
    page2 = await service.list(page=2, page_size=3)
    assert len(page2.items) == 3

    # 搜索
    hit = await service.list(page=1, page_size=20, search="金融")
    assert hit.total == 1
    assert hit.items[0].title == "金融 CRM 试点"

    # 状态过滤
    drafts = await service.list(page=1, page_size=20, status="draft")
    assert drafts.total == 6


# ===========================================================================
# 7. 详情（含 items）
# ===========================================================================


@pytest.mark.asyncio
async def test_get_quotation_with_items(service):
    """get 返回的明细完整、按 sort_order 升序。"""
    created = await service.create(
        QuotationCreateReq(
            items=[
                QuotationItemReq(
                    product_name="C", quantity=1, unit_price=Decimal("10"), sort_order=3
                ),
                QuotationItemReq(
                    product_name="A", quantity=2, unit_price=Decimal("20"), sort_order=1
                ),
                QuotationItemReq(
                    product_name="B", quantity=3, unit_price=Decimal("30"), sort_order=2
                ),
            ],
        )
    )
    qid = created["id"]
    detail = await service.get(qid)
    assert detail is not None
    assert detail["id"] == qid
    assert len(detail["items"]) == 3
    # sort_order 升序：A(1) → B(2) → C(3)
    assert [i["product_name"] for i in detail["items"]] == ["A", "B", "C"]


# ===========================================================================
# 8. 更新（items 级联重建）
# ===========================================================================


@pytest.mark.asyncio
async def test_update_quotation(service, seeded_db):
    """更新 items 时，旧 items 被删除、新 items 重建、金额重算。"""
    created = await service.create(
        QuotationCreateReq(
            title="旧标题",
            items=[
                QuotationItemReq(
                    product_name="旧 1", quantity=1, unit_price=Decimal("100")
                ),
                QuotationItemReq(
                    product_name="旧 2", quantity=1, unit_price=Decimal("200")
                ),
            ],
        )
    )
    qid = created["id"]

    # 验证：原始 2 条，total = 300
    assert len(created["items"]) == 2
    assert created["total_amount"] == Decimal("300.00")

    # 更新：换标题 + 换 items + 加折扣
    upd = QuotationUpdateReq(
        title="新标题",
        discount_rate=Decimal("50"),
        items=[
            QuotationItemReq(
                product_name="新 A", quantity=2, unit_price=Decimal("150")
            ),
            QuotationItemReq(
                product_name="新 B", quantity=1, unit_price=Decimal("100")
            ),
        ],
    )
    result = await service.update(qid, upd)
    assert result is not None
    assert result["title"] == "新标题"
    # 新明细：400 * 0.5 = 200
    assert result["total_amount"] == Decimal("400.00")
    assert result["final_amount"] == Decimal("200.00")
    assert result["discount_rate"] == Decimal("50")
    # 旧明细已清，新明细只 2 条
    assert len(result["items"]) == 2
    names = {i["product_name"] for i in result["items"]}
    assert names == {"新 A", "新 B"}

    # 数据库层面再确认旧 items 真的没了
    rows = (
        await seeded_db.execute(select(QuotationItem).where(QuotationItem.quotation_id == qid))
    ).scalars().all()
    assert len(rows) == 2
    assert {r.product_name for r in rows} == {"新 A", "新 B"}


# ===========================================================================
# 9. 标记已发送
# ===========================================================================


@pytest.mark.asyncio
async def test_send_quotation(service):
    """draft → sent，sent_at 自动填充。"""
    created = await service.create(
        QuotationCreateReq(items=[QuotationItemReq(product_name="商品 A")])
    )
    qid = created["id"]
    assert created["status"] == "draft"
    assert created["sent_at"] is None

    sent = await service.mark_sent(qid)
    assert sent is not None
    assert sent["status"] == "sent"
    assert sent["sent_at"] is not None
    # 状态机：再 send 应抛 ValueError
    with pytest.raises(ValueError, match="不允许迁移"):
        await service.mark_sent(qid)


# ===========================================================================
# 10. 标记已接受
# ===========================================================================


@pytest.mark.asyncio
async def test_accept_quotation(service):
    """draft → sent → accepted，accepted_at 自动填充。"""
    created = await service.create(
        QuotationCreateReq(items=[QuotationItemReq(product_name="商品 A")])
    )
    qid = created["id"]

    # draft 不能直接 accept
    with pytest.raises(ValueError, match="不允许迁移"):
        await service.mark_accepted(qid)

    await service.mark_sent(qid)
    accepted = await service.mark_accepted(qid)
    assert accepted is not None
    assert accepted["status"] == "accepted"
    assert accepted["accepted_at"] is not None
    # 已接受不能再操作
    with pytest.raises(ValueError, match="不允许迁移"):
        await service.mark_rejected(qid)


# ===========================================================================
# 11. 删除（硬删除 + CASCADE 清明细）
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_quotation_cascades_items(service, seeded_db):
    """硬删除主表，FK CASCADE 自动清空 items。"""
    created = await service.create(
        QuotationCreateReq(
            items=[
                QuotationItemReq(product_name="A"),
                QuotationItemReq(product_name="B"),
            ]
        )
    )
    qid = created["id"]

    # 删前：明细 2 条
    rows_before = (
        await seeded_db.execute(select(QuotationItem).where(QuotationItem.quotation_id == qid))
    ).scalars().all()
    assert len(rows_before) == 2

    # 删主表
    ok = await service.delete(qid)
    assert ok is True

    # 删后：明细 0
    rows_after = (
        await seeded_db.execute(select(QuotationItem).where(QuotationItem.quotation_id == qid))
    ).scalars().all()
    assert len(rows_after) == 0

    # 再次删除不存在 → False
    assert await service.delete(qid) is False


# ===========================================================================
# 12. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：各状态计数 + 总金额 + 已接受金额。"""
    # draft × 2
    await service.create(
        QuotationCreateReq(
            items=[QuotationItemReq(product_name="D1", unit_price=Decimal("100"))]
        )
    )
    await service.create(
        QuotationCreateReq(
            items=[QuotationItemReq(product_name="D2", unit_price=Decimal("200"))]
        )
    )
    # sent × 1
    q_sent = await service.create(
        QuotationCreateReq(
            items=[QuotationItemReq(product_name="S1", unit_price=Decimal("500"))]
        )
    )
    await service.mark_sent(q_sent["id"])
    # accepted × 1
    q_acc = await service.create(
        QuotationCreateReq(
            items=[QuotationItemReq(product_name="A1", unit_price=Decimal("1000"))]
        )
    )
    await service.mark_sent(q_acc["id"])
    await service.mark_accepted(q_acc["id"])
    # rejected × 1
    q_rej = await service.create(
        QuotationCreateReq(
            items=[QuotationItemReq(product_name="R1", unit_price=Decimal("50"))]
        )
    )
    await service.mark_rejected(q_rej["id"])

    stats = await service.stats()
    assert stats.total == 5
    assert stats.draft == 2
    assert stats.sent == 1
    assert stats.accepted == 1
    assert stats.rejected == 1
    assert stats.expired == 0
    # total_amount = 100+200+500+1000+50 = 1850
    assert stats.total_amount == Decimal("1850.00")
    # accepted_amount = 1000
    assert stats.accepted_amount == Decimal("1000.00")
