"""支付服务 — 支持支付宝/微信/对公转账"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 支付渠道枚举
PAYMENT_CHANNELS = ["alipay", "wechat", "bank_transfer"]


async def create_payment(channel: str, order_id: str, amount: int, subject: str = "") -> Dict[str, Any]:
    """创建支付订单（桩实现）。"""
    if channel == "alipay":
        return await _create_alipay(order_id, amount, subject)
    elif channel == "wechat":
        return await _create_wechat(order_id, amount, subject)
    elif channel == "bank_transfer":
        return await _create_bank_transfer(order_id, amount, subject)
    else:
        return {"error": f"unsupported channel: {channel}"}


async def _create_alipay(order_id: str, amount: int, subject: str) -> Dict[str, Any]:
    """支付宝当面付 / 扫码支付（桩）。"""
    return {
        "channel": "alipay",
        "order_id": order_id,
        "amount": amount,
        "status": "pending",
        "qr_code": f"https://qr.alipay.com/{order_id}",
        "pay_url": f"https://openapi.alipay.com/gateway.do?order={order_id}",
    }


async def _create_wechat(order_id: str, amount: int, subject: str) -> Dict[str, Any]:
    """微信支付 Native / JSAPI（桩）。"""
    return {
        "channel": "wechat",
        "order_id": order_id,
        "amount": amount,
        "status": "pending",
        "qr_code": f"weixin://pay/{order_id}",
        "prepay_id": f"wx_prepay_{order_id}",
    }


async def _create_bank_transfer(order_id: str, amount: int, subject: str) -> Dict[str, Any]:
    """对公账户转账 — 返回收款信息供用户自行转账。"""
    return {
        "channel": "bank_transfer",
        "order_id": order_id,
        "amount": amount,
        "status": "pending",
        "bank_info": {
            "account_name": "武汉锐果互动信息技术有限公司",
            "bank": "汉口银行雄楚大道支行",
            "account_no": "0050 1100 0103 723",
            "bank_code": "3135 2100 0907",
            "remark": f"转账时请备注：{order_id}",
        },
    }


async def verify_callback(channel: str, data: Dict[str, Any]) -> bool:
    """验证支付回调（桩实现）。"""
    logger.info("payment callback channel=%s", channel)
    return True


def get_payment_channels() -> list[Dict[str, Any]]:
    """返回支持的支付渠道列表（前端展示用）。"""
    return [
        {"id": "alipay", "name": "支付宝", "icon": "alipay", "enabled": True},
        {"id": "wechat", "name": "微信支付", "icon": "wechat", "enabled": True},
        {"id": "bank_transfer", "name": "对公转账", "icon": "bank", "enabled": True,
         "bank_info": {
             "account_name": "武汉锐果互动信息技术有限公司",
             "bank": "汉口银行雄楚大道支行",
             "account_no": "0050 1100 0103 723",
         }},
    ]
