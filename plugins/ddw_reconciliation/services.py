from __future__ import annotations

"""DDW 应收实收核销插件业务逻辑层。

设计要点：
- **不创建新表**：直接读写 P1-3 crm_receivables / P1-4 crm_offline_pos_records
- **状态机**：
  - receivable：pending/partial/paid/overdue —— 复用 P1-3 的逻辑
    （paid>=amount -> paid；0<paid<amount -> partial；paid=0 且 due<today -> overdue；否则 pending）
  - payment：pending/matched/partial/unmatched
    （matched>=amount -> matched；0<matched<amount -> partial；matched=0 -> pending；
    unmatched 是 admin 手工标记，本插件不主动写入）
- **事务**：
  - confirm / cancel 必须在单事务内完成；任一子操作失败整体回滚
- **内存历史**：
  - 模块级 ``_history: list[HistoryItem]`` 记录所有操作（不落库）
  - 模块级 ``_allocations: dict[(payment_id, receivable_id), Decimal]`` 记录每对
    (payment, receivable) 当前累计核销金额，供 cancel 快速查找
  - 每次测试 / 每次进程重启会清空（符合 spec 描述"通过操作 receivable 和
    payment 表实现核销逻辑"，历史仅做审计用，无需落库）
"""

import logging
import threading
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_offline_pos.models import Payment
from plugins.ddw_receivable.models import Receivable

from .schemas import (
    CancelReq,
    CancelResp,
    CancelResultItem,
    ConfirmMatchItem,
    ConfirmReq,
    ConfirmResp,
    ConfirmResultItem,
    HistoryItem,
    HistoryResp,
    MatchReq,
    MatchResp,
    MatchSuggestionItem,
    UnmatchedPaymentItem,
    UnmatchedReceivableItem,
    UnmatchedSummaryResp,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ZERO = Decimal(0)

# 应收允许被核销的状态（P1-3 已收清的 paid 不允许再核销）
_RECEIVABLE_MATCHABLE: frozenset[str] = frozenset({"pending", "partial", "overdue"})
# 实收允许参与核销的状态
_PAYMENT_MATCHABLE: frozenset[str] = frozenset({"pending", "partial"})
# 同一 payment 在 confirm 时可拆分的最大条数（防滥用）
MAX_MATCHES_PER_CONFIRM = 20


# ---------------------------------------------------------------------------
# 内存历史 + 分配表（模块级）
#
# 注意：
# 1) 锁用于跨 asyncio 协程的内存数据安全；SQLAlchemy session 仍由调用方管理
# 2) 测试中如需"清空历史"，用 clear_history() 显式调用
# ---------------------------------------------------------------------------

_history: list[HistoryItem] = []
_allocations: dict[tuple[int, int], Decimal] = {}
_history_seq: int = 0
_state_lock = threading.Lock()


def _next_seq() -> int:
    """原子获取下一个历史序号。"""
    global _history_seq
    with _state_lock:
        _history_seq += 1
        return _history_seq


def clear_history() -> None:
    """清空内存历史与分配表（测试用）。"""
    global _history_seq
    with _state_lock:
        _history.clear()
        _allocations.clear()
        _history_seq = 0


def get_history_snapshot() -> list[HistoryItem]:
    """返回历史快照（按 id 倒序；测试用）。"""
    with _state_lock:
        return sorted(_history, key=lambda h: h.id, reverse=True)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _recompute_receivable_status(r: Receivable) -> None:
    """应收状态机（与 P1-3 ``_recompute_status`` 同源；私有函数这里重新实现）。"""
    today = date.today()
    if r.paid_amount >= r.amount:
        r.status = "paid"
    elif r.paid_amount > ZERO:
        r.status = "partial"
    elif r.due_date < today:
        r.status = "overdue"
    else:
        r.status = "pending"


def _recompute_payment_status(p: Payment) -> None:
    """实收状态机（与 P1-4 的状态枚举一致）。"""
    if p.matched_amount >= p.amount:
        p.status = "matched"
    elif p.matched_amount > ZERO:
        p.status = "partial"
    else:
        p.status = "pending"


def _payment_to_dict(p: Payment) -> dict[str, Any]:
    """Payment ORM → dict（精简版，仅核销场景所需字段）。"""
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "company_id": p.company_id,
        "payment_no": p.payment_no,
        "payer_name": p.payer_name,
        "amount": p.amount,
        "matched_amount": p.matched_amount,
        "status": p.status,
        "payment_date": p.payment_date,
    }


