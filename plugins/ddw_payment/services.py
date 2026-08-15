"""DDW 实收管理插件业务逻辑层。

关键函数：
- :func:`generate_payment_no` —— 按 PAY-YYYYMMDD-NNN 规则生成单号

服务：
- :class:`PaymentService` —— 实收 CRUD + 状态机查询 + 统计 + 未核销列表
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Payment
from .schemas import (
    PaymentCreateReq,
    PaymentListResp,
    PaymentResp,
    PaymentStatsResp,
    PaymentUnmatchedListResp,
    PaymentUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 辅助函数：单号生成
# ---------------------------------------------------------------------------


async def generate_payment_no(db: AsyncSession) -> str:
    """生成当日唯一单号：PAY-YYYYMMDD-NNN（NNN 从 001 开始递增）。

    通过 ``like 'PAY-YYYYMMDD-%'`` 查出当日所有单号，解析末段序号取最大值 + 1。
    极小概率碰撞：理论上同毫秒并发插入可能拿到相同序号，
    数据库 unique 约束兜底（重复时由调用方在 ``IntegrityError`` 中重试）。
    """
    today_str = date.today().strftime("%Y%m%d")
    prefix = f"PAY-{today_str}-"
    stmt = select(Payment.payment_no).where(Payment.payment_no.like(f"{prefix}%"))
    rows = (await db.execute(stmt)).scalars().all()
    max_seq = 0
    for no in rows:
        try:
            seq = int(no.rsplit("-", 1)[-1])
            if seq > max_seq:
                max_seq = seq
        except (ValueError, IndexError):
            continue
    return f"{prefix}{max_seq + 1:03d}"


# ---------------------------------------------------------------------------
# 辅助函数：序列化
# ---------------------------------------------------------------------------


ZERO = Decimal("0")
ONE = Decimal("1")


def _payment_to_dict(p: Payment, include_unmatched_amount: bool = False) -> Dict[str, Any]:
    """Payment ORM → dict。

    :param include_unmatched_amount: 未核销列表场景下额外计算 ``unmatched_amount``。
    """
    base: Dict[str, Any] = {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "company_id": p.company_id,
        "payment_no": p.payment_no,
        "payer_name": p.payer_name,
        "bank_reference": p.bank_reference,
        "bank_account": p.bank_account,
        "amount": p.amount,
        "payment_date": p.payment_date,
        "payment_method": p.payment_method,
        "notes": p.notes,
        "status": p.status,
        "matched_amount": p.matched_amount,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "created_by": p.created_by,
    }
    if include_unmatched_amount:
        base["unmatched_amount"] = (p.amount or ZERO) - (p.matched_amount or ZERO)
    return base


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class PaymentService:
    """实收业务服务。

    设计原则：
    - 本插件**不**实现核销逻辑。``status`` 中除 pending 外的状态、``matched_amount``
      字段均由 P1-5 reconciliation 写入；本插件只创建、查询、统计。
    - 仅 pending 状态允许更新（防误改已核销的实收记录）。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #

    async def create(self, data: PaymentCreateReq) -> Dict[str, Any]:
        """新建实收。

        - 自动生成 payment_no（PAY-YYYYMMDD-NNN）
        - 状态默认为 pending
        - matched_amount 默认 0
        """
        payment_no = await generate_payment_no(self.db)

        payment = Payment(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            payment_no=payment_no,
            payer_name=data.payer_name,
            bank_reference=data.bank_reference,
            bank_account=data.bank_account,
            amount=data.amount,
            payment_date=data.payment_date,
            payment_method=data.payment_method,
            notes=data.notes,
            status="pending",
            matched_amount=ZERO,
            created_by=data.created_by,
        )
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)

        logger.info(
            "payment created: id=%s no=%s payer=%s amount=%s method=%s",
            payment.id,
            payment.payment_no,
            payment.payer_name,
            payment.amount,
            payment.payment_method,
        )
        return _payment_to_dict(payment)

    # ------------------------------------------------------------------ #
    # get
    # ------------------------------------------------------------------ #

    async def get(self, payment_id: int) -> Optional[Dict[str, Any]]:
        """获取实收详情。"""
        payment = await self.db.get(Payment, payment_id)
        if not payment:
            return None
        return _payment_to_dict(payment)

    # ------------------------------------------------------------------ #
    # list
    # ------------------------------------------------------------------ #

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        company_id: Optional[int] = None,
        payer_name: Optional[str] = None,
        payment_no: Optional[str] = None,
        payment_method: Optional[str] = None,
        status: Optional[str] = None,
        payment_date_from: Optional[date] = None,
        payment_date_to: Optional[date] = None,
    ) -> PaymentListResp:
        """实收列表（分页 + 多维筛选）。

        筛选字段：
        - company_id：精确匹配
        - payer_name：模糊匹配（LIKE '%payer_name%'）
        - payment_no：模糊匹配（LIKE '%payment_no%'）
        - payment_method：精确匹配
        - status：精确匹配
        - payment_date_from / payment_date_to：日期区间闭区间
        """
        conditions = []
        if company_id is not None:
            conditions.append(Payment.company_id == company_id)
        if payer_name:
            conditions.append(Payment.payer_name.like(f"%{payer_name}%"))
        if payment_no:
            conditions.append(Payment.payment_no.like(f"%{payment_no}%"))
        if payment_method:
            conditions.append(Payment.payment_method == payment_method)
        if status:
            conditions.append(Payment.status == status)
        if payment_date_from is not None:
            conditions.append(Payment.payment_date >= payment_date_from)
        if payment_date_to is not None:
            conditions.append(Payment.payment_date <= payment_date_to)

        # total
        count_stmt = select(func.count(Payment.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(Payment)
            .order_by(Payment.payment_date.desc(), Payment.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return PaymentListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[PaymentResp(**_payment_to_dict(p)) for p in rows],
        )

    # ------------------------------------------------------------------ #
    # update（仅 pending 状态可改）
    # ------------------------------------------------------------------ #

    async def update(
        self, payment_id: int, data: PaymentUpdateReq
    ) -> Optional[Dict[str, Any]]:
        """更新实收。

        约束：
        - 仅 ``status == "pending"`` 状态允许修改（防误改已核销记录）
        - 字段级更新（model_dump(exclude_unset=True)）
        - payment_no / status / matched_amount / created_at / created_by 不允许通过本接口改
        """
        payment = await self.db.get(Payment, payment_id)
        if not payment:
            return None
        if payment.status != "pending":
            raise ValueError(
                f"实收单当前状态 '{payment.status}' 不允许修改（仅 pending 状态可改）"
            )

        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(payment, k, v)

        await self.db.commit()
        await self.db.refresh(payment)
        logger.info(
            "payment updated: id=%s no=%s fields=%s",
            payment.id,
            payment.payment_no,
            sorted(updates.keys()),
        )
        return _payment_to_dict(payment)

    # ------------------------------------------------------------------ #
    # unmatched（未核销列表，供 P1-5 reconciliation 拉取）
    # ------------------------------------------------------------------ #

    async def list_unmatched(
        self,
        page: int = 1,
        page_size: int = 20,
        company_id: Optional[int] = None,
    ) -> PaymentUnmatchedListResp:
        """未核销实收列表（status=pending 或 partial，matched_amount < amount）。

        用于 P1-5 reconciliation 拉取待核销数据。
        响应中每条记录额外带 ``unmatched_amount``（amount - matched_amount）。
        """
        # 未核销条件：matched_amount < amount AND status IN (pending, partial)
        conditions = [
            Payment.matched_amount < Payment.amount,
            Payment.status.in_(["pending", "partial"]),
        ]
        if company_id is not None:
            conditions.append(Payment.company_id == company_id)

        count_stmt = select(func.count(Payment.id)).where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        offset = (page - 1) * page_size
        list_stmt = (
            select(Payment)
            .where(and_(*conditions))
            .order_by(Payment.payment_date.asc(), Payment.id.asc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return PaymentUnmatchedListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[PaymentResp(**_payment_to_dict(p, include_unmatched_amount=True))
                               for p in rows],
        )

    # ------------------------------------------------------------------ #
    # stats
    # ------------------------------------------------------------------ #

    async def stats(self) -> PaymentStatsResp:
        """统计概览：各状态计数 + 总收款金额 + 已核销金额 + 未核销金额。

        状态由本插件创建时默认 pending，matched/partial/unmatched 由 P1-5 维护。
        """
        # 状态分组
        by_status_rows = (
            await self.db.execute(
                select(Payment.status, func.count(Payment.id)).group_by(Payment.status)
            )
        ).all()
        by_status: Dict[str, int] = {s: cnt for s, cnt in by_status_rows}

        # 总收款金额
        total_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Payment.amount), ZERO))
            )
        ).scalar_one()

        # 已核销金额
        matched_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(Payment.matched_amount), ZERO))
            )
        ).scalar_one()

        # Decimal 化
        total_amount_d = Decimal(total_amount) if total_amount is not None else ZERO
        matched_amount_d = Decimal(
            matched_amount) if matched_amount is not None else ZERO
        unmatched_amount_d = total_amount_d - matched_amount_d

        return PaymentStatsResp(
            total=sum(by_status.values()),
            pending=by_status.get("pending", 0),
            partial=by_status.get("partial", 0),
            matched=by_status.get("matched", 0),
            unmatched=by_status.get("unmatched", 0),
            total_amount=total_amount_d,
            matched_amount=matched_amount_d,
            unmatched_amount=unmatched_amount_d,
        )


__all__ = [
    "PaymentService",
    "generate_payment_no",
]
