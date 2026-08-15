from __future__ import annotations

"""DDW 发票管理插件测试用例（8 个，覆盖核心 CRUD + 状态机 + 筛选 + 统计）。"""

from datetime import date
from decimal import Decimal

import pytest

from plugins.ddw_invoice.schemas import (
    InvoiceCreateReq,
    InvoiceUpdateReq,
    InvoiceUploadReq,
    InvoiceVoidReq,
)

# ===========================================================================
# 1. 新建开票申请
# ===========================================================================


@pytest.mark.asyncio
async def test_create_invoice(service_with_order):
    """正常创建开票申请：status=requested, invoice_no/url/issued_at 为空。"""
    req = InvoiceCreateReq(
        company_id=100,
        order_id=200,
        invoice_type="special",
        amount=Decimal("10000.00"),
        tax_amount=Decimal("1300.00"),
        total_amount=Decimal("11300.00"),
        invoice_title="武汉锐果互动信息技术有限公司",
        tax_id="91420100MA0000000X",
        notes="2026 智造项目首款开票",
        created_by=1,
    )
    result = await service_with_order.create(req)
    assert result["id"] is not None
    assert result["tenant_id"] == 1
    assert result["company_id"] == 100
    assert result["order_id"] == 200
    assert result["invoice_type"] == "special"
    assert result["amount"] == Decimal("10000.00")
    assert result["tax_amount"] == Decimal("1300.00")
    assert result["total_amount"] == Decimal("11300.00")
    assert result["invoice_title"] == "武汉锐果互动信息技术有限公司"
    assert result["tax_id"] == "91420100MA0000000X"
    assert result["status"] == "requested"
    assert result["invoice_no"] is None
    assert result["invoice_url"] is None
    assert result["issued_at"] is None
    assert result["created_by"] == 1


# ===========================================================================
# 2. 列表分页
# ===========================================================================


@pytest.mark.asyncio
async def test_list_invoices_paginated(service):
    """分页：插入 25 条，page=2&page_size=10 应返回 10 条。"""
    for i in range(25):
        await service.create(
            InvoiceCreateReq(
                invoice_type="normal" if i % 2 == 0 else "special",
                amount=Decimal("100.00"),
                tax_amount=Decimal("13.00"),
                total_amount=Decimal("113.00"),
                invoice_title=f"抬头 {i}",
                tax_id=f"TAX{i:09d}",
            )
        )

    p1 = await service.list(page=1, page_size=10)
    p2 = await service.list(page=2, page_size=10)
    p3 = await service.list(page=3, page_size=10)

    assert p1.total == 25
    assert p1.page == 1
    assert len(p1.items) == 10
    assert len(p2.items) == 10
    assert p3.page == 3
    assert len(p3.items) == 5  # 最后一页只有 5 条


# ===========================================================================
# 3. 列表筛选（按 invoice_type）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_invoices_filter_by_type(service):
    """按 invoice_type 精确筛选：special / normal。"""
    for i in range(3):
        await service.create(
            InvoiceCreateReq(
                invoice_type="special",
                amount=Decimal("1000.00"),
                tax_amount=Decimal("130.00"),
                total_amount=Decimal("1130.00"),
                invoice_title=f"专票 {i}",
                tax_id=f"TAX{i:09d}",
            )
        )
    for i in range(5):
        await service.create(
            InvoiceCreateReq(
                invoice_type="normal",
                amount=Decimal("200.00"),
                tax_amount=Decimal("26.00"),
                total_amount=Decimal("226.00"),
                invoice_title=f"普票 {i}",
                tax_id=f"TAXN{i:08d}",
            )
        )

    sp = await service.list(page=1, page_size=50, invoice_type="special")
    nm = await service.list(page=1, page_size=50, invoice_type="normal")
    all_ = await service.list(page=1, page_size=50)

    assert sp.total == 3
    assert all(i.invoice_type == "special" for i in sp.items)
    assert nm.total == 5
    assert all(i.invoice_type == "normal" for i in nm.items)
    assert all_.total == 8


# ===========================================================================
# 4. 详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_invoice_detail(service_with_order):
    """获取发票详情。"""
    created = await service_with_order.create(
        InvoiceCreateReq(
            company_id=100,
            order_id=200,
            invoice_type="normal",
            amount=Decimal("5000.00"),
            tax_amount=Decimal("650.00"),
            total_amount=Decimal("5650.00"),
            invoice_title="测试客户公司",
            tax_id="91420100MA9999999X",
        )
    )
    iid = created["id"]
    detail = await service_with_order.get(iid)
    assert detail is not None
    assert detail["id"] == iid
    assert detail["company_id"] == 100
    assert detail["order_id"] == 200
    assert detail["amount"] == Decimal("5000.00")
    assert detail["total_amount"] == Decimal("5650.00")
    assert detail["status"] == "requested"


