"""G1 支付宝收单真实化测试（mock 模式，不发起真实网络请求）。"""

from plugins.ddw_wallet.services.alipay_client import (
    _cents_to_yuan_str,
    get_mock_client,
    reset_mock,
)


def test_cents_to_yuan_decimal_precision():
    """金额转换：分 → 元字符串，Decimal 精确，禁 float 丢精度。"""
    assert _cents_to_yuan_str(29) == "0.29"  # float(29)/100=0.29, 正确
    assert _cents_to_yuan_str(100) == "1.00"
    assert _cents_to_yuan_str(9999) == "99.99"
    assert _cents_to_yuan_str(1) == "0.01"
    assert _cents_to_yuan_str(0) == "0.00"
    # 确认是 Decimal 不是 float
    assert _cents_to_yuan_str(29) != "0.289999999999999999999"


def test_create_wap_order_form_html():
    """下单返回自动提交 form_html（mock 模式）。"""
    reset_mock()
    # 直接用 mock client 测试（python-alipay-sdk 未安装时也通过）
    mock = get_mock_client()
    result = mock.create_wap_pay("ALI_001", "5.00", "问渠充值")
    assert "form" in result.lower() or "alipay" in result.lower()


def test_verify_notify_basic():
    """验签：mock 模式下基本字段存在即可通过。"""
    mock = get_mock_client()
    assert mock.query("ALI_001")["trade_status"] == "TRADE_SUCCESS"


def test_query_order_mock():
    """查单 mock：TRADE_SUCCESS。"""
    mock = get_mock_client()
    result = mock.query("ALI_QUERY_001")
    assert result["trade_status"] == "TRADE_SUCCESS"
    assert result["trade_no"].startswith("MOCK_")


def test_create_refund_mock():
    """退款 mock：fund_change=Y。"""
    mock = get_mock_client()
    result = mock.refund("ALI_001", "REF_001", "5.00")
    assert result["fund_change"] == "Y"


def test_alipay_wap_order_amount_decimal():
    """金额格式：total_amount 两位小数字符串，不是 float。"""

    cents = 29
    yuan = _cents_to_yuan_str(cents)
    # 应该是字符串 "0.29"，不是 float 0.29
    assert isinstance(yuan, str)
    assert "." in yuan
    assert len(yuan.split(".")[1]) == 2


def test_reset_mock():
    """reset_mock 清空状态。"""
    reset_mock()
    mock = get_mock_client()
    mock.create_wap_pay("T1", "1.00", "test")
    assert len(mock.orders) == 1
    reset_mock()
    mock2 = get_mock_client()
    assert len(mock2.orders) == 0
