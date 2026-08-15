"""ddw_wallet API 路由 — 全部端点（三钱包 + 多租户 + 异步队列）。"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, date
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Header, Request, Query
from sqlalchemy import select, func as sa_func

from plugins.ddw_wallet.models import (
    AuditLog,
    ChargeRecord,
    RateRule,
    RawCallback,
    RechargeOrder,
    RefundRecord,
    RoyaltyRecord,
)
logger = logging.getLogger(__name__)

from plugins.ddw_wallet.schemas import (
    ChargeCreate,
    ChargeOut,
    FreezeRequest,
    PaginatedTransactions,
    PlatformAccountOut,
    RateRuleOut,
    RechargeCreate,
    RechargeOut,
    ReconcileRequest,
    RefundCreate,
    RefundOut,
    RoyaltyCreate,
    RoyaltyOut,
    TransactionOut,
    WalletAccountOut,
    WithdrawCreate,
    WithdrawOut,
)
from plugins.ddw_wallet.services.account import (
    InsufficientBalanceError,
    freeze_balance,
    get_or_create_account,
    get_three_balances,
    unfreeze_balance,
)
from plugins.ddw_wallet.services.charge import charge, charge_with_fallback
from plugins.ddw_wallet.services.recharge import (
    create_recharge,
    get_recharge_order,
    handle_wechat_notify,
)
from plugins.ddw_wallet.services.refund import refund_balance, handle_refund_notify
from plugins.ddw_wallet.services.royalty import settle_royalty
from plugins.ddw_wallet.services.reconciliation import reconcile
from plugins.ddw_wallet.services.withdraw import create_withdraw

PREFIX = "/api/v1/plugins/ddw_wallet"

# ── 异步回调队列（G11）────────────────────────────────

_callback_queue: asyncio.Queue = None  # 懒创建，避免 import 即崩
_worker_started = False


async def _process_raw_callback(raw: RawCallback):
    """处理单条原始回调。"""
    from core.database.session import session_scope

    async with session_scope() as s:
        try:
            headers = json.loads(raw.headers) if raw.headers else {}
            body = raw.body if hasattr(raw, 'body') else raw.raw_body
            data = json.loads(body)

            if raw.channel == "wechat":
                from plugins.ddw_wallet.services.wechat_pay import decrypt_notify
                decrypted = decrypt_notify(headers, body)
                ok_, reply = await handle_wechat_notify(s, decrypted)
            elif raw.channel == "alipay":
                from plugins.ddw_wallet.services.alipay_client import verify_notify
                params = data.get("params", data)
                if not verify_notify(params, params.get("sign", "")):
                    ok_, reply = False, "验签失败"
                else:
                    # 支付宝入账逻辑（复用 recharge）
                    from plugins.ddw_wallet.services.recharge import handle_alipay_notify
                    ok_, reply = await handle_alipay_notify(s, params)
            else:
                ok_, _reply = False, f"未知通道: {raw.channel}"

            await s.commit()

            raw.status = "processed" if ok_ else "failed"
            raw.processed_at = datetime.now()
            await s.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Callback %d failed: %s", raw.id, exc)
            raw.status = "failed"
            await s.commit()


async def _callback_worker():
    """进程内异步 worker（不引 Celery/Redis）。"""
    while True:
        if _callback_queue is None:
            await asyncio.sleep(1)
            continue
        raw = await _callback_queue.get()
        for attempt in range(3):
            try:
                await _process_raw_callback(raw)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Callback %d attempt %d failed: %s", raw.id, attempt + 1, exc)
                if attempt < 2:
                    await asyncio.sleep(1)
        _callback_queue.task_done()


async def start_callback_worker():
    """启动回调 worker（插件 setup 时调用）。"""
    global _worker_started, _callback_queue
    if _callback_queue is None:
        _callback_queue = asyncio.Queue()
    if not _worker_started:
        asyncio.create_task(_callback_worker())
        _worker_started = True
        logger.info("RawCallback worker started")


# ── 辅助 ──────────────────────────────────────────────

def _get_tenant_id(x_tenant_id: str = Header(default="default")) -> str:
    """从请求头取租户 ID（C6）。"""
    return x_tenant_id or "default"


def build_router() -> APIRouter:
    """构建钱包路由。"""
    r = APIRouter(prefix=PREFIX, tags=["ddw_wallet"])

    # ── 健康检查 ────────────────────────────────────

    @r.get("/health")
    async def health():
        return {"status": "ok", "version": "0.2.0"}

    # ── 账户 ────────────────────────────────────

    @r.post("/accounts", response_model=WalletAccountOut)
    async def create_account(
        user_id: str,
        tenant_id: str = "default",
    ) -> WalletAccountOut:
        """创建账户（幂等，三钱包）。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            acc = await get_or_create_account(s, user_id, tenant_id=tenant_id)
            await s.commit()
            return WalletAccountOut(
                user_id=acc.user_id,
                tenant_id=acc.tenant_id,
                recharge_balance_cents=acc.recharge_balance_cents,
                income_balance_cents=acc.income_balance_cents,
                skin_balance_cents=acc.skin_balance_cents,
                frozen_cents=acc.frozen_cents,
                status=acc.status,
                updated_at=acc.updated_at,
            )

    @r.get("/accounts/{user_id}", response_model=WalletAccountOut)
    async def get_account(
        user_id: str,
        tenant_id: str = "default",
    ) -> WalletAccountOut:
        """余额查询（三钱包）。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            try:
                bal = await get_three_balances(s, user_id)
                return WalletAccountOut(
                    user_id=bal.user_id,
                    tenant_id=tenant_id,
                    recharge_balance_cents=bal.recharge_balance_cents,
                    income_balance_cents=bal.income_balance_cents,
                    skin_balance_cents=bal.skin_balance_cents,
                    frozen_cents=bal.frozen_cents,
                    status="active",
                    updated_at=None,
                )
            except ValueError:
                raise HTTPException(404, "Account not found")

    @r.get("/accounts/{user_id}/balances", response_model=WalletAccountOut)
    async def get_balances(
        user_id: str,
        tenant_id: str = "default",
    ) -> WalletAccountOut:
        """三钱包余额查询（G7 端点）。"""
        return await get_account(user_id, tenant_id)

    @r.post("/accounts/{user_id}/freeze")
    async def freeze(
        user_id: str,
        req: FreezeRequest,
        tenant_id: str = "default",
    ) -> Dict[str, Any]:
        """冻结余额（G8）。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            try:
                res = await freeze_balance(s, user_id, req.amount_cents, reason=req.reason, tenant_id=tenant_id)
                await s.commit()
                return {"user_id": user_id, "frozen_cents": req.amount_cents, "version": res.version}
            except InsufficientBalanceError as e:
                raise HTTPException(402, detail={"code": "INSUFFICIENT_BALANCE", "balance_cents": e.balance_cents})

    @r.post("/accounts/{user_id}/unfreeze")
    async def unfreeze(
        user_id: str,
        req: FreezeRequest,
        tenant_id: str = "default",
    ) -> Dict[str, Any]:
        """解冻余额（G8）。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            try:
                res = await unfreeze_balance(s, user_id, req.amount_cents, reason=req.reason, tenant_id=tenant_id)
                await s.commit()
                return {"user_id": user_id, "unfrozen_cents": req.amount_cents, "version": res.version}
            except ValueError as e:
                raise HTTPException(400, str(e))

    # ── 充值 ────────────────────────────────────

    @r.post("/recharges", response_model=RechargeOut)
    async def create_recharge_order(
        req: RechargeCreate,
        tenant_id: str = "default",
    ) -> RechargeOut:
        """创建充值单。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            await get_or_create_account(s, req.user_id, tenant_id=tenant_id)
            res = await create_recharge(s, req.user_id, req.amount_cents, req.channel, tenant_id=tenant_id)
            await s.commit()
            return res

    @r.post("/recharges/notify/wechat")
    async def wechat_notify(
        request: Request,
        tenant_id: str = "default",
    ) -> Dict[str, str]:
        """微信支付回调（G11 异步队列 + C5）。"""
        body = (await request.body()).decode("utf-8")
        headers = dict(request.headers)

        # 落库（RawCallback）
        from core.database.session import session_scope
        async with session_scope() as s:
            raw = RawCallback(
                channel="wechat",
                event_type="payment",
                raw_body=body,
                headers=json.dumps(headers),
                status="pending",
            )
            s.add(raw)
            await s.commit()
            await s.refresh(raw)

        # 异步队列消费（防御：未启动则启动）
        if _callback_queue is None:
            await start_callback_worker()
        await _callback_queue.put(raw)
        return {"code": "SUCCESS", "message": "OK"}

    @r.post("/recharges/notify/alipay")
    async def alipay_notify(
        request: Request,
        tenant_id: str = "default",
    ) -> Dict[str, str]:
        """支付宝异步通知（C4 + G11 异步队列）。"""
        body = (await request.body()).decode("utf-8")
        headers = dict(request.headers)

        from core.database.session import session_scope
        async with session_scope() as s:
            raw = RawCallback(
                channel="alipay",
                event_type="payment",
                raw_body=body,
                headers=json.dumps(headers),
                status="pending",
            )
            s.add(raw)
            await s.commit()
            await s.refresh(raw)

        if _callback_queue is None:
            await start_callback_worker()
        await _callback_queue.put(raw)
        return {"code": "SUCCESS", "message": "OK"}

    @r.get("/recharges/{order_no}")
    async def get_order(
        order_no: str,
        tenant_id: str = "default",
    ) -> Dict[str, Any]:
        """充值单状态查询。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            order = await get_recharge_order(s, order_no)
            if order is None:
                raise HTTPException(404, "Order not found")
            return {
                "order_no": order.order_no,
                "amount_cents": order.amount_cents,
                "channel": order.channel,
                "status": order.status,
            }

    @r.get("/recharges/query/{order_no}")
    async def query_order(
        order_no: str,
        tenant_id: str = "default",
    ) -> Dict[str, Any]:
        """主动查单兜底（G1 端点）。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            order = await get_recharge_order(s, order_no)
            if order is None:
                raise HTTPException(404, "Order not found")
            # 调真实查单（微信/支付宝）
            try:
                if order.channel == "wechat":
                    from plugins.ddw_wallet.services.wechat_pay import query_order as wx_query
                    wx = await wx_query(order_no)
                    return {"order_no": order_no, "local_status": order.status, "provider_status": wx.get("trade_state", "")}
                elif order.channel == "alipay":
                    from plugins.ddw_wallet.services.alipay_client import query_order as ali_query
                    ali = ali_query(order_no)
                    return {"order_no": order_no, "local_status": order.status, "provider_status": ali.get("trade_status", "")}
            except Exception as exc:  # noqa: BLE001
                return {"order_no": order_no, "local_status": order.status, "provider_status": "QUERY_FAILED", "error": str(exc)[:200]}
            return {"order_no": order_no, "local_status": order.status}

    # ── 扣费 ────────────────────────────────────

    @r.post("/charges", response_model=ChargeOut)
    async def create_charge(
        req: ChargeCreate,
        tenant_id: str = "default",
    ) -> ChargeOut:
        """按量扣费（幂等）。"""
        from core.database.session import session_scope

        try:
            async with session_scope() as s:
                res = await charge(s, req.user_id, req.charge_type, req.subject, req.ref_id, req.ref_type, req.amount_cents, tenant_id=tenant_id)
                await s.commit()
                return res
        except InsufficientBalanceError as e:
            raise HTTPException(402, detail={"code": "INSUFFICIENT_BALANCE", "balance_cents": e.balance_cents})

    @r.post("/charges/fallback", response_model=ChargeOut)
    async def create_charge_fallback(
        req: ChargeCreate,
        tenant_id: str = "default",
    ) -> ChargeOut:
        """混合扣费（recharge→income→skin，G4）。"""
        from core.database.session import session_scope

        priority = tuple((req.balance_priority or "recharge,income,skin").split(","))
        try:
            async with session_scope() as s:
                res = await charge_with_fallback(
                    s, req.user_id, req.amount_cents, req.ref_id, req.charge_type,
                    tenant_id=tenant_id, subject=req.subject, ref_type=req.ref_type,
                    priority=priority,
                )
                await s.commit()
                return res
        except InsufficientBalanceError as e:
            raise HTTPException(402, detail={"code": "INSUFFICIENT_BALANCE", "balance_cents": e.balance_cents})

    # ── 退款 ────────────────────────────────────

    @r.post("/refunds", response_model=RefundOut)
    async def create_refund(
        req: RefundCreate,
        tenant_id: str = "default",
    ) -> RefundOut:
        """余额退款（真实调用，G2）。"""
        from core.database.session import session_scope

        try:
            async with session_scope() as s:
                res = await refund_balance(s, req.user_id, req.amount_cents, source=req.source, tenant_id=tenant_id)
                await s.commit()
                return res
        except ValueError as e:
            raise HTTPException(400, str(e))

    @r.post("/refunds/notify/wechat")
    async def refund_notify_wechat(request: Request) -> Dict[str, str]:
        """微信退款结果回调（G2）。"""
        body = (await request.body()).decode("utf-8")
        headers = dict(request.headers)

        from core.database.session import session_scope
        async with session_scope() as s:
            from plugins.ddw_wallet.services.wechat_pay import decrypt_notify
            try:
                data = decrypt_notify(headers, body)
                refund_no = data.get("out_refund_no", "")
                status = "success" if data.get("refund_status") == "SUCCESS" else "failed"
                ok = await handle_refund_notify(s, refund_no, data.get("refund_id", ""), status)
                await s.commit()
                return {"code": "SUCCESS" if ok else "FAIL"}
            except Exception as exc:  # noqa: BLE001
                logger.warning("Wechat refund notify failed: %s", exc)
                return {"code": "FAIL", "message": str(exc)[:200]}

    @r.post("/refunds/notify/alipay")
    async def refund_notify_alipay(request: Request) -> Dict[str, str]:
        """支付宝退款结果回调（G2）。"""
        _ = (await request.body()).decode("utf-8")
        params = dict(request.query_params)

        from core.database.session import session_scope
        async with session_scope() as s:
            from plugins.ddw_wallet.services.alipay_client import verify_notify as ali_verify
            try:
                if not ali_verify(params, params.get("sign", "")):
                    return {"code": "FAIL", "message": "验签失败"}
                refund_no = params.get("out_request_no", "")
                status = "success" if params.get("fund_change") == "Y" else "failed"
                ok = await handle_refund_notify(s, refund_no, params.get("trade_no", ""), status)
                await s.commit()
                return {"code": "SUCCESS" if ok else "FAIL"}
            except Exception as exc:  # noqa: BLE001
                logger.warning("Alipay refund notify failed: %s", exc)
                return {"code": "FAIL", "message": str(exc)[:200]}

    # ── 分成 ────────────────────────────────────

    @r.post("/royalties", response_model=RoyaltyOut)
    async def create_royalty(
        req: RoyaltyCreate,
        tenant_id: str = "default",
    ) -> RoyaltyOut:
        """课件分成入账（幂等）。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            res = await settle_royalty(s, req.author_user_id, req.courseware_id, req.trigger_txn_id, req.study_amount_cents, req.subject, tenant_id=tenant_id)
            await s.commit()
            return res

    # ── 流水查询（C6: 强制 tenant_id 过滤）───────

    @r.get("/transactions", response_model=PaginatedTransactions)
    async def list_transactions(
        user_id: str,
        tenant_id: str = "default",
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=100),
    ) -> PaginatedTransactions:
        """流水查询（G7: 强制 tenant_id + user_id 过滤）。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            recharges = (await s.execute(
                select(RechargeOrder).where(
                    RechargeOrder.user_id == user_id,
                    RechargeOrder.tenant_id == tenant_id,
                    RechargeOrder.status == "paid",
                )
            )).scalars().all()

            charges_list = (await s.execute(
                select(ChargeRecord).where(
                    ChargeRecord.user_id == user_id,
                    ChargeRecord.tenant_id == tenant_id,
                )
            )).scalars().all()

            refunds = (await s.execute(
                select(RefundRecord).where(
                    RefundRecord.user_id == user_id,
                    RefundRecord.tenant_id == tenant_id,
                )
            )).scalars().all()

            royalties = (await s.execute(
                select(RoyaltyRecord).where(
                    RoyaltyRecord.author_user_id == user_id,
                    RoyaltyRecord.tenant_id == tenant_id,
                )
            )).scalars().all()

            items: List[TransactionOut] = []
            for r in recharges:
                items.append(TransactionOut(order_no=r.order_no, amount_cents=r.amount_cents, direction="in", channel=r.channel, created_at=r.created_at))
            for c in charges_list:
                items.append(TransactionOut(txn_no=c.txn_no, amount_cents=c.amount_cents, direction="out", channel="wallet", subject=c.subject, created_at=c.created_at))
            for rf in refunds:
                items.append(TransactionOut(txn_no=rf.refund_no, amount_cents=rf.amount_cents, direction="out", channel=rf.channel, created_at=rf.created_at))
            for ry in royalties:
                items.append(TransactionOut(txn_no=ry.royalty_no, amount_cents=ry.income_cents, direction="in", channel="royalty", subject=ry.courseware_id, created_at=ry.created_at))

            items.sort(key=lambda x: x.created_at, reverse=True)
            total = len(items)
            start = (page - 1) * size
            return PaginatedTransactions(items=items[start:start + size], total=total, page=page, size=size)

    # ── 对账（G6）────────────────────────────────

    @r.post("/reconcile")
    async def run_reconcile(
        req: ReconcileRequest,
        tenant_id: str = "default",
    ) -> Dict[str, Any]:
        """手动触发对账（G6）。"""
        from core.database.session import session_scope

        target_date = date.fromisoformat(req.date)
        async with session_scope() as s:
            report = await reconcile(s, target_date)
            return {
                "date": report.date,
                "local_total": report.local_total,
                "bill_total": report.bill_total,
                "diff_total": report.diff_total,
                "matched_count": report.matched_count,
                "mismatched_count": report.mismatched_count,
                "local_only_count": report.local_only_count,
                "bill_only_count": report.bill_only_count,
            }

    @r.get("/reconcile/report")
    async def reconcile_report(
        query_date: str = Query(default=None),
        tenant_id: str = "default",
    ) -> Dict[str, Any]:
        """最近一次对账报告（G6）。"""
        from core.database.session import session_scope

        from datetime import date
        target = date.fromisoformat(query_date) if query_date else date.today()
        async with session_scope() as s:
            report = await reconcile(s, target)
            return {
                "date": report.date,
                "local_total": report.local_total,
                "bill_total": report.bill_total,
                "diff_total": report.diff_total,
                "matched_count": report.matched_count,
                "mismatched_count": report.mismatched_count,
            }

    # ── 审计日志（G12）────────────────────────────

    @r.get("/audit-logs")
    async def list_audit_logs(
        user_id: str = Query(default=None),
        tenant_id: str = "default",
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=100),
    ) -> Dict[str, Any]:
        """审计日志查询（G12）。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
            if user_id:
                stmt = stmt.where(AuditLog.user_id == user_id)
            stmt = stmt.order_by(AuditLog.created_at.desc())
            result = await s.execute(stmt)
            logs = result.scalars().all()
            total = len(logs)
            start = (page - 1) * size
            return {
                "items": [
                    {
                        "id": log.id, "user_id": log.user_id, "operator": log.operator,
                        "action": log.action, "amount_cents": log.amount_cents,
                        "balance_before": log.balance_before, "balance_after": log.balance_after,
                        "reason": log.reason, "created_at": log.created_at.isoformat() if log.created_at else None,
                    }
                    for log in logs[start:start + size]
                ],
                "total": total, "page": page, "size": size,
            }

    # ── 提现（G15）────────────────────────────────

    @r.post("/withdraw", response_model=WithdrawOut)
    async def create_withdraw_endpoint(
        req: WithdrawCreate,
        tenant_id: str = "default",
    ) -> WithdrawOut:
        """提现申请（income 余额可提现，G15）。"""
        from core.database.session import session_scope

        try:
            async with session_scope() as s:
                rec = await create_withdraw(s, req.user_id, req.amount_cents, channel=req.channel, tenant_id=tenant_id)
                await s.commit()
                return WithdrawOut(withdraw_no=rec.withdraw_no, amount_cents=rec.amount_cents, status=rec.status)
        except InsufficientBalanceError as e:
            raise HTTPException(402, detail={"code": "INSUFFICIENT_BALANCE", "balance_cents": e.balance_cents})
        except ValueError as e:
            raise HTTPException(400, str(e))

    # ── 平台账户（G5/M3）────────────────────────

    @r.get("/platform/accounts", response_model=PlatformAccountOut)
    async def get_platform_accounts(
        tenant_id: str = "default",
    ) -> PlatformAccountOut:
        """平台账户余额（G5 汇总 charge_records type=platform_fee）。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            result = await s.execute(
                select(
                    sa_func.coalesce(sa_func.sum(ChargeRecord.amount_cents), 0),
                    sa_func.count(ChargeRecord.id),
                ).where(
                    ChargeRecord.charge_type == "platform_fee",
                    ChargeRecord.tenant_id == tenant_id,
                )
            )
            row = result.one()
            return PlatformAccountOut(total_fee_cents=row[0], count=row[1])

    # ── 计费规则 ────────────────────────────────

    @r.get("/rates", response_model=List[RateRuleOut])
    async def list_rates() -> List[RateRuleOut]:
        """计费规则列表（管理端）。"""
        from core.database.session import session_scope

        async with session_scope() as s:
            rows = (await s.execute(select(RateRule).where(RateRule.active == True))).scalars().all()  # noqa: E712
            return [RateRuleOut(id=r.id, charge_type=r.charge_type, subject=r.subject, unit_price_cents=r.unit_price_cents, unit=r.unit, active=r.active) for r in rows]

    return r


__all__ = ["build_router"]
