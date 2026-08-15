from __future__ import annotations

"""DDW 应收管理插件业务逻辑层。

关键设计：
- :func:`_recompute_status` —— 应收写入 paid_amount 后自动重算 status
  规则：paid>=amount -> paid；0<paid<amount -> partial；paid=0 且 due<today -> overdue；
  否则 pending
- :func:`_auto_mark_overdue` —— list/stats/overdue 等 read 类操作前，
  用 SQL 批量把 pending/partial 中 due_date<today 的标记为 overdue，
  避免查询时再过滤
- :class:`ReceivableService` —— CRUD + 收款 + 统计 + 逾期列表
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Receivable
from .schemas import (
    ReceivableCreateReq,
    ReceivableListResp,
    ReceivableOverdueListResp,
    ReceivableResp,
    ReceivableStatsResp,
    ReceivableUpdateReq,
    RecordPaymentReq,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# 状态机合法迁移（业务侧限制：已付清 / 部分收不可改基本信息）
_EDITABLE_STATUSES: frozenset[str] = frozenset({"pending", "overdue"})


# ---------------------------------------------------------------------------
# 内部辅助：状态重算
# ---------------------------------------------------------------------------


def _recompute_status(r: Receivable) -> None:
    """根据 paid_amount / amount / due_date 重算 r.status。

    规则（按优先级）：
    1. paid_amount >= amount          -> paid
    2. 0 < paid_amount < amount       -> partial
    3. paid_amount == 0 且 due<today   -> overdue
    4. 其他                              -> pending
    """
    today = date.today()
    if r.paid_amount >= r.amount:
        r.status = "paid"
    elif r.paid_amount > ZERO:
        r.status = "partial"
    elif r.due_date < today:
        r.status = "overdue"
    else:
        r.status = "pending"


async def _auto_mark_overdue(db: AsyncSession) -> None:
    """批量把 pending/partial 中 due_date<today 的标记为 overdue。

    在 read 类操作（list/stats/overdue）前调用一次，避免业务侧在 read 时
    还要再次按 due_date 过滤。
    """
    today = date.today()
    stmt = (
        update(Receivable)
        .where(
            Receivable.status.in_(["pending", "partial"]),
            Receivable.due_date < today,
        )
        .values(status="overdue")
    )
    await db.execute(stmt)
    await db.commit()


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _recv_to_dict(r: Receivable) -> Dict[str, Any]:
    """ORM -> dict（含 outstanding_amount 计算字段）。"""
    paid = r.paid_amount or ZERO
    amount = r.amount or ZERO
    return {
        "id": r.id,
        "tenant_id": r.tenant_id,
        "company_id": r.company_id,
        "order_id": r.order_id,
        "contract_id": r.contract_id,
        "plan_name": r.plan_name,
        "node_name": r.node_name,
        "amount": amount,
        "paid_amount": paid,
        "outstanding_amount": amount - paid,
        "due_date": r.due_date,
        "paid_at": r.paid_at,
        "status": r.status,
        "notes": r.notes,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "created_by": r.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class ReceivableService:
    """应收业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- CRUD -----

    async def create(self, data: ReceivableCreateReq) -> Dict[str, Any]:
        """新建应收。

        - 初始 paid_amount=0, status=pending（如果 due_date<today 会由后续
          list 操作自动改为 overdue；不在 create 时直接判定，避免并发问题）
        """
        r = Receivable(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            order_id=data.order_id,
            contract_id=data.contract_id,
            plan_name=data.plan_name,
            node_name=data.node_name,
            amount=data.amount,
            paid_amount=ZERO,
            due_date=data.due_date,
            status="pending",
            notes=data.notes,
            created_by=data.created_by,
        )
        self.db.add(r)
        await self.db.commit()
        await self.db.refresh(r)
        logger.info(
            "receivable created: id=%s node=%s amount=%s due=%s",
            r.id, r.node_name, r.amount, r.due_date,
        )
        return _recv_to_dict(r)

    async def get(self, receivable_id: int) -> Optional[Dict[str, Any]]:
        """获取应收详情。"""
        r = await self.db.get(Receivable, receivable_id)
        if not r:
            return None
        return _recv_to_dict(r)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        company_id: Optional[int] = None,
        order_id: Optional[int] = None,
        contract_id: Optional[int] = None,
        status: Optional[str] = None,
        due_before: Optional[date] = None,
        due_after: Optional[date] = None,
    ) -> ReceivableListResp:
        """应收列表（分页 + 多维筛选）。

        操作前先 ``_auto_mark_overdue`` 一次，确保状态是最新的。
        """
        await _auto_mark_overdue(self.db)

        conditions = []
        if company_id is not None:
            conditions.append(Receivable.company_id == company_id)
        if order_id is not None:
            conditions.append(Receivable.order_id == order_id)
        if contract_id is not None:
            conditions.append(Receivable.contract_id == contract_id)
        if status:
            conditions.append(Receivable.status == status)
        if due_before is not None:
            conditions.append(Receivable.due_date <= due_before)
        if due_after is not None:
            conditions.append(Receivable.due_date >= due_after)

        # total
        count_stmt = select(func.count(Receivable.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # 列表
        offset = (page - 1) * page_size
        list_stmt = (
            select(Receivable)
            .order_by(Receivable.due_date.asc(), Receivable.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return ReceivableListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[ReceivableResp(**_recv_to_dict(r)) for r in rows],
        )

    async def update(
        self, receivable_id: int, data: ReceivableUpdateReq
    ) -> Optional[Dict[str, Any]]:
        """更新应收。

        业务规则：
        - 仅 ``_EDITABLE_STATUSES`` （pending/overdue）状态允许改基本信息
        - partial / paid 状态拒绝修改（避免破坏已建立的对账数据）
        """
        r = await self.db.get(Receivable, receivable_id)
        if not r:
            return None
        if r.status not in _EDITABLE_STATUSES:
            raise ValueError(
                f"当前 status='{r.status}' 不允许修改（仅允许 pending/overdue）"
            )

        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(r, k, v)

        await self.db.commit()
        await self.db.refresh(r)
        logger.info("receivable updated: id=%s fields=%s", r.id, list(updates.keys()))
        return _recv_to_dict(r)

    # ----- 收款（核心业务） -----

    async def record_payment(
        self, receivable_id: int, data: RecordPaymentReq
    ) -> Optional[Dict[str, Any]]:
        """记录一次收款（增量累加）。

        - paid_amount += payment_amount（允许超额，超额仍按 paid 处理）
        - paid_at = payment_date or now(UTC)
        - 调用 _recompute_status 重算 status
        """
        r = await self.db.get(Receivable, receivable_id)
        if not r:
            return None

        current_paid = r.paid_amount or ZERO
        r.paid_amount = current_paid + Decimal(data.payment_amount)
        r.paid_at = data.payment_date or datetime.now(timezone.utc).replace(tzinfo=None)
        _recompute_status(r)

        await self.db.commit()
        await self.db.refresh(r)
        logger.info(
            "receivable payment: id=%s +%s -> paid=%s status=%s",
            r.id, data.payment_amount, r.paid_amount, r.status,
        )
        return _recv_to_dict(r)

    # ----- 逾期 / 统计 -----

    async def overdue(
        self, page: int = 1, page_size: int = 50
    ) -> ReceivableOverdueListResp:
        """逾期列表（专用接口，先 auto_mark 再拉）。

        业务语义：due_date < today 且尚未付清（status='overdue' 或 'partial' 中
        已过期的也会被先标记成 overdue）。这里只取 status='overdue' 的记录。
        """
        await _auto_mark_overdue(self.db)

        # 总额：所有 overdue 应收的 amount 与 paid 差
        sum_stmt = select(
            func.coalesce(func.sum(Receivable.amount), 0).label("total_amt"),
            func.coalesce(func.sum(Receivable.paid_amount), 0).label("total_paid"),
        ).where(Receivable.status == "overdue")
        total_amt, total_paid = (await self.db.execute(sum_stmt)).one()

        # 列表
        offset = (page - 1) * page_size
        list_stmt = (
            select(Receivable)
            .where(Receivable.status == "overdue")
            .order_by(Receivable.due_date.asc(), Receivable.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return ReceivableOverdueListResp(
            total=len(rows) + offset,  # 简单展示当前页的 offset+len（不重跑 count）
            items=[ReceivableResp(**_recv_to_dict(r)) for r in rows],
            total_overdue_amount=Decimal(total_amt or 0),
            total_outstanding_amount=Decimal(total_amt or 0) - Decimal(total_paid or 0),
        )

    async def stats(self) -> ReceivableStatsResp:
        """统计概览：各状态计数 + 应收/已收/未收总额。

        操作前先 ``_auto_mark_overdue`` 一次，保证 overdue 计数最新。
        """
        await _auto_mark_overdue(self.db)

        by_status_rows = (
            await self.db.execute(
                select(Receivable.status, func.count(Receivable.id)).group_by(
                    Receivable.status
                )
            )
        ).all()
        by_status: Dict[str, int] = {s: c for s, c in by_status_rows}

        total_amt = (
            await self.db.execute(
                select(func.coalesce(func.sum(Receivable.amount), ZERO))
            )
        ).scalar_one()
        paid_amt = (
            await self.db.execute(
                select(func.coalesce(func.sum(Receivable.paid_amount), ZERO))
            )
        ).scalar_one()

        total_amount = Decimal(total_amt or 0)
        paid_amount = Decimal(paid_amt or 0)
        return ReceivableStatsResp(
            total=sum(by_status.values()),
            pending=by_status.get("pending", 0),
            partial=by_status.get("partial", 0),
            paid=by_status.get("paid", 0),
            overdue=by_status.get("overdue", 0),
            total_amount=total_amount,
            paid_amount=paid_amount,
            outstanding_amount=total_amount - paid_amount,
        )


__all__ = [
    "ReceivableService",
    "_auto_mark_overdue",
    "_recompute_status",
]
