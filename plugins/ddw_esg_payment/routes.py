"""API endpoints for ESG payment plugin."""
from __future__ import annotations

import random
import string
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request

from .models import (
    Attribution,
    Commission,
    CommissionResponse,
    Coupon,
    CouponResponse,
    Order,
    OrderCreate,
    OrderResponse,
    Payment,
    PromoCodeCreate,
    PromoCodeResponse,
    Promotion,
    Withdrawal,
    WithdrawalCreate,
    WithdrawalResponse,
)
from .payment_gateway import get_gateway
from .promo import (
    PLANS,
    PROMO_CONFIG,
    compute_order_amounts,
    generate_promo_code,
)

# In-memory store for demo/testing (replaced by DB in production)
_ORDERS: dict[str, Order] = {}
_PAYMENTS: dict[str, Payment] = {}
_PROMOTIONS: dict[str, Promotion] = {}
_ATTRIBUTIONS: dict[str, Attribution] = {}
_COMMISSIONS: dict[str, Commission] = {}
_COUPONS: dict[str, Coupon] = {}
_WITHDRAWALS: dict[str, Withdrawal] = {}


def _make_trade_no() -> str:
    return "DDW" + datetime.now().strftime("%Y%m%d%H%M%S") + "".join(
        random.choices(string.digits, k=6)
    )


def _grant_welcome_coupon(user_id: str) -> None:
    """Grant a welcome coupon if user doesn't have one."""
    for c in _COUPONS.values():
        if c.user_id == user_id and c.code == "WELCOME":
            return
    now = datetime.now()
    coupon = Coupon(
        id=str(uuid.uuid4()),
        user_id=user_id,
        code="WELCOME",
        amount=PROMO_CONFIG["coupon_amounts"]["welcome"],
        min_order_amount=0,
        valid_from=now,
        valid_to=now + timedelta(days=PROMO_CONFIG["coupon_validity_days"]),
        status="active",
    )
    _COUPONS[coupon.id] = coupon