# ===========================================================================
# 5. 更新（仅 requested 状态可改）
# ===========================================================================


@pytest.mark.asyncio
async def test_update_invoice(service):
    """更新 requested 状态的发票（修改金额三件套保持一致）。"""
    created = await service.create(
        InvoiceCreateReq(
            invoice_type="normal",
            amount=Decimal("100.00"),
            tax_amount=Decimal("13.00"),
            total_amount=Decimal("113.00"),
            invoice_title="原抬头",
            tax_id="TAX000000001",
        )
    )
    iid = created["id"]

    upd = InvoiceUpdateReq(
        invoice_type="special",
        amount=Decimal("200.00"),
        tax_amount=Decimal("26.00"),
        total_amount=Decimal("226.00"),
        invoice_title="新抬头",
        notes="抬头更名",
    )
    result = await service.update(iid, upd)
    assert result is not None
    assert result["invoice_type"] == "special"
    assert result["amount"] == Decimal("200.00")
    assert result["tax_amount"] == Decimal("26.00")
    assert result["total_amount"] == Decimal("226.00")
    assert result["invoice_title"] == "新抬头"
    assert result["notes"] == "抬头更名"
    # 状态不变（仅内容修改）
    assert result["status"] == "requested"


# ===========================================================================
# 6. 上传发票（requested → issued，issued_at=今天）
# ===========================================================================


@pytest.mark.asyncio
async def test_upload_invoice(service):
    """上传发票文件：status: requested → issued, issued_at=今天。"""
    created = await service.create(
        InvoiceCreateReq(
            invoice_type="special",
            amount=Decimal("10000.00"),
            tax_amount=Decimal("1300.00"),
            total_amount=Decimal("11300.00"),
            invoice_title="武汉锐果互动",
            tax_id="91420100MA0000000X",
        )
    )
    iid = created["id"]
    assert created["status"] == "requested"
    assert created["issued_at"] is None

    today = date.today()
    upload = InvoiceUploadReq(
        invoice_url="https://invoice.ddw.dev/2026/INV-001.pdf",
        invoice_no="INV-2026-0001",
    )
    result = await service.upload(iid, upload)
    assert result is not None
    assert result["status"] == "issued"
    assert result["invoice_no"] == "INV-2026-0001"
    assert result["invoice_url"] == "https://invoice.ddw.dev/2026/INV-001.pdf"
    assert result["issued_at"] == today


# ===========================================================================
# 7. 作废（issued → voided）
# ===========================================================================


@pytest.mark.asyncio
async def test_void_invoice(service):
    """作废：issued → voided，void_reason 追加到 notes。"""
    created = await service.create(
        InvoiceCreateReq(
            invoice_type="special",
            amount=Decimal("10000.00"),
            tax_amount=Decimal("1300.00"),
            total_amount=Decimal("11300.00"),
            invoice_title="武汉锐果互动",
            tax_id="91420100MA0000000X",
        )
    )
    iid = created["id"]

    # 先上传变 issued
    await service.upload(
        iid,
        InvoiceUploadReq(
            invoice_url="https://invoice.ddw.dev/INV-001.pdf",
            invoice_no="INV-2026-0001",
        ),
    )
    issued = await service.get(iid)
    assert issued["status"] == "issued"

    # 再作废
    result = await service.void(iid, InvoiceVoidReq(void_reason="客户要求红冲重开"))
    assert result is not None
    assert result["status"] == "voided"
    assert "作废原因: 客户要求红冲重开" in result["notes"]