def _receivable_to_dict(r: Receivable) -> dict[str, Any]:
    """Receivable ORM → dict（精简版）。"""
    paid = r.paid_amount or ZERO
    amount = r.amount or ZERO
    return {
        "id": r.id,
        "tenant_id": r.tenant_id,
        "company_id": r.company_id,
        "node_name": r.node_name,
        "amount": amount,
        "paid_amount": paid,
        "outstanding_amount": amount - paid,
        "status": r.status,
        "due_date": r.due_date,
    }


# ---------------------------------------------------------------------------
# ReconciliationService
# ---------------------------------------------------------------------------


class ReconciliationService:
    """应收实收核销业务服务。

    所有方法都直接读写 P1-3 / P1-4 的表，不创建新表。
    confirm / cancel 是事务性的，要么全部成功，要么整体回滚。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ====================================================================== #
    # 1. 匹配推荐（只读 SQL 查询，不修改任何状态）
    # ====================================================================== #

    async def match(self, req: MatchReq) -> MatchResp:
        """按 payment 自动推荐可匹配的应收列表（精确匹配：金额 + 公司）。

        规则：
        - payment.status 必须为 pending / partial
        - receivable.status 必须为 pending / partial / overdue
        - payment.company_id == receivable.company_id（任一为 None 时跳过）
        - payment.amount - payment.matched_amount == receivable.amount - receivable.paid_amount
          （即"剩余金额完全相等"）
        """
        # 1) 取 payment
        payment = await self.db.get(Payment, req.payment_id)
        if not payment:
            raise ValueError(f"实收单 payment_id={req.payment_id} 不存在")

        if payment.status not in _PAYMENT_MATCHABLE:
            raise ValueError(
                f"实收单 status='{payment.status}' 不允许参与匹配（仅 {sorted(_PAYMENT_MATCHABLE)}）"
            )

        payment_remaining = (payment.amount or ZERO) - (payment.matched_amount or ZERO)
        if payment_remaining <= ZERO:
            # 已完全核销，没东西可匹配
            return MatchResp(
                payment_id=payment.id,
                payment_no=payment.payment_no,
                payment_amount=payment.amount or ZERO,
                payment_matched_amount=payment.matched_amount or ZERO,
                payment_remaining=payment_remaining,
                payment_company_id=payment.company_id,
                payment_status=payment.status,
                suggestions=[],
            )

        # 2) 查候选 receivable（同公司 + 状态可核销 + 剩余金额 = payment_remaining）
        if payment.company_id is None:
            # 没 company_id 没法做精确匹配（spec 要求"金额 + 公司"严格相等）
            return MatchResp(
                payment_id=payment.id,
                payment_no=payment.payment_no,
                payment_amount=payment.amount or ZERO,
                payment_matched_amount=payment.matched_amount or ZERO,
                payment_remaining=payment_remaining,
                payment_company_id=None,
                payment_status=payment.status,
                suggestions=[],
            )

        stmt = (
            select(Receivable)
            .where(
                Receivable.company_id == payment.company_id,
                Receivable.status.in_(list(_RECEIVABLE_MATCHABLE)),
                # outstanding = amount - paid_amount, 用 SQL 端表达式比较
                (Receivable.amount - Receivable.paid_amount) == payment_remaining,
            )
            .order_by(Receivable.due_date.asc(), Receivable.id.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        suggestions: list[MatchSuggestionItem] = []
        for r in rows:
            paid = r.paid_amount or ZERO
            amount = r.amount or ZERO
            outstanding = amount - paid
            suggestions.append(
                MatchSuggestionItem(
                    receivable_id=r.id,
                    node_name=r.node_name,
                    company_id=r.company_id,
                    amount=amount,
                    paid_amount=paid,
                    outstanding_amount=outstanding,
                    due_date=r.due_date,
                    status=r.status,
                    match_type="exact",
                    suggested_amount=outstanding,  # exact 时建议把 receivable 一笔收齐
                    confidence=1.0,
                )
            )

        return MatchResp(
            payment_id=payment.id,
            payment_no=payment.payment_no,
            payment_amount=payment.amount or ZERO,
            payment_matched_amount=payment.matched_amount or ZERO,
            payment_remaining=payment_remaining,
            payment_company_id=payment.company_id,
            payment_status=payment.status,
            suggestions=suggestions,
        )

    # ====================================================================== #
    # 2. 确认核销（事务）
    # ====================================================================== #

    async def confirm(self, req: ConfirmReq) -> ConfirmResp:
        """确认核销：事务内更新多个 receivable + 一个 payment。

        业务规则：
        - payment.status 必须为 pending / partial
        - 每个 receivable.status 必须为 pending / partial / overdue
        - sum(matches.amount) 必须 <= payment.amount - payment.matched_amount
        - 不允许 receivable 收款超额（默认严格模式，allow_overpay=False）
        - 任何子操作失败 → 整体 rollback
        """
        if len(req.matches) > MAX_MATCHES_PER_CONFIRM:
            raise ValueError(
                f"单次核销最多 {MAX_MATCHES_PER_CONFIRM} 条，实际 {len(req.matches)} 条"
            )

        # ---- 1) 取 payment ----
        payment = await self.db.get(Payment, req.payment_id)
        if not payment:
            raise ValueError(f"实收单 payment_id={req.payment_id} 不存在")
        if payment.status not in _PAYMENT_MATCHABLE:
            raise ValueError(
                f"实收单 status='{payment.status}' 不允许核销（仅 {sorted(_PAYMENT_MATCHABLE)}）"
            )

        payment_remaining = (payment.amount or ZERO) - (payment.matched_amount or ZERO)
        if payment_remaining <= ZERO:
            raise ValueError(
                f"实收单 payment_id={req.payment_id} 已完全核销（remaining={payment_remaining}）"
            )

        # ---- 2) 校验：总和不超额 ----
        total_to_match = sum((m.amount for m in req.matches), ZERO)
        if total_to_match <= ZERO:
            raise ValueError("matches 总和必须 > 0")
        if total_to_match > payment_remaining:
            raise ValueError(
                f"matches 总和 {total_to_match} 超过实收单剩余可核销金额 {payment_remaining}"
            )

        # ---- 3) 逐条加载 receivable 并校验 ----
        loaded: list[tuple[ConfirmMatchItem, Receivable]] = []
        for m in req.matches:
            r = await self.db.get(Receivable, m.receivable_id)
            if not r:
                raise ValueError(f"应收 receivable_id={m.receivable_id} 不存在")
            if r.status not in _RECEIVABLE_MATCHABLE:
                raise ValueError(
                    f"应收 receivable_id={m.receivable_id} status='{r.status}' 不允许核销"
                )
            # 不允许超付
            current_paid = r.paid_amount or ZERO
            if current_paid + m.amount > r.amount:
                raise ValueError(
                    f"应收 receivable_id={m.receivable_id} 已收 {current_paid} + 本次 {m.amount} "
                    f"将超过应收金额 {r.amount}（默认不允许超付）"
                )
            loaded.append((m, r))

        # ---- 4) 事务：扣 receivable + payment，写历史 ----
        payment_status_before = payment.status
        payment_matched_before = payment.matched_amount or ZERO

        # 用 SAVEPOINT 风格的嵌套事务确保 confirm 整体原子
        try:
            for m, r in loaded:
                r.paid_amount = (r.paid_amount or ZERO) + Decimal(m.amount)
                _recompute_receivable_status(r)

            payment.matched_amount = (payment.matched_amount or ZERO) + total_to_match
            _recompute_payment_status(payment)

            await self.db.commit()
        except Exception:
            await self.db.rollback()
            logger.exception("confirm 失败，已回滚 payment_id=%s", req.payment_id)
            raise

        # 刷新让 updated_at 等自动字段同步
        for _m, r in loaded:
            await self.db.refresh(r)
        await self.db.refresh(payment)

        # ---- 5) 写内存历史 + 分配表 ----
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        results: list[ConfirmResultItem] = []
        # 一次性分配历史 id（一条 confirm = 1 个聚合 history 记录 + N 个明细）
        history_id = _next_seq()
        for m, r in loaded:
            paid = r.paid_amount or ZERO
            amount = r.amount or ZERO
            results.append(
                ConfirmResultItem(
                    receivable_id=r.id,
                    paid_amount=paid,
                    outstanding_amount=amount - paid,
                    status=r.status,
                    matched_this_time=Decimal(m.amount),
                )
            )
            with _state_lock:
                key = (payment.id, r.id)
                _allocations[key] = _allocations.get(key, ZERO) + Decimal(m.amount)
                _history.append(
                    HistoryItem(
                        id=history_id,  # confirm 内 N 条 history 共用同一 id
                        action="confirm",
                        payment_id=payment.id,
                        receivable_id=r.id,
                        amount=Decimal(m.amount),
                        timestamp=now,
                        payment_status_before=payment_status_before,
                        payment_status_after=payment.status,
                        payment_matched_before=payment_matched_before,
                        payment_matched_after=payment.matched_amount or ZERO,
                        receivable_status_before=None,  # 简化：confirm 同一事务内前态
                        receivable_status_after=r.status,
                        receivable_paid_before=None,
                        receivable_paid_after=paid,
                    )
                )

        logger.info(
            "reconciliation confirm: payment_id=%s total=%s -> status=%s history_id=%s",
            payment.id, total_to_match, payment.status, history_id,
        )

        return ConfirmResp(
            payment_id=payment.id,
            payment_no=payment.payment_no,
            payment_status=payment.status,
            payment_matched_amount=payment.matched_amount or ZERO,
            payment_remaining=(payment.amount or ZERO) - (payment.matched_amount or ZERO),
            total_matched=total_to_match,
            results=results,
            history_id=history_id,
        )

    # ====================================================================== #
    # 3. 取消核销（事务）
    # ====================================================================== #

    async def cancel(self, req: CancelReq) -> CancelResp:
        """取消核销：回退 payment / receivable 的已核销金额。

        两种模式：
        - 取消单条：cancel(payment_id=X, receivable_id=Y) —— 回退 (X, Y) 配对
        - 整笔回退：cancel(payment_id=X, cancel_all=True) —— 把 payment X 上的
          所有 (X, *) 配对一次性回退
        """
        if not req.cancel_all and req.receivable_id is None:
            raise ValueError("必须提供 receivable_id 或 cancel_all=True 之一")
        if req.cancel_all and req.receivable_id is not None:
            raise ValueError("receivable_id 与 cancel_all 互斥，只能二选一")

        # ---- 1) 取 payment ----
        payment = await self.db.get(Payment, req.payment_id)
        if not payment:
            raise ValueError(f"实收单 payment_id={req.payment_id} 不存在")

        # ---- 2) 找要回退的 receivable 列表 ----
        with _state_lock:
            if req.cancel_all:
                targets: list[tuple[int, Decimal]] = [
                    (rid, amt)
                    for (pid, rid), amt in _allocations.items()
                    if pid == req.payment_id and amt > ZERO
                ]
            else:
                assert req.receivable_id is not None
                amt = _allocations.get((req.payment_id, req.receivable_id), ZERO)
                if amt <= ZERO:
                    raise ValueError(
                        f"payment_id={req.payment_id} 与 receivable_id={req.receivable_id} "
                        f"之间没有可回退的核销记录"
                    )
                targets = [(req.receivable_id, amt)]

        if not targets:
            raise ValueError(f"payment_id={req.payment_id} 没有任何可回退的核销")

        # ---- 3) 加载 receivable 校验 ----
        loaded: list[tuple[int, Decimal, Receivable]] = []
        for rid, amt in targets:
            r = await self.db.get(Receivable, rid)
            if not r:
                raise ValueError(f"应收 receivable_id={rid} 不存在")
            loaded.append((rid, amt, r))

        # ---- 4) 事务：回退 receivable + payment ----
        payment_status_before = payment.status
        payment_matched_before = payment.matched_amount or ZERO

        try:
            total_reversed = ZERO
            for _rid, amt, r in loaded:
                r.paid_amount = (r.paid_amount or ZERO) - Decimal(amt)
                if r.paid_amount < ZERO:
                    # 防御性：理论上 _allocations 与实际应收不会矛盾
                    raise ValueError(
                        f"应收 receivable_id={r.id} paid_amount 扣成负数 "
                        f"({r.paid_amount})，数据异常"
                    )
                _recompute_receivable_status(r)
                total_reversed += Decimal(amt)

            payment.matched_amount = (payment.matched_amount or ZERO) - total_reversed
            if payment.matched_amount < ZERO:
                raise ValueError(
                    f"实收单 payment_id={payment.id} matched_amount 扣成负数，"
                    f"数据异常"
                )
            _recompute_payment_status(payment)

            await self.db.commit()
        except Exception:
            await self.db.rollback()
            logger.exception("cancel 失败，已回滚 payment_id=%s", req.payment_id)
            raise

        for _rid, _amt, r in loaded:
            await self.db.refresh(r)
        await self.db.refresh(payment)

        # ---- 5) 写内存历史 + 删分配表 ----
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        results: list[CancelResultItem] = []
        history_id = _next_seq()
        with _state_lock:
            for rid, amt, r in loaded:
                paid = r.paid_amount or ZERO
                amount = r.amount or ZERO
                results.append(
                    CancelResultItem(
                        receivable_id=rid,
                        reversed_amount=Decimal(amt),
                        paid_amount=paid,
                        outstanding_amount=amount - paid,
                        status=r.status,
                    )
                )
                # 清掉分配表（允许多次 cancel：只清已回退的部分）
                key = (payment.id, rid)
                _allocations.pop(key, None)
                _history.append(
                    HistoryItem(
                        id=history_id,
                        action="cancel",
                        payment_id=payment.id,
                        receivable_id=rid,
                        amount=Decimal(amt),
                        timestamp=now,
                        payment_status_before=payment_status_before,
                        payment_status_after=payment.status,
                        payment_matched_before=payment_matched_before,
                        payment_matched_after=payment.matched_amount or ZERO,
                        receivable_status_before=None,
                        receivable_status_after=r.status,
                        receivable_paid_before=None,
                        receivable_paid_after=paid,
                    )
                )

        logger.info(
            "reconciliation cancel: payment_id=%s reversed=%s -> status=%s history_id=%s",
            payment.id, total_reversed, payment.status, history_id,
        )

        return CancelResp(
            payment_id=payment.id,
            payment_no=payment.payment_no,
            payment_status=payment.status,
            payment_matched_amount=payment.matched_amount or ZERO,
            total_reversed=total_reversed,
            results=results,
            history_id=history_id,
        )

    # ====================================================================== #
    # 4. 核销历史（从内存读）
    # ====================================================================== #

    async def history(
        self,
        page: int = 1,
        page_size: int = 50,
        payment_id: Optional[int] = None,
        action: Optional[str] = None,
    ) -> HistoryResp:
        """核销历史（从内存 _history 读取）。

        可选过滤：
        - payment_id：只返回该 payment 的历史
        - action：confirm / cancel
        """
        with _state_lock:
            items = list(_history)

        if payment_id is not None:
            items = [h for h in items if h.payment_id == payment_id]
        if action:
            items = [h for h in items if h.action == action]

        items.sort(key=lambda h: h.id, reverse=True)

        total = len(items)
        offset = max(0, (page - 1) * page_size)
        page_items = items[offset : offset + page_size]

        return HistoryResp(total=total, items=page_items)

    # ====================================================================== #
    # 5. 未核销汇总
    # ====================================================================== #

    async def unmatched(self) -> UnmatchedSummaryResp:
        """未核销汇总：分别拉 status=pending/partial 的 payment 与
        status=pending/partial/overdue 的 receivable，附带汇总金额。
        """
        # ---- payments ----
        pay_stmt = (
            select(Payment)
            .where(
                Payment.status.in_(list(_PAYMENT_MATCHABLE)),
                Payment.matched_amount < Payment.amount,
            )
            .order_by(Payment.payment_date.asc(), Payment.id.asc())
        )
        pay_rows = (await self.db.execute(pay_stmt)).scalars().all()
        pay_items: list[UnmatchedPaymentItem] = []
        pay_total = ZERO
        for p in pay_rows:
            matched = p.matched_amount or ZERO
            amount = p.amount or ZERO
            unmatched = amount - matched
            pay_total += unmatched
            pay_items.append(
                UnmatchedPaymentItem(
                    id=p.id,
                    payment_no=p.payment_no,
                    payer_name=p.payer_name,
                    company_id=p.company_id,
                    amount=amount,
                    matched_amount=matched,
                    unmatched_amount=unmatched,
                    status=p.status,
                    payment_date=p.payment_date,
                )
            )

        # ---- receivables ----
        recv_stmt = (
            select(Receivable)
            .where(
                Receivable.status.in_(list(_RECEIVABLE_MATCHABLE)),
                Receivable.paid_amount < Receivable.amount,
            )
            .order_by(Receivable.due_date.asc(), Receivable.id.asc())
        )
        recv_rows = (await self.db.execute(recv_stmt)).scalars().all()
        recv_items: list[UnmatchedReceivableItem] = []
        recv_total = ZERO
        for r in recv_rows:
            paid = r.paid_amount or ZERO
            amount = r.amount or ZERO
            outstanding = amount - paid
            recv_total += outstanding
            recv_items.append(
                UnmatchedReceivableItem(
                    id=r.id,
                    node_name=r.node_name,
                    company_id=r.company_id,
                    order_id=r.order_id,
                    amount=amount,
                    paid_amount=paid,
                    outstanding_amount=outstanding,
                    status=r.status,
                    due_date=r.due_date,
                )
            )

        return UnmatchedSummaryResp(
            payment_count=len(pay_items),
            receivable_count=len(recv_items),
            payment_unmatched_total=pay_total,
            receivable_outstanding_total=recv_total,
            payments=pay_items,
            receivables=recv_items,
        )


__all__ = [
    "MAX_MATCHES_PER_CONFIRM",
    "ReconciliationService",
    "clear_history",
    "get_history_snapshot",
]