def register_routes(router: APIRouter) -> None:
    """Register all endpoint handlers on the given router.

    Called from __init__.py after the shared router is created.
    """

    @router.get("/health")
    async def health_check():
        return {"status": "ok", "plugin": "ddw-esg-payment"}

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    @router.post("/orders", response_model=OrderResponse)
    async def create_order(body: OrderCreate):
        plan = PLANS.get(body.plan_id)
        if not plan:
            raise HTTPException(400, f"Unknown plan: {body.plan_id}")

        promo_obj = None
        if body.promo_code:
            promo_obj = _PROMOTIONS.get(body.promo_code)
            if not promo_obj:
                raise HTTPException(400, "Invalid promo code")

        coupon_amount = 0
        if body.coupon_id:
            coupon = _COUPONS.get(body.coupon_id)
            if not coupon or coupon.user_id != body.user_id or coupon.status != "active":
                raise HTTPException(400, "Invalid coupon")
            coupon_amount = coupon.amount

        amounts = compute_order_amounts(body.plan_id, promo_obj, coupon_amount)

        now = datetime.now()
        order = Order(
            id=str(uuid.uuid4()),
            user_id=body.user_id,
            plan_id=body.plan_id,
            trade_no=_make_trade_no(),
            promo_code=body.promo_code,
            coupon_id=body.coupon_id,
            assessment_id=body.assessment_id,
            pay_method=body.pay_method,
            metadata_=body.metadata,
            currency="CNY",
            status="pending",
            created_at=now,
            updated_at=now,
            **amounts,
        )
        _ORDERS[order.id] = order

        # Grant welcome coupon for new users
        _grant_welcome_coupon(body.user_id)

        return order

    @router.get("/orders", response_model=list[OrderResponse])
    async def list_orders(user_id: str = Query(...)):
        return [o for o in _ORDERS.values() if o.user_id == user_id]

    @router.get("/orders/admin/all", response_model=list[OrderResponse])
    async def admin_list_orders():
        return list(_ORDERS.values())

    @router.get("/orders/{order_id}", response_model=OrderResponse)
    async def get_order(order_id: str):
        order = _ORDERS.get(order_id)
        if not order:
            raise HTTPException(404, "Order not found")
        return order

    @router.post("/orders/{order_id}/pay")
    async def initiate_payment(order_id: str):
        order = _ORDERS.get(order_id)
        if not order:
            raise HTTPException(404, "Order not found")
        if order.status != "pending":
            raise HTTPException(400, f"Order status is {order.status}")
        if not order.pay_method:
            raise HTTPException(400, "pay_method required")
        return {"order_id": order.id, "pay_method": order.pay_method, "amount": order.final_amount}

    @router.post("/orders/{order_id}/cancel")
    async def cancel_order(order_id: str):
        order = _ORDERS.get(order_id)
        if not order:
            raise HTTPException(404, "Order not found")
        if order.status != "pending":
            raise HTTPException(400, f"Cannot cancel order in status {order.status}")
        order.status = "cancelled"
        return {"order_id": order.id, "status": "cancelled"}

    # ------------------------------------------------------------------
    # Payment endpoints
    # ------------------------------------------------------------------

    @router.post("/pay/wechat/create")
    async def create_wechat_payment(order_id: str = Query(...)):
        order = _ORDERS.get(order_id)
        if not order:
            raise HTTPException(404, "Order not found")
        gw = get_gateway("wechat")
        result = await gw.create_payment(order)
        return result

    @router.post("/pay/alipay/create")
    async def create_alipay_payment(order_id: str = Query(...)):
        order = _ORDERS.get(order_id)
        if not order:
            raise HTTPException(404, "Order not found")
        gw = get_gateway("alipay")
        result = await gw.create_payment(order)
        return result

    @router.get("/pay/{order_id}/status")
    async def payment_status(order_id: str):
        order = _ORDERS.get(order_id)
        if not order:
            raise HTTPException(404, "Order not found")
        return {"order_id": order.id, "status": order.status}

    # ------------------------------------------------------------------
    # Promo
    # ------------------------------------------------------------------

    @router.post("/promo/codes", response_model=PromoCodeResponse)
    async def create_promo_code(body: PromoCodeCreate):
        code = generate_promo_code(body.prefix)
        now = datetime.now()
        promo = Promotion(
            code=code,
            promoter_id=body.promoter_id,
            promo_type=body.promo_type,
            prefix=body.prefix,
            valid_from=now,
            valid_to=now + timedelta(days=365),
        )
        _PROMOTIONS[code] = promo
        return promo

    @router.get("/promo/codes/my", response_model=list[PromoCodeResponse])
    async def my_promo_codes(promoter_id: str = Query(...)):
        return [p for p in _PROMOTIONS.values() if p.promoter_id == promoter_id]

    @router.get("/promo/codes/{code}/stats")
    async def promo_code_stats(code: str):
        promo = _PROMOTIONS.get(code)
        if not promo:
            raise HTTPException(404, "Promo code not found")
        return {
            "code": promo.code,
            "click_count": promo.click_count,
            "register_count": promo.register_count,
            "pay_count": promo.pay_count,
            "total_commission": promo.total_commission,
        }

    @router.get("/promo/redirect/{code}")
    async def promo_redirect(code: str):
        promo = _PROMOTIONS.get(code)
        if not promo:
            raise HTTPException(404, "Invalid promo code")
        promo.click_count += 1
        return {"redirect_url": f"/?ref={code}", "code": code}

    @router.post("/promo/track/click")
    async def track_click(code: str = Query(...)):
        promo = _PROMOTIONS.get(code)
        if not promo:
            raise HTTPException(404, "Promo code not found")
        promo.click_count += 1
        return {"code": code, "click_count": promo.click_count}

    # ------------------------------------------------------------------
    # Commission
    # ------------------------------------------------------------------

    @router.get("/commission/my", response_model=list[CommissionResponse])
    async def my_commissions(promoter_id: str = Query(...)):
        return [c for c in _COMMISSIONS.values() if c.promoter_id == promoter_id]

    @router.get("/commission/my/summary")
    async def commission_summary(promoter_id: str = Query(...)):
        my = [c for c in _COMMISSIONS.values() if c.promoter_id == promoter_id]
        total = sum(c.amount for c in my)
        confirmed = sum(c.amount for c in my if c.status == "confirmed")
        pending = sum(c.amount for c in my if c.status == "pending")
        paid = sum(c.amount for c in my if c.status == "paid")
        return {
            "total_commission_cents": total,
            "confirmed_cents": confirmed,
            "pending_cents": pending,
            "paid_cents": paid,
            "count": len(my),
        }

    @router.post("/commission/withdraw", response_model=WithdrawalResponse)
    async def request_withdrawal(body: WithdrawalCreate):
        if body.amount < PROMO_CONFIG["withdrawal_min_cents"]:
            raise HTTPException(400, "Below minimum withdrawal amount")
        if body.amount > PROMO_CONFIG["withdrawal_max_cents"]:
            raise HTTPException(400, "Exceeds maximum withdrawal amount")
        w = Withdrawal(
            id=str(uuid.uuid4()),
            user_id=body.user_id,
            amount=body.amount,
            bank_info=body.bank_info,
        )
        _WITHDRAWALS[w.id] = w
        return w

    @router.get("/commission/withdrawals", response_model=list[WithdrawalResponse])
    async def withdrawal_history(user_id: str = Query(...)):
        return [w for w in _WITHDRAWALS.values() if w.user_id == user_id]

    # ------------------------------------------------------------------
    # Coupons
    # ------------------------------------------------------------------

    @router.get("/coupons/my", response_model=list[CouponResponse])
    async def my_coupons(user_id: str = Query(...)):
        now = datetime.now()
        result = []
        for c in _COUPONS.values():
            if c.user_id == user_id:
                if c.status == "active" and c.valid_to >= now:
                    result.append(c)
                elif c.status == "active" and c.valid_to < now:
                    c.status = "expired"
        return result

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    @router.post("/webhook/wechat")
    async def wechat_webhook(request: Request):
        body = await request.body()
        gw = get_gateway("wechat")
        valid = await gw.verify_webhook(body, request.headers.get("signature", ""))
        if not valid:
            raise HTTPException(
                401,
                "Webhook 签名校验失败（DDW_ESG_PAYMENT_WEBHOOK_SECRET 未配置"
                "或签名不匹配），回调被拒绝",
            )
        return {"status": "ok"}

    @router.post("/webhook/alipay")
    async def alipay_webhook(request: Request):
        body = await request.body()
        gw = get_gateway("alipay")
        valid = await gw.verify_webhook(body, request.headers.get("signature", ""))
        if not valid:
            raise HTTPException(
                401,
                "Webhook 签名校验失败（DDW_ESG_PAYMENT_WEBHOOK_SECRET 未配置"
                "或签名不匹配），回调被拒绝",
            )
        return {"status": "ok"}