# ===========================================================================
# 8. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：total/requested/issued/voided + total_amount + tax_amount + by_type。"""
    # 3 requested（special）
    for i in range(3):
        await service.create(
            InvoiceCreateReq(
                invoice_type="special",
                amount=Decimal("1000.00"),
                tax_amount=Decimal("130.00"),
                total_amount=Decimal("1130.00"),
                invoice_title=f"专票 {i}",
                tax_id=f"TAX{i:09d}",
            )
        )
    # 2 issued（normal）
    for i in range(2):
        c = await service.create(
            InvoiceCreateReq(
                invoice_type="normal",
                amount=Decimal("200.00"),
                tax_amount=Decimal("26.00"),
                total_amount=Decimal("226.00"),
                invoice_title=f"普票 {i}",
                tax_id=f"TAXN{i:08d}",
            )
        )
        await service.upload(
            c["id"],
            InvoiceUploadReq(
                invoice_url=f"https://invoice.ddw.dev/INV-{i}.pdf",
                invoice_no=f"INV-N-{i:04d}",
            ),
        )
    # 1 voided（special，先 upload 再 void）
    c = await service.create(
        InvoiceCreateReq(
            invoice_type="special",
            amount=Decimal("500.00"),
            tax_amount=Decimal("65.00"),
            total_amount=Decimal("565.00"),
            invoice_title="专票 X",
            tax_id="TAX000000999",
        )
    )
    await service.upload(
        c["id"],
        InvoiceUploadReq(
            invoice_url="https://invoice.ddw.dev/INV-X.pdf",
            invoice_no="INV-X-0001",
        ),
    )
    await service.void(c["id"], InvoiceVoidReq(void_reason="抬头错误"))

    stats = await service.stats()
    assert stats.total == 6
    assert stats.requested == 3
    assert stats.issued == 2
    assert stats.voided == 1

    # total_amount: 3*1130 + 2*226 + 565 = 3390 + 452 + 565 = 4407
    assert stats.total_amount == Decimal("4407.00")
    # tax_amount: 3*130 + 2*26 + 65 = 390 + 52 + 65 = 507
    assert stats.tax_amount == Decimal("507.00")

    # by_invoice_type: special=4 (3 requested + 1 voided), normal=2
    assert stats.by_invoice_type.get("special") == 4
    assert stats.by_invoice_type.get("normal") == 2


# ===========================================================================
# MVP 新功能测试（Task 7）
# ===========================================================================


@pytest.mark.asyncio
async def test_request_by_customer_auto_fills_title(service, seeded_company_with_invoice_info):
    """客户提交开票申请：自动从 crm_companies 读取 invoice_title + tax_id。"""
    from plugins.ddw_invoice.schemas import InvoiceRequestByCustomerReq

    req = InvoiceRequestByCustomerReq(
        company_id=100,
        invoice_type="special",
        amount=Decimal("10000.00"),
        tax_amount=Decimal("1300.00"),
        total_amount=Decimal("11300.00"),
        notes="首期款开票",
        created_by=1,
    )
    result = await service.request_by_customer(req)
    assert result["id"] is not None
    assert result["company_id"] == 100
    assert result["invoice_title"] == "武汉测试客户公司"  # 自动填充
    assert result["tax_id"] == "91420100MA0000000X"      # 自动填充
    assert result["status"] == "requested"
    assert result["total_amount"] == Decimal("11300.00")


@pytest.mark.asyncio
async def test_request_by_customer_company_not_found(service, seeded_company):
    """客户提交开票申请：企业不存在 → ValueError。"""
    from plugins.ddw_invoice.schemas import InvoiceRequestByCustomerReq

    req = InvoiceRequestByCustomerReq(
        company_id=9999,  # 不存在
        invoice_type="normal",
        amount=Decimal("100.00"),
        tax_amount=Decimal("13.00"),
        total_amount=Decimal("113.00"),
    )
    with pytest.raises(ValueError, match="不存在"):
        await service.request_by_customer(req)


@pytest.mark.asyncio
async def test_list_by_company_paginated(service, seeded_company_with_invoice_info):
    """客户按企业 ID 查发票列表：分页。"""
    from plugins.ddw_invoice.schemas import InvoiceRequestByCustomerReq

    # 插入 6 张发票到 company_id=100
    for i in range(6):
        await service.request_by_customer(
            InvoiceRequestByCustomerReq(
                company_id=100,
                invoice_type="normal",
                amount=Decimal("100.00"),
                tax_amount=Decimal("13.00"),
                total_amount=Decimal("113.00"),
            )
        )
    # 插入 2 张到 company_id=200（必须先插另一家企业 → 用普通 create 绕过）
    # 直接 insert 不同 company_id 的发票
    from plugins.ddw_invoice.models import Invoice

    for i in range(2):
        inv = Invoice(
            tenant_id=1,
            company_id=200,
            invoice_type="normal",
            amount=Decimal("200.00"),
            tax_amount=Decimal("26.00"),
            total_amount=Decimal("226.00"),
            invoice_title="其他公司",
            tax_id="TAX999999999",
            status="requested",
        )
        service.db.add(inv)
    await service.db.commit()

    p1 = await service.list_by_company(company_id=100, page=1, page_size=4)
    p2 = await service.list_by_company(company_id=100, page=2, page_size=4)
    assert p1.total == 6
    assert len(p1.items) == 4
    assert p2.total == 6
    assert len(p2.items) == 2
    # 必须全部是 company_id=100
    for item in p1.items + p2.items:
        assert item.company_id == 100


