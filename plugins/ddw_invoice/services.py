from __future__ import annotations

"""DDW 发票管理插件业务逻辑层。

关键设计：
- 状态机：requested（已申请）→ issued（已开具）→ voided（已作废）
- create: status=requested, invoice_no/url/issued_at 为空
- update: 仅 requested 状态可改（防破坏已开/已作废发票）
- upload: requested → issued；invoice_url/invoice_no 必填，issued_at 默认今天
- void: issued → voided；void_reason 入参（仅追加到 notes，不入业务字段）
- stats: 各状态计数 + total_amount/tax_amount 汇总 + by_invoice_type 分组
- request_by_customer: 客户提交，自动从企业主体填充抬头/税号
- list_by_company: 客户按企业 ID 查自己的发票列表
- record_download: 客户下载发票，递增计数 + 记录最后下载时间
- batch_upload: 管理员批量上传发票文件到多个开票申请
- 事件总线：申请/开票/作废时通过 ``core.events.bus.get_bus().publish`` 发布
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Invoice
from .schemas import (
    InvoiceBatchUploadReq,
    InvoiceCreateReq,
    InvoiceDownloadResp,
    InvoiceListResp,
    InvoiceRequestByCustomerReq,
    InvoiceResp,
    InvoiceStatsResp,
    InvoiceUpdateReq,
    InvoiceUploadReq,
    InvoiceVoidReq,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# 状态机合法迁移
_EDITABLE_STATUSES: frozenset[str] = frozenset({"requested"})
_UPLOADABLE_STATUSES: frozenset[str] = frozenset({"requested"})
_VOIDABLE_STATUSES: frozenset[str] = frozenset({"issued"})
_DOWNLOADABLE_STATUSES: frozenset[str] = frozenset({"issued"})

# 事件名常量
_EVENT_REQUESTED = "invoice.requested"
_EVENT_ISSUED = "invoice.issued"
_EVENT_VOIDED = "invoice.voided"
_EVENT_BATCH_ISSUED = "invoice.batch_issued"
_EVENT_DOWNLOADED = "invoice.downloaded"


# ---------------------------------------------------------------------------
# 内部辅助：金额校验
# ---------------------------------------------------------------------------


def _validate_total(data_amount: Decimal, data_tax: Decimal, data_total: Decimal) -> None:
    """校验金额三件套：total == amount + tax。"""
    expected_total = Decimal(data_amount) + Decimal(data_tax)
    if Decimal(data_total) != expected_total:
        raise ValueError(
            f"total_amount({data_total}) != amount({data_amount}) + tax_amount({data_tax}) "
            f"= {expected_total}"
        )


# ---------------------------------------------------------------------------
# 内部辅助：EventBus 发布（失败容错，不影响业务）
# ---------------------------------------------------------------------------


def _publish_event(event: str, payload: Dict[str, Any]) -> None:
    """通过 EventBus 发布事件；事件总线不可用时静默退化。"""
    try:
        from core.events.bus import get_bus

        bus = get_bus()
        # publish_threadsafe 同时支持异步/同步上下文
        if hasattr(bus, "publish_threadsafe"):
            bus.publish_threadsafe(event, payload)
        else:  # pragma: no cover - 兼容性兜底
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(bus.publish(event, payload))
            except RuntimeError:
                pass
    except Exception:  # noqa: BLE001
        # 事件总线导入/发布失败不影响主业务
        logger.exception("publish_event(%s) failed", event)


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _invoice_to_dict(inv: Invoice) -> Dict[str, Any]:
    """Invoice ORM → dict。"""
    return {
        "id": inv.id,
        "tenant_id": inv.tenant_id,
        "company_id": inv.company_id,
        "order_id": inv.order_id,
        "invoice_no": inv.invoice_no,
        "invoice_type": inv.invoice_type,
        "amount": inv.amount,
        "tax_amount": inv.tax_amount,
        "total_amount": inv.total_amount,
        "invoice_title": inv.invoice_title,
        "tax_id": inv.tax_id,
        "invoice_url": inv.invoice_url,
        "issued_at": inv.issued_at,
        "status": inv.status,
        "notes": inv.notes,
        # Task 1 新增字段
        "notified_at": inv.notified_at,
        "notification_method": inv.notification_method,
        "download_count": inv.download_count or 0,
        "last_downloaded_at": inv.last_downloaded_at,
        "last_downloaded_by": inv.last_downloaded_by,
        "invoice_code": inv.invoice_code,
        "invoice_check_code": inv.invoice_check_code,
        "file_type": inv.file_type,
        "file_size_bytes": inv.file_size_bytes,
        "created_at": inv.created_at,
        "updated_at": inv.updated_at,
        "created_by": inv.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class InvoiceService:
    """发票业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #

    async def create(self, data: InvoiceCreateReq) -> Dict[str, Any]:
        """新建开票申请。

        - 强制校验 total_amount = amount + tax_amount
        - 初始 status=requested；invoice_no / invoice_url / issued_at 为空
        """
        _validate_total(data.amount, data.tax_amount, data.total_amount)

        invoice = Invoice(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            order_id=data.order_id,
            invoice_no=None,
            invoice_type=data.invoice_type,
            amount=data.amount,
            tax_amount=data.tax_amount,
            total_amount=data.total_amount,
            invoice_title=data.invoice_title,
            tax_id=data.tax_id,
            invoice_url=None,
            issued_at=None,
            status="requested",
            notes=data.notes,
            created_by=data.created_by,
        )
        self.db.add(invoice)
        await self.db.commit()
        await self.db.refresh(invoice)
        logger.info(
            "invoice created: id=%s type=%s amount=%s tax=%s total=%s",
            invoice.id,
            invoice.invoice_type,
            invoice.amount,
            invoice.tax_amount,
            invoice.total_amount,
        )

        # 发布 EventBus 事件（Task 1）
        _publish_event(
            _EVENT_REQUESTED,
            {
                "invoice_id": invoice.id,
                "tenant_id": invoice.tenant_id,
                "company_id": invoice.company_id,
                "order_id": invoice.order_id,
                "invoice_type": invoice.invoice_type,
                "total_amount": str(invoice.total_amount),
                "invoice_title": invoice.invoice_title,
            },
        )

        return _invoice_to_dict(invoice)

    # ------------------------------------------------------------------ #
    # request_by_customer（Task 4.1：客户提交，自动从企业主体填充抬头/税号）
    # ------------------------------------------------------------------ #

    async def request_by_customer(
        self, data: InvoiceRequestByCustomerReq
    ) -> Dict[str, Any]:
        """客户提交开票申请，自动从 crm_companies 读取发票抬头和税号。

        优先级：
        - invoice_title: company.invoice_title ?? company.name
        - tax_id: company.tax_id ?? company.credit_code
        """
        # 延迟导入，避免插件单独测试时强制依赖 ddw_company_profile
        try:
            from plugins.ddw_company_profile.models import Company
        except ImportError as e:
            raise ValueError(
                "ddw_company_profile 插件未注册，无法自动填充抬头"
            ) from e

        company = await self.db.get(Company, data.company_id)
        if not company:
            raise ValueError(f"企业 {data.company_id} 不存在")

        invoice_title = getattr(company, "invoice_title", None) or company.name
        tax_id = getattr(company, "tax_id", None) or getattr(
            company, "credit_code", None
        )
        if not tax_id:
            raise ValueError(
                f"企业 {data.company_id} 缺少税号（tax_id / credit_code 均未配置），"
                f"请先在企业主体中完善开票信息"
            )

        # 沿用 create() 的金额校验与 EventBus 发布
        create_req = InvoiceCreateReq(
            tenant_id=getattr(company, "tenant_id", 1) or 1,
            company_id=data.company_id,
            order_id=data.order_id,
            invoice_type=data.invoice_type,
            amount=data.amount,
            tax_amount=data.tax_amount,
            total_amount=data.total_amount,
            invoice_title=str(invoice_title),
            tax_id=str(tax_id),
            notes=data.notes,
            created_by=data.created_by,
        )
        return await self.create(create_req)

    # ------------------------------------------------------------------ #
    # get
    # ------------------------------------------------------------------ #

    async def get(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        """获取发票详情。"""
        invoice = await self.db.get(Invoice, invoice_id)
        if not invoice:
            return None
        return _invoice_to_dict(invoice)

    # ------------------------------------------------------------------ #
    # list（管理员/全量）+ list_by_company（客户侧）
    # ------------------------------------------------------------------ #

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        company_id: Optional[int] = None,
        order_id: Optional[int] = None,
        invoice_type: Optional[str] = None,
        status: Optional[str] = None,
        issued_at_from: Optional[date] = None,
        issued_at_to: Optional[date] = None,
    ) -> InvoiceListResp:
        """发票列表（分页 + 多维筛选）。

        筛选字段：
        - company_id：精确匹配
        - order_id：精确匹配
        - invoice_type：精确匹配（special/normal）
        - status：精确匹配（requested/issued/voided）
        - issued_at_from / issued_at_to：开票日期闭区间
        """
        conditions = []
        if company_id is not None:
            conditions.append(Invoice.company_id == company_id)
        if order_id is not None:
            conditions.append(Invoice.order_id == order_id)
        if invoice_type:
            conditions.append(Invoice.invoice_type == invoice_type)
        if status:
            conditions.append(Invoice.status == status)
        if issued_at_from is not None:
            conditions.append(Invoice.issued_at >= issued_at_from)
        if issued_at_to is not None:
            conditions.append(Invoice.issued_at <= issued_at_to)

        # total
        count_stmt = select(func.count(Invoice.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(Invoice)
            .order_by(Invoice.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return InvoiceListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[InvoiceResp(**_invoice_to_dict(i)) for i in rows],
        )

    async def list_by_company(
        self,
        company_id: int,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> InvoiceListResp:
        """客户按企业 ID 查询自己的发票列表（按 created_at 降序）。

        - 强制 company_id 精确匹配（防止越权查看其他企业）
        - 可选按状态筛选
        - 按 Invoice.id 降序（与 created_at 降序一致）
        """
        conditions = [Invoice.company_id == company_id]
        if status:
            conditions.append(Invoice.status == status)

        count_stmt = select(func.count(Invoice.id))
        count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one() or 0

        offset = (page - 1) * page_size
        list_stmt = (
            select(Invoice)
            .where(and_(*conditions))
            .order_by(Invoice.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return InvoiceListResp(
            total=int(total),
            page=page,
            page_size=page_size,
            items=[InvoiceResp(**_invoice_to_dict(i)) for i in rows],
        )

    # ------------------------------------------------------------------ #
    # update（仅 requested 状态可改）
    # ------------------------------------------------------------------ #

    async def update(
        self, invoice_id: int, data: InvoiceUpdateReq
    ) -> Optional[Dict[str, Any]]:
        """更新发票。

        约束：
        - 仅 ``status == "requested"`` 状态允许修改
        - 字段级更新（model_dump(exclude_unset=True)）
        - 若同时给出 amount/tax_amount/total_amount，必须满足 total == amount + tax
        """
        invoice = await self.db.get(Invoice, invoice_id)
        if not invoice:
            return None
        if invoice.status not in _EDITABLE_STATUSES:
            raise ValueError(
                f"发票当前状态 '{invoice.status}' 不允许修改（仅 requested 状态可改）"
            )

        updates = data.model_dump(exclude_unset=True)

        # 校验三件套一致性（如果用户一次性更新了 amount/tax_amount/total_amount）
        if (
            "amount" in updates
            or "tax_amount" in updates
            or "total_amount" in updates
        ):
            new_amount = Decimal(updates.get("amount", invoice.amount))
            new_tax = Decimal(updates.get("tax_amount", invoice.tax_amount))
            new_total = Decimal(updates.get("total_amount", invoice.total_amount))
            _validate_total(new_amount, new_tax, new_total)

        for k, v in updates.items():
            setattr(invoice, k, v)

        await self.db.commit()
        await self.db.refresh(invoice)
        logger.info("invoice updated: id=%s fields=%s", invoice.id, sorted(updates.keys()))
        return _invoice_to_dict(invoice)

    # ------------------------------------------------------------------ #
    # upload（requested → issued）
    # ------------------------------------------------------------------ #

    async def upload(
        self, invoice_id: int, data: InvoiceUploadReq
    ) -> Optional[Dict[str, Any]]:
        """上传发票文件（requested → issued）。

        - 必须当前为 requested 状态（已开/已作废不可重传）
        - invoice_url / invoice_no 必填
        - issued_at 不传则默认今天
        - amount/tax_amount/total_amount 可选覆盖（覆盖时需满足 total=amount+tax）
        """
        invoice = await self.db.get(Invoice, invoice_id)
        if not invoice:
            return None
        if invoice.status not in _UPLOADABLE_STATUSES:
            raise ValueError(
                f"发票当前状态 '{invoice.status}' 不允许上传（仅 requested 状态可上传）"
            )

        invoice.invoice_url = data.invoice_url
        invoice.invoice_no = data.invoice_no
        invoice.issued_at = data.issued_at or date.today()

        # 金额可覆盖
        if data.amount is not None:
            invoice.amount = data.amount
        if data.tax_amount is not None:
            invoice.tax_amount = data.tax_amount
        if data.total_amount is not None:
            invoice.total_amount = data.total_amount

        # 文件扩展信息（Task 1）
        if data.invoice_code is not None:
            invoice.invoice_code = data.invoice_code
        if data.invoice_check_code is not None:
            invoice.invoice_check_code = data.invoice_check_code
        if data.file_type is not None:
            invoice.file_type = data.file_type
        if data.file_size_bytes is not None:
            invoice.file_size_bytes = data.file_size_bytes

        # 校验三件套一致性（覆盖后）
        _validate_total(invoice.amount, invoice.tax_amount, invoice.total_amount)

        invoice.status = "issued"

        await self.db.commit()
        await self.db.refresh(invoice)
        logger.info(
            "invoice uploaded: id=%s no=%s status=issued issued_at=%s",
            invoice.id,
            invoice.invoice_no,
            invoice.issued_at,
        )

        # 发布 EventBus 事件
        _publish_event(
            _EVENT_ISSUED,
            {
                "invoice_id": invoice.id,
                "tenant_id": invoice.tenant_id,
                "company_id": invoice.company_id,
                "invoice_no": invoice.invoice_no,
                "invoice_url": invoice.invoice_url,
                "issued_at": (
                    invoice.issued_at.isoformat()
                    if invoice.issued_at is not None
                    else None
                ),
                "total_amount": str(invoice.total_amount),
            },
        )

        return _invoice_to_dict(invoice)

    # ------------------------------------------------------------------ #
    # batch_upload（Task 4.4：管理员批量上传）
    # ------------------------------------------------------------------ #

    async def batch_upload(
        self, data: InvoiceBatchUploadReq
    ) -> Dict[str, Any]:
        """管理员批量上传发票文件并关联到多个开票申请。

        返回：
            {
              "total": 提交条目数,
              "succeeded": 成功数,
              "failed": 失败数,
              "results": [{"invoice_id": ..., "ok": bool, "error": Optional[str]}, ...]
            }
        """
        results: List[Dict[str, Any]] = []
        succeeded = 0
        failed = 0

        for item in data.items:  # type: InvoiceBatchUploadItem
            try:
                upload_req = InvoiceUploadReq(
                    invoice_url=item.invoice_url,
                    invoice_no=item.invoice_no,
                    issued_at=item.issued_at,
                    invoice_code=item.invoice_code,
                    invoice_check_code=item.invoice_check_code,
                    file_type=item.file_type or "pdf",
                    file_size_bytes=item.file_size_bytes,
                )
                result = await self.upload(item.invoice_id, upload_req)
                if result is None:
                    results.append(
                        {
                            "invoice_id": item.invoice_id,
                            "ok": False,
                            "error": "invoice not found",
                        }
                    )
                    failed += 1
                else:
                    results.append(
                        {
                            "invoice_id": item.invoice_id,
                            "ok": True,
                            "invoice_no": result.get("invoice_no"),
                            "invoice_url": result.get("invoice_url"),
                        }
                    )
                    succeeded += 1
            except ValueError as e:
                results.append(
                    {
                        "invoice_id": item.invoice_id,
                        "ok": False,
                        "error": str(e),
                    }
                )
                failed += 1

        # 批量完成后发布一次汇总事件（方便下游一次性发送通知）
        if succeeded > 0 and data.notify:
            _publish_event(
                _EVENT_BATCH_ISSUED,
                {
                    "total": len(data.items),
                    "succeeded": succeeded,
                    "failed": failed,
                    "invoice_ids": [
                        r["invoice_id"] for r in results if r["ok"]
                    ],
                },
            )

        return {
            "total": len(data.items),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }

    # ------------------------------------------------------------------ #
    # void（issued → voided）
    # ------------------------------------------------------------------ #

    async def void(
        self, invoice_id: int, data: InvoiceVoidReq
    ) -> Optional[Dict[str, Any]]:
        """作废发票（issued → voided）。

        - 必须当前为 issued 状态
        - 作废原因追加到 notes（用空行 + "作废原因: ..." 形式拼接，原 notes 保留）
        """
        invoice = await self.db.get(Invoice, invoice_id)
        if not invoice:
            return None
        if invoice.status not in _VOIDABLE_STATUSES:
            raise ValueError(
                f"发票当前状态 '{invoice.status}' 不允许作废（仅 issued 状态可作废）"
            )

        invoice.status = "voided"
        # 作废原因追加到 notes（不破坏原有 notes）
        if invoice.notes:
            invoice.notes = f"{invoice.notes}\n作废原因: {data.void_reason}"
        else:
            invoice.notes = f"作废原因: {data.void_reason}"

        await self.db.commit()
        await self.db.refresh(invoice)
        logger.info(
            "invoice voided: id=%s reason=%s",
            invoice.id,
            data.void_reason,
        )

        # 发布 EventBus 事件
        _publish_event(
            _EVENT_VOIDED,
            {
                "invoice_id": invoice.id,
                "tenant_id": invoice.tenant_id,
                "company_id": invoice.company_id,
                "void_reason": data.void_reason,
            },
        )

        return _invoice_to_dict(invoice)

    # ------------------------------------------------------------------ #
    # record_download（Task 4.3：客户下载发票）
    # ------------------------------------------------------------------ #

    async def record_download(
        self, invoice_id: int, user_id: Optional[int] = None
    ) -> InvoiceDownloadResp:
        """记录下载并返回 invoice_url（仅 issued 状态可下载）。

        - 增加 download_count
        - 更新 last_downloaded_at / last_downloaded_by
        - 返回 InvoiceDownloadResp（含 download_url，MVP 阶段等于 invoice_url）
        - 发布 invoice.downloaded 事件（供通知/审计订阅）
        """
        invoice = await self.db.get(Invoice, invoice_id)
        if not invoice:
            raise ValueError(f"发票 {invoice_id} 不存在")
        if invoice.status not in _DOWNLOADABLE_STATUSES:
            raise ValueError(
                f"发票当前状态 '{invoice.status}' 不可下载（仅 issued 状态可下载）"
            )
        if not invoice.invoice_url:
            raise ValueError("发票文件 URL 未上传，请联系管理员")

        invoice.download_count = (invoice.download_count or 0) + 1
        invoice.last_downloaded_at = datetime.now(timezone.utc)
        invoice.last_downloaded_by = user_id
        await self.db.commit()
        await self.db.refresh(invoice)

        logger.info(
            "invoice downloaded: id=%s count=%s user=%s",
            invoice.id,
            invoice.download_count,
            user_id,
        )

        # 发布 EventBus 事件
        _publish_event(
            _EVENT_DOWNLOADED,
            {
                "invoice_id": invoice.id,
                "tenant_id": invoice.tenant_id,
                "company_id": invoice.company_id,
                "download_count": invoice.download_count,
                "downloaded_by": user_id,
            },
        )

        url = invoice.invoice_url
        return InvoiceDownloadResp(
            invoice_id=invoice.id,
            invoice_no=invoice.invoice_no,
            invoice_url=url,
            file_type=invoice.file_type or "pdf",
            file_size_bytes=invoice.file_size_bytes,
            download_url=url,  # MVP：直接返回原 URL
            download_count=invoice.download_count or 0,
            last_downloaded_at=invoice.last_downloaded_at,
        )

    # ------------------------------------------------------------------ #
    # stats
    # ------------------------------------------------------------------ #

    async def stats(self) -> InvoiceStatsResp:
        """发票统计概览。

        - 各状态计数（total/requested/issued/voided）
        - 金额汇总（total_amount 价税合计之和；tax_amount 税额之和）
        - by_invoice_type：按发票类型分组（special/normal）
        - download_total: 所有发票下载次数之和（Task 1）
        - total_downloaded_files: 已开票且至少有 1 次下载的发票数（Task 1）
        """
        # 状态分组
        by_status_rows = (
            await self.db.execute(
                select(Invoice.status, func.count(Invoice.id)).group_by(Invoice.status)
            )
        ).all()
        by_status: Dict[str, int] = {s: cnt for s, cnt in by_status_rows}

        # 金额汇总
        total_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Invoice.total_amount), ZERO))
            )
        ).scalar_one()
        tax_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Invoice.tax_amount), ZERO))
            )
        ).scalar_one()

        # 按发票类型分组
        by_type_rows = (
            await self.db.execute(
                select(Invoice.invoice_type, func.count(Invoice.id)).group_by(
                    Invoice.invoice_type
                )
            )
        ).all()
        by_type: Dict[str, int] = {t: cnt for t, cnt in by_type_rows}

        # 下载统计（Task 1）
        download_total_rows = (
            await self.db.execute(
                select(func.coalesce(func.sum(Invoice.download_count), 0))
            )
        ).scalar_one()
        download_total = int(download_total_rows or 0)

        total_downloaded_files = (
            await self.db.execute(
                select(func.count(Invoice.id)).where(Invoice.download_count > 0)
            )
        ).scalar_one()

        return InvoiceStatsResp(
            total=sum(by_status.values()),
            requested=by_status.get("requested", 0),
            issued=by_status.get("issued", 0),
            voided=by_status.get("voided", 0),
            total_amount=Decimal(total_amount or "0"),
            tax_amount=Decimal(tax_amount or "0"),
            by_invoice_type=by_type,
            download_total=download_total,
            total_downloaded_files=int(total_downloaded_files or 0),
        )


__all__ = ["InvoiceService"]
