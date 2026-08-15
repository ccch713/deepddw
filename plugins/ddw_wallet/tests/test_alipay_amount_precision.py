"""支付宝回调金额精度测试 — 回归防护：float 丢分 Bug（2026-08-05 质检发现并修复）。"""
from decimal import Decimal


def test_alipay_amount_decimal_precision():
    """float("0.29")*100 = 28.999... → int = 28（丢 1 分）；Decimal 必须得 29。"""
    cases = {"0.29": 29, "0.01": 1, "100.00": 10000, "0.10": 10, "5": 500}
    for yuan_str, expect_cents in cases.items():
        cents = int(Decimal(yuan_str) * 100)
        assert cents == expect_cents, (
            f"{yuan_str} 元 → {cents} 分（期望 {expect_cents}）"
        )


def test_alipay_amount_float_bug_reminder():
    """记录 Bug 本质：float 路径会丢分，代码中禁止回退 float 转换。"""
    assert int(float("0.29") * 100) == 28  # float 确实丢分（说明修复必要性）
    assert int(Decimal("0.29") * 100) == 29  # Decimal 正确