@pytest.mark.asyncio
async def test_list_by_company_filter_status(service, seeded_company_with_invoice_info):
    """客户按状态筛选发票。"""
    from plugins.ddw_invoice.schemas import (
        InvoiceRequestByCustomerReq,
        InvoiceUploadReq,
    )

    # 3 张 requested
    for i in range(3):
        await service.request_by_customer(
            InvoiceRequestByCustomerReq(
                company_id=100,
                invoice_type="normal",
                amount=Decimal("100.00"),
                tax_amount=Decimal("13.00"),
                total_amount=Decimal("113.00"),
            )
        )
    # 2 张 issued
    issued_ids = []
    for i in range(2):
        created = await service.request_by_customer(
            InvoiceRequestByCustomerReq(
                company_id=100,
                invoice_type="special",
                amount=Decimal("200.00"),
                tax_amount=Decimal("26.00"),
                total_amount=Decimal("226.00"),
            )
        )
        issued_ids.append(created["id"])
    # 上传前 2 张到 issued
    for inv_id in issued_ids:
        await service.upload(
            inv_id,
            InvoiceUploadReq(
                invoice_url=f"https://invoice.ddw.dev/{inv_id}.pdf",
                invoice_no=f"INV-{inv_id:04d}",
            ),
        )

    requested = await service.list_by_company(company_id=100, status="requested")
    issued = await service.list_by_company(company_id=100, status="issued")
    all_ = await service.list_by_company(company_id=100)

    assert requested.total == 3
    assert issued.total == 2
    assert all_.total == 5
    assert all(i.status == "requested" for i in requested.items)
    assert all(i.status == "issued" for i in issued.items)


@pytest.mark.asyncio
async def test_record_download_increments_count(service, seeded_company_with_invoice_info):
    """客户下载发票：download_count 单调递增 + last_downloaded_at 被记录。"""
    from plugins.ddw_invoice.schemas import (
        InvoiceRequestByCustomerReq,
        InvoiceUploadReq,
    )

    created = await service.request_by_customer(
        InvoiceRequestByCustomerReq(
            company_id=100,
            invoice_type="normal",
            amount=Decimal("100.00"),
            tax_amount=Decimal("13.00"),
            total_amount=Decimal("113.00"),
        )
    )
    inv_id = created["id"]

    # 上传到 issued
    await service.upload(
        inv_id,
        InvoiceUploadReq(
            invoice_url="https://invoice.ddw.dev/INV-001.pdf",
            invoice_no="INV-2026-0001",
            file_type="pdf",
            file_size_bytes=102400,
        ),
    )

    # 第 1 次下载
    r1 = await service.record_download(inv_id, user_id=42)
    assert r1.invoice_id == inv_id
    assert r1.invoice_no == "INV-2026-0001"
    assert r1.file_type == "pdf"
    assert r1.file_size_bytes == 102400
    assert r1.download_count == 1
    assert r1.last_downloaded_at is not None

    # 第 2 次下载
    r2 = await service.record_download(inv_id, user_id=42)
    assert r2.download_count == 2

    # 数据库里也是 2
    detail = await service.get(inv_id)
    assert detail["download_count"] == 2
    assert detail["last_downloaded_by"] == 42


@pytest.mark.asyncio
async def test_download_invoice_not_issued(service, seeded_company_with_invoice_info):
    """下载未开具的发票 → ValueError。"""
    from plugins.ddw_invoice.schemas import InvoiceRequestByCustomerReq

    created = await service.request_by_customer(
        InvoiceRequestByCustomerReq(
            company_id=100,
            invoice_type="normal",
            amount=Decimal("100.00"),
            tax_amount=Decimal("13.00"),
            total_amount=Decimal("113.00"),
        )
    )
    inv_id = created["id"]
    # 未 upload，状态仍是 requested
    with pytest.raises(ValueError, match="不可下载"):
        await service.record_download(inv_id)


