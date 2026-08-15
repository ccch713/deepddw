"""DDW 渠道授权与结算插件 — 电子签适配器测试。"""

from __future__ import annotations

import pytest

from plugins.ddw_channel_auth.signature_adapters import ADAPTERS


@pytest.mark.anyio
async def test_five_adapters_registered():
    """5 家电子签适配器应全部注册。"""
    expected = {"esign", "fadada", "tencent", "qiyuesuo", "shangshangqian"}
    assert set(ADAPTERS.keys()) == expected, f"适配器集合不匹配: {ADAPTERS.keys()}"


@pytest.mark.anyio
async def test_esign_adapter_create_request():
    """e签宝适配器 create_request 返回 mock 数据。"""
    adapter = ADAPTERS["esign"]
    result = await adapter.create_request("合同A", [{"name": "张三"}], "https://cb.url")
    assert "external_request_id" in result
    assert result["external_request_id"].startswith("ESIGN-MOCK-")


@pytest.mark.anyio
async def test_esign_adapter_verify_callback():
    """e签宝适配器 verify_callback V1 mock 直接通过。"""
    adapter = ADAPTERS["esign"]
    assert await adapter.verify_callback({}, "some-sig") is True
    assert await adapter.verify_callback({}, "") is False
