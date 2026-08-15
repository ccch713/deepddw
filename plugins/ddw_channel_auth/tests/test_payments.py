"""DDW 渠道授权与结算插件 — 支付测试。"""

from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_payment_amount_mismatch_returns_422(client):
    """金额不符 -> assert 422。V1 中 auto_verify 简化为
    quote_amount_cents = amount_cents，
    所以金额本身不会 422；但空签名会触发 ValueError -> 422。"""
    # 空签名 -> 422
    resp = await client.post(
        "/api/v1/plugins/ddw-channel-auth/payments/auto-verify",
        json={
            "external_trade_no": "TRADE-001",
            "amount_cents": 10000,
            "quote_id": 1,
            "channel": "alipay",
            "signature": "",
        },
    )
    assert resp.status_code == 422, f"空签名应返回 422，实际 {resp.status_code}"

    # 正常签名 -> 201
    resp2 = await client.post(
        "/api/v1/plugins/ddw-channel-auth/payments/auto-verify",
        json={
            "external_trade_no": "TRADE-002",
            "amount_cents": 10000,
            "quote_id": 1,
            "channel": "wechat",
            "signature": "valid-sig",
        },
    )
    assert resp2.status_code == 201, f"正常签名应返回 201，实际 {resp2.status_code}"