@pytest.mark.asyncio
async def test_admin_upload_invoice_with_extended_fields(service):
    """管理员上传发票文件：含发票代码 / 校验码 / 文件大小。"""
    created = await service.create(
        InvoiceCreateReq(
            invoice_type="special",
            amount=Decimal("50000.00"),
            tax_amount=Decimal("6500.00"),
            total_amount=Decimal("56500.00"),
            invoice_title="武汉锐果互动",
            tax_id="91420100MA0000000X",
        )
    )
    iid = created["id"]

    result = await service.upload(
        iid,
        InvoiceUploadReq(
            invoice_url="https://invoice.ddw.dev/E-2026-0001.pdf",
            invoice_no="011002000000",
            invoice_code="011002000000",
            invoice_check_code="123456",
            file_type="pdf",
            file_size_bytes=204800,
        ),
    )
    assert result["status"] == "issued"
    assert result["invoice_code"] == "011002000000"
    assert result["invoice_check_code"] == "123456"
    assert result["file_type"] == "pdf"
    assert result["file_size_bytes"] == 204800


@pytest.mark.asyncio
async def test_batch_upload_mixed_results(service):
    """管理员批量上传：部分成功部分失败（已作废的发票不能再上传）。"""
    # 1 张可上传
    c1 = await service.create(
        InvoiceCreateReq(
            invoice_type="normal",
            amount=Decimal("100.00"),
            tax_amount=Decimal("13.00"),
            total_amount=Decimal("113.00"),
            invoice_title="A 公司",
            tax_id="TAX000000001",
        )
    )
    # 1 张先 upload 后 void（再 upload 会失败）
    c2 = await service.create(
        InvoiceCreateReq(
            invoice_type="special",
            amount=Decimal("200.00"),
            tax_amount=Decimal("26.00"),
            total_amount=Decimal("226.00"),
            invoice_title="B 公司",
            tax_id="TAX000000002",
        )
    )
    await service.upload(
        c2["id"],
        InvoiceUploadReq(
            invoice_url="https://invoice.ddw.dev/B.pdf",
            invoice_no="INV-B-0001",
        ),
    )
    from plugins.ddw_invoice.schemas import InvoiceVoidReq

    await service.void(c2["id"], InvoiceVoidReq(void_reason="测试"))
    # 1 个不存在的 invoice_id
    fake_id = 99999

    from plugins.ddw_invoice.schemas import (
        InvoiceBatchUploadItem,
        InvoiceBatchUploadReq,
    )

    req = InvoiceBatchUploadReq(
        items=[
            InvoiceBatchUploadItem(
                invoice_id=c1["id"],
                invoice_url="https://invoice.ddw.dev/A.pdf",
                invoice_no="INV-A-0001",
            ),
            InvoiceBatchUploadItem(
                invoice_id=c2["id"],  # 已 voided，会失败
                invoice_url="https://invoice.ddw.dev/B2.pdf",
                invoice_no="INV-B-0002",
            ),
            InvoiceBatchUploadItem(
                invoice_id=fake_id,  # 不存在，会失败
                invoice_url="https://invoice.ddw.dev/F.pdf",
                invoice_no="INV-F-0001",
            ),
        ],
        notify=False,
    )

    result = await service.batch_upload(req)
    assert result["total"] == 3
    assert result["succeeded"] == 1
    assert result["failed"] == 2
    # 第 1 项成功
    assert result["results"][0]["ok"] is True
    assert result["results"][0]["invoice_id"] == c1["id"]
    # 第 2 项因状态不允许失败
    assert result["results"][1]["ok"] is False
    assert "不允许" in result["results"][1]["error"]
    # 第 3 项因不存在失败
    assert result["results"][2]["ok"] is False
    assert "not found" in result["results"][2]["error"]


@pytest.mark.asyncio
async def test_stats_includes_download_metrics(service, seeded_company_with_invoice_info):
    """统计概览：download_total + total_downloaded_files 含新下载字段。"""
    from plugins.ddw_invoice.schemas import (
        InvoiceRequestByCustomerReq,
        InvoiceUploadReq,
    )

    # 2 张 issued 各下载若干次
    inv_ids = []
    for i in range(2):
        c = await service.request_by_customer(
            InvoiceRequestByCustomerReq(
                company_id=100,
                invoice_type="normal",
                amount=Decimal("100.00"),
                tax_amount=Decimal("13.00"),
                total_amount=Decimal("113.00"),
            )
        )
        await service.upload(
            c["id"],
            InvoiceUploadReq(
                invoice_url=f"https://invoice.ddw.dev/{c['id']}.pdf",
                invoice_no=f"INV-{c['id']:04d}",
            ),
        )
        inv_ids.append(c["id"])
    # 1 张 requested（不计入下载统计）
    await service.request_by_customer(
        InvoiceRequestByCustomerReq(
            company_id=100,
            invoice_type="special",
            amount=Decimal("500.00"),
            tax_amount=Decimal("65.00"),
            total_amount=Decimal("565.00"),
        )
    )

    # 各下载 3 次 + 1 次
    for _ in range(3):
        await service.record_download(inv_ids[0])
    await service.record_download(inv_ids[1])

    stats = await service.stats()
    assert stats.total == 3
    assert stats.requested == 1
    assert stats.issued == 2
    # download_total = 3 + 1 = 4
    assert stats.download_total == 4
    # total_downloaded_files = 2（两张发票各有至少 1 次下载）
    assert stats.total_downloaded_files == 2


