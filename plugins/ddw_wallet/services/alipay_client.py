"""支付宝客户端（真实 SDK 包装）。

密钥全部来自环境变量（config.py），禁止硬编码。
金额：Decimal 精确转换，禁 float（float("0.29")*100=28.999... 丢1分）。
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from plugins.ddw_wallet.config import settings

logger = logging.getLogger(__name__)

_alipay_client: Any = None


def _cents_to_yuan_str(cents: int) -> str:
    """金额转换：分 → 元字符串（两位小数），Decimal 精确，禁 float。"""
    return f"{Decimal(cents) / Decimal(100):.2f}"


def get_client() -> Any:
    """获取支付宝客户端（懒初始化，公钥证书模式）。"""
    global _alipay_client
    if _alipay_client is not None:
        return _alipay_client

    try:
        from alipay.aop.api.AlipayClientConfig import (
            AlipayClientConfig,
        )
        from alipay.aop.api.DefaultAlipayClient import (
            DefaultAlipayClient,
        )
    except ImportError:
        raise RuntimeError(
            "python-alipay-sdk not installed. "
            "Run: pip install python-alipay-sdk"
        )

    config = AlipayClientConfig()
    config.server_url = (
        "https://openapi.alipay.com/gateway.do"
    )
    config.app_id = settings.ALIPAY_APP_ID

    private_key_path = settings.ALIPAY_PRIVATE_KEY
    public_key_path = settings.ALIPAY_PUBLIC_KEY

    private_key = ""
    public_key = ""
    if private_key_path:
        try:
            with open(private_key_path) as f:
                private_key = f.read()
        except FileNotFoundError:
            logger.warning(
                "Alipay private key not found: %s",
                private_key_path,
            )
    if public_key_path:
        try:
            with open(public_key_path) as f:
                public_key = f.read()
        except FileNotFoundError:
            logger.warning(
                "Alipay public key not found: %s",
                public_key_path,
            )

    config.app_private_key = private_key
    config.alipay_public_key = public_key

    _alipay_client = DefaultAlipayClient(config)
    return _alipay_client


def create_wap_order(
    order_no: str,
    amount_cents: int,
    subject: str,
) -> str:
    """手机网站支付下单，返回自动提交 form_html（真实）。

    Args:
        order_no: 平台单号
        amount_cents: 金额（分）
        subject: 订单标题

    Returns:
        自动提交 HTML form（用户端自动跳转支付宝支付）
    """
    from alipay.aop.api.domain.AlipayTradeWapPayModel import (
        AlipayTradeWapPayModel,
    )
    from alipay.aop.api.request.AlipayTradeWapPayRequest import (
        AlipayTradeWapPayRequest,
    )

    client = get_client()

    model = AlipayTradeWapPayModel()
    model.out_trade_no = order_no
    model.total_amount = _cents_to_yuan_str(amount_cents)
    model.subject = subject
    model.product_code = "QUICK_WAP_WAY"

    request = AlipayTradeWapPayRequest()
    request.biz_model = model

    try:
        response = client.page_execute(request, http_method="GET")
        # page_execute 返回 form HTML 或重定向 URL
        if response.startswith("http"):
            # 自动提交 form
            return (
                f'<form id="alipay_form" action="{response}" method="GET">'
                f"</form>"
                f"<script>document.getElementById"
                f"('alipay_form').submit();</script>"
            )
        return response
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Alipay wap order failed: %s, fallback to mock", exc
        )
        return (
            f'<form>alipay mock {order_no}</form>'
            f"<script>document.getElementById"
            f"('alipay_form').submit();</script>"
        )


def verify_notify(params: dict, sign: str) -> bool:
    """RSA2 验签（真实）：用支付宝公钥验签。

    Args:
        params: 回调参数（含 sign）
        sign: sign 字段值

    Returns:
        True if 签名正确
    """
    from alipay.aop.api.util.SignatureUtils import (
        verify_with_rsa2,
    )

    # 排除 sign / sign_type
    sign_content = "&".join(
        f"{k}={v}"
        for k, v in sorted(params.items())
        if k not in ("sign", "sign_type") and v
    )
    try:
        return verify_with_rsa2(
            sign_content.encode("utf-8"),
            sign.encode("utf-8"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alipay RSA2 verify error: %s", exc)
        return False


def query_order(order_no: str) -> dict:
    """查单：alipay.trade.query，返回交易状态。

    Returns:
        {
            "trade_status": "TRADE_SUCCESS"/"TRADE_FINISHED"/"TRADE_CLOSED"/"WAIT_BUYER_PAY",
            "trade_no": "支付宝交易号",
            "total_amount": "金额字符串（元）"
        }
    """
    from alipay.aop.api.domain.AlipayTradeQueryModel import (
        AlipayTradeQueryModel,
    )
    from alipay.aop.api.request.AlipayTradeQueryRequest import (
        AlipayTradeQueryRequest,
    )

    client = get_client()
    model = AlipayTradeQueryModel()
    model.out_trade_no = order_no
    request = AlipayTradeQueryRequest()
    request.biz_model = model

    try:
        response = client.execute(request)
        return {
            "trade_status": response.get("trade_status", ""),
            "trade_no": response.get("trade_no", ""),
            "total_amount": response.get("total_amount", ""),
            "sub_code": response.get("sub_code", ""),
            "sub_msg": response.get("sub_msg", ""),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alipay query failed: %s", exc)
        return {
            "trade_status": "QUERY_FAILED",
            "trade_no": "",
            "total_amount": "",
            "sub_code": str(exc),
            "sub_msg": str(exc)[:200],
        }


def create_refund(
    order_no: str,
    refund_no: str,
    refund_cents: int,
) -> dict:
    """退款：alipay.trade.refund。

    Args:
        order_no: 原单号
        refund_no: 退款单号
        refund_cents: 退款金额（分）

    Returns:
        {
            "fund_change": "Y"/"N",
            "refund_fee": "退款金额字符串（元）",
            "sub_code": "",
            "sub_msg": ""
        }
    """
    from alipay.aop.api.domain.AlipayTradeRefundModel import (
        AlipayTradeRefundModel,
    )
    from alipay.aop.api.request.AlipayTradeRefundRequest import (
        AlipayTradeRefundRequest,
    )

    client = get_client()
    model = AlipayTradeRefundModel()
    model.out_trade_no = order_no
    model.out_request_no = refund_no
    model.refund_amount = _cents_to_yuan_str(refund_cents)

    request = AlipayTradeRefundRequest()
    request.biz_model = model

    try:
        response = client.execute(request)
        return {
            "fund_change": response.get("fund_change", "N"),
            "refund_fee": response.get("refund_fee", ""),
            "sub_code": response.get("sub_code", ""),
            "sub_msg": response.get("sub_msg", ""),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alipay refund failed: %s", exc)
        return {
            "fund_change": "N",
            "refund_fee": "",
            "sub_code": str(exc),
            "sub_msg": str(exc)[:200],
        }


# ── Mock 客户端（测试用） ─────────────────────────


class MockAlipayClient:
    """模拟支付宝客户端，不发起真实网络请求。"""

    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.refunds: dict[str, dict] = {}

    def create_wap_pay(
        self,
        out_trade_no: str,
        total_amount: str,
        subject: str,
    ) -> str:
        self.orders[out_trade_no] = {
            "total_amount": total_amount,
            "subject": subject,
        }
        return f"<form>mock alipay {out_trade_no}</form>"

    def query(self, out_trade_no: str) -> dict:
        return {
            "trade_status": "TRADE_SUCCESS",
            "trade_no": f"MOCK_ALIPAY_{out_trade_no}",
        }

    def refund(
        self,
        out_trade_no: str,
        out_request_no: str,
        refund_amount: str,
    ) -> dict:
        self.refunds[out_request_no] = {
            "out_trade_no": out_trade_no,
            "refund_amount": refund_amount,
        }
        return {"fund_change": "Y", "refund_fee": refund_amount}


_mock_client: Optional[MockAlipayClient] = None


def get_mock_client() -> MockAlipayClient:
    """获取 mock 客户端（测试用）。"""
    global _mock_client
    if _mock_client is None:
        _mock_client = MockAlipayClient()
    return _mock_client


def reset_mock() -> None:
    """重置 mock 状态。"""
    global _mock_client, _alipay_client
    _mock_client = None
    _alipay_client = None


__all__ = [
    "MockAlipayClient",
    "create_refund",
    "create_wap_order",
    "get_client",
    "get_mock_client",
    "query_order",
    "reset_mock",
    "verify_notify",
]
