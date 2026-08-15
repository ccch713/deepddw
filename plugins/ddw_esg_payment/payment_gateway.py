"""Payment gateway framework — stub implementations for WeChat Pay and Alipay.

安全说明（硬伤修复）：
- ``verify_webhook`` 不再恒 True：改为 HMAC-SHA256 签名校验，密钥来自环境变量
  ``DDW_ESG_PAYMENT_WEBHOOK_SECRET``；未配置密钥时拒绝所有回调（fail-secure，
  防止伪造支付成功回调）。
- ``create_payment`` / ``refund`` 仍为 demo 数据；对接微信/支付宝真实 SDK
  需要商户号与 API 凭证，属后续专项（TODO）。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import random
import string
from abc import ABC, abstractmethod
from datetime import datetime

from .models import Order

# Webhook 签名密钥环境变量（部署端注入；未配置 → 拒绝回调）
WEBHOOK_SECRET_ENV = "DDW_ESG_PAYMENT_WEBHOOK_SECRET"

# Webhook 签名方案：HMAC-SHA256(payload 原始字节)，hex 小写
WEBHOOK_SIGNATURE_SCHEME = "hmac-sha256-hex"


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """校验 webhook 回调签名（HMAC-SHA256，hex）。

    - 未配置 ``DDW_ESG_PAYMENT_WEBHOOK_SECRET`` → False（fail-secure）
    - signature 缺失或与预期不符 → False
    """
    secret = os.environ.get(WEBHOOK_SECRET_ENV, "").strip()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


class PaymentGateway(ABC):
    """Abstract payment gateway interface."""

    @abstractmethod
    async def create_payment(self, order: Order) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def verify_webhook(self, payload: bytes, signature: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def refund(self, order_id: str, amount: int) -> dict:
        raise NotImplementedError


class WechatPayGateway(PaymentGateway):
    async def create_payment(self, order: Order) -> dict:
        return {
            "prepay_id": "wx_demo_" + order.trade_no,
            "nonce_str": "".join(
                random.choices(string.ascii_letters, k=32)
            ),
            "timestamp": str(int(datetime.now().timestamp())),
            "sign_type": "RSA",
            "pay_sign": "demo_signature",
        }

    async def verify_webhook(self, payload: bytes, signature: str) -> bool:
        # 真实微信支付回调验签需商户 APIv3 证书，本地无法真验；
        # 采用可配置 HMAC 签名校验（DDW_ESG_PAYMENT_WEBHOOK_SECRET），
        # 未配置密钥一律拒绝（fail-secure），不再恒 True。
        return verify_webhook_signature(payload, signature)

    async def refund(self, order_id: str, amount: int) -> dict:
        return {"refund_id": "demo_refund_" + order_id}


class AlipayGateway(PaymentGateway):
    async def create_payment(self, order: Order) -> dict:
        return {
            "qr_code": f"https://qr.alipay.com/demo_{order.trade_no}",
            "trade_no": order.trade_no,
            "total_amount": f"{order.final_amount / 100:.2f}",
        }

    async def verify_webhook(self, payload: bytes, signature: str) -> bool:
        # 同 Wechat：可配置 HMAC 校验，未配置密钥拒绝回调（fail-secure）。
        return verify_webhook_signature(payload, signature)

    async def refund(self, order_id: str, amount: int) -> dict:
        return {"refund_id": "demo_refund_" + order_id}


# ---------------------------------------------------------------------------
# Gateway registry
# ---------------------------------------------------------------------------

_GATEWAYS: dict[str, PaymentGateway] = {
    "wechat": WechatPayGateway(),
    "alipay": AlipayGateway(),
}


def get_gateway(channel: str) -> PaymentGateway:
    gw = _GATEWAYS.get(channel)
    if not gw:
        raise ValueError(f"Unsupported payment channel: {channel}")
    return gw
