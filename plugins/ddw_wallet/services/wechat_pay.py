"""微信支付 APIv3 客户端（官方 SDK 包装）。

密钥全部来自环境变量（config.py），禁止硬编码。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from plugins.ddw_wallet.config import settings

logger = logging.getLogger(__name__)

# 延迟导入 wechatpayv3（可能未安装）
_wx_client: Any = None


def get_client() -> Any:
    """获取微信支付客户端（懒初始化）。"""
    global _wx_client
    if _wx_client is not None:
        return _wx_client

    try:
        from wechatpayv3 import WeChatPay, WeChatPayType
    except ImportError:
        raise RuntimeError(
            "wechatpayv3 not installed. "
            "Run: pip install wechatpayv3"
        )

    key_path = settings.WECHAT_PRIVATE_KEY
    private_key = ""
    if key_path:
        try:
            with open(key_path) as f:
                private_key = f.read()
        except FileNotFoundError:
            logger.warning(
                "WeChat private key not found: %s", key_path
            )

    # 微信支付公钥模式（商户平台启用后回调验签必须，二者同有同无）
    extra = {}
    if settings.WECHAT_PUBLIC_KEY and settings.WECHAT_PUBLIC_KEY_ID:
        try:
            with open(settings.WECHAT_PUBLIC_KEY) as f:
                extra["public_key"] = f.read()
            extra["public_key_id"] = settings.WECHAT_PUBLIC_KEY_ID
        except FileNotFoundError:
            logger.warning(
                "WeChat public key not found: %s",
                settings.WECHAT_PUBLIC_KEY,
            )

    _wx_client = WeChatPay(
        wechatpay_type=WeChatPayType.NATIVE,
        mchid=settings.WECHAT_MCH_ID,
        private_key=private_key,
        cert_serial_no=settings.WECHAT_CERT_SERIAL_NO,
        apiv3_key=settings.WECHAT_API_V3_KEY,
        appid=settings.WECHAT_APP_ID,
        notify_url=settings.WECHAT_NOTIFY_URL,
        **extra,
    )
    return _wx_client


def create_native_order(
    order_no: str,
    amount_cents: int,
    description: str,
) -> str:
    """Native 下单，返回 code_url（二维码内容）。"""
    wx = get_client()
    code, message = wx.pay(
        description=description,
        out_trade_no=order_no,
        amount={"total": amount_cents},
        payer=None,
    )
    if code != 200:
        raise RuntimeError(
            f"Wechat native order failed: {code} {message}"
        )
    return json.loads(message)["code_url"]


def decrypt_notify(
    headers: dict, body: str
) -> dict:
    """回调：验签 + 解密，返回明文 resource 对象。"""
    wx = get_client()
    return wx.callback(headers=headers, body=body)


def create_refund(
    order_no: str,
    refund_no: str,
    total_cents: int,
    refund_cents: int,
) -> dict:
    """发起退款。"""
    wx = get_client()
    code, message = wx.refund(
        out_trade_no=order_no,
        out_refund_no=refund_no,
        amount={
            "refund": refund_cents,
            "total": total_cents,
            "currency": "CNY",
        },
    )
    if code != 200:
        raise RuntimeError(
            f"Wechat refund failed: {code} {message}"
        )
    return json.loads(message)


# ── Mock 客户端（测试用） ─────────────────────────


class MockWeChatClient:
    """模拟微信支付客户端，不发起真实网络请求。"""

    def __init__(self) -> None:
        self.orders: Dict[str, dict] = {}
        self.refunds: Dict[str, dict] = {}

    def pay(
        self,
        description: str,
        out_trade_no: str,
        amount: dict,
        payer: Any = None,
    ) -> dict:
        self.orders[out_trade_no] = {
            "out_trade_no": out_trade_no,
            "amount": amount,
            "description": description,
        }
        return {
            "code_url": f"weixin://wxpay/mock_{out_trade_no}"
        }

    def callback(
        self, headers: dict, body: str
    ) -> dict:
        """模拟验签+解密，直接返回 body 的 JSON。"""
        return json.loads(body)

    def refund(
        self,
        out_trade_no: str,
        out_refund_no: str,
        amount: dict,
    ) -> dict:
        self.refunds[out_refund_no] = {
            "out_trade_no": out_trade_no,
            "out_refund_no": out_refund_no,
            "amount": amount,
        }
        return {"status": "PROCESSING"}


_mock_client: Optional[MockWeChatClient] = None


def get_mock_client() -> MockWeChatClient:
    """获取 mock 客户端（测试用）。"""
    global _mock_client
    if _mock_client is None:
        _mock_client = MockWeChatClient()
    return _mock_client


def reset_mock() -> None:
    """重置 mock 状态。"""
    global _mock_client, _wx_client
    _mock_client = None
    _wx_client = None


__all__ = [
    "MockWeChatClient",
    "create_native_order",
    "create_refund",
    "decrypt_notify",
    "get_client",
    "get_mock_client",
    "reset_mock",
]