@pytest.mark.asyncio
async def test_download_returns_invoice_download_resp(service, seeded_company_with_invoice_info):
    """下载返回 InvoiceDownloadResp（含 invoice_url / download_url / file_type）。"""
    from plugins.ddw_invoice.schemas import (
        InvoiceRequestByCustomerReq,
        InvoiceUploadReq,
    )

    created = await service.request_by_customer(
        InvoiceRequestByCustomerReq(
            company_id=100,
            invoice_type="normal",
            amount=Decimal("100.00"),
            tax_amount=Decimal("13.00"),
            total_amount=Decimal("113.00"),
        )
    )
    await service.upload(
        created["id"],
        InvoiceUploadReq(
            invoice_url="https://invoice.ddw.dev/X.pdf",
            invoice_no="INV-X-0001",
            file_type="pdf",
        ),
    )

    resp = await service.record_download(created["id"], user_id=99)
    # 字段验证
    assert resp.invoice_id == created["id"]
    assert resp.invoice_no == "INV-X-0001"
    assert resp.invoice_url == "https://invoice.ddw.dev/X.pdf"
    assert resp.file_type == "pdf"
    assert resp.download_url == "https://invoice.ddw.dev/X.pdf"  # MVP 同 invoice_url
    assert resp.download_count == 1


@pytest.mark.asyncio
async def test_upload_publishes_event(monkeypatch, service):
    """upload 完成后调用 EventBus.publish_threadsafe（验证集成，不依赖订阅者）。"""
    # 让 publish_threadsafe 不实际执行 task，只记录调用
    calls: list = []

    class FakeBus:
        def publish_threadsafe(self, event, payload=None):
            calls.append((event, payload))

    monkeypatch.setattr(
        "core.events.bus.get_bus", lambda: FakeBus(), raising=False
    )

    created = await service.create(
        InvoiceCreateReq(
            invoice_type="normal",
            amount=Decimal("100.00"),
            tax_amount=Decimal("13.00"),
            total_amount=Decimal("113.00"),
            invoice_title="event test",
            tax_id="TAX000000777",
        )
    )
    # create 也发请求事件
    assert any(c[0] == "invoice.requested" for c in calls)

    await service.upload(
        created["id"],
        InvoiceUploadReq(
            invoice_url="https://invoice.ddw.dev/E.pdf",
            invoice_no="INV-E-0001",
        ),
    )
    # 应同时有 issued 事件
    assert any(c[0] == "invoice.issued" for c in calls)


@pytest.mark.asyncio
async def test_record_download_publishes_event(monkeypatch, service, seeded_company_with_invoice_info):
    """下载事件：record_download 调用 EventBus.publish_threadsafe。"""
    from plugins.ddw_invoice.schemas import (
        InvoiceRequestByCustomerReq,
        InvoiceUploadReq,
    )

    created = await service.request_by_customer(
        InvoiceRequestByCustomerReq(
            company_id=100,
            invoice_type="normal",
            amount=Decimal("100.00"),
            tax_amount=Decimal("13.00"),
            total_amount=Decimal("113.00"),
        )
    )
    await service.upload(
        created["id"],
        InvoiceUploadReq(
            invoice_url="https://invoice.ddw.dev/D.pdf",
            invoice_no="INV-D-0001",
        ),
    )

    calls: list = []

    class FakeBus:
        def publish_threadsafe(self, event, payload=None):
            calls.append((event, payload))

    monkeypatch.setattr(
        "core.events.bus.get_bus", lambda: FakeBus(), raising=False
    )

    await service.record_download(created["id"], user_id=1)
    assert any(c[0] == "invoice.downloaded" for c in calls)
