"""计费 API 路由 — 支持支付宝/微信/对公转账"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_saas_billing.models import Subscription, UsageLog
from plugins.ddw_saas_billing.services.payment_service import (
    PAYMENT_CHANNELS,
    create_payment,
    get_payment_channels,
)


class SubReq(BaseModel):
    tenant_id: int
    plan_name: str = "free"
    monthly_limit: int = 1000

class PayReq(BaseModel):
    channel: str  # alipay / wechat / bank_transfer
    order_id: str
    amount: int
    subject: str = ""

async def list_subscriptions(tenant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    async with session_scope() as s, bypass_tenant_filter():
        q = select(Subscription)
        if tenant_id:
            q = q.where(Subscription.tenant_id == tenant_id)
        rows = (await s.execute(q)).scalars().all()
    return [{"id": r.id, "tenant_id": r.tenant_id, "plan": r.plan_name, "status": r.status, "used": r.used, "limit": r.monthly_limit} for r in rows]

async def create_subscription(req: SubReq) -> Dict[str, Any]:
    async with session_scope() as s, bypass_tenant_filter():
        sub = Subscription(tenant_id=req.tenant_id, plan_name=req.plan_name, monthly_limit=req.monthly_limit)
        s.add(sub)
        await s.commit()
        await s.refresh(sub)
    return {"id": sub.id, "plan": sub.plan_name}

async def usage(tenant_id: int) -> Dict[str, Any]:
    async with session_scope() as s, bypass_tenant_filter():
        rows = (await s.execute(select(UsageLog).where(UsageLog.tenant_id == tenant_id))).scalars().all()
    total = sum(r.tokens_used for r in rows)
    return {"tenant_id": tenant_id, "total_tokens": total, "events": len(rows)}

async def create_pay_order(req: PayReq) -> Dict[str, Any]:
    """创建支付订单 — 用户选择支付渠道。"""
    if req.channel not in PAYMENT_CHANNELS:
        return {"error": f"unsupported channel: {req.channel}, supported: {PAYMENT_CHANNELS}"}
    return await create_payment(req.channel, req.order_id, req.amount, req.subject)

async def payment_channels() -> List[Dict[str, Any]]:
    """返回支持的支付渠道列表。"""
    return get_payment_channels()

async def alipay_callback() -> Dict[str, Any]:
    return {"status": "ok", "message": "alipay callback received"}

async def wechat_callback() -> Dict[str, Any]:
    return {"status": "ok", "message": "wechat callback received"}

def build_router(plugin) -> APIRouter:
    r = APIRouter(prefix=plugin.router_prefix, tags=[plugin.name])
    r.add_api_route("/subscriptions", list_subscriptions, methods=["GET"])
    r.add_api_route("/subscriptions", create_subscription, methods=["POST"])
    r.add_api_route("/usage/{tenant_id}", usage, methods=["GET"])
    r.add_api_route("/payment/channels", payment_channels, methods=["GET"])
    r.add_api_route("/payment/create", create_pay_order, methods=["POST"])
    r.add_api_route("/webhook/alipay", alipay_callback, methods=["POST"])
    r.add_api_route("/webhook/wechat", wechat_callback, methods=["POST"])
    return r
