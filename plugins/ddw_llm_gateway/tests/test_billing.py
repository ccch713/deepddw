import sys
import os
import pytest
from unittest.mock import AsyncMock, patch

project_root = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from plugins.ddw_llm_gateway.models import ModelRegistration, RouteRule  # noqa: E402


@pytest.mark.asyncio
async def test_usage_record_created(client, mock_deepseek, storage):
    """请求完成后自动创建 UsageRecord"""
    # 创建专用测试模型（有价格）和路由
    test_model = ModelRegistration(
        model_id="test-billing-model",
        provider="test-billing",
        display_name="Test Billing Model",
        base_url="https://api.test.com/v1",
        api_key="test-key",
        input_price_per_1m=1000.0,
        output_price_per_1m=2000.0,
        priority=1
    )
    storage.create_model(test_model)
    storage.create_route(RouteRule(
        rule_id="route-test-billing",
        name="test-billing",
        scene="test-billing-model",
        strategy="priority",
        model_chain=["test-billing-model"]
    ))

    mock_response = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1694268190,
        "model": "test-billing-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "total_tokens": 300
        }
    }

    with patch('plugins.ddw_llm_gateway.router.call_upstream', AsyncMock(return_value=mock_response)):  # noqa: E501
        resp = client.post("/v1/chat/completions", json={
            "model": "test-billing-model",
            "messages": [{"role": "user", "content": "hello"}]
        }, headers={"Authorization": "Bearer sk-ddw-test"})

        assert resp.status_code == 200

        records = storage.get_usage_records(limit=5)
        # 找到与 test-billing-model 相关的记录
        billing_records = [r for r in records if r.model_id == "test-billing-model"]
        assert len(billing_records) == 1
        assert billing_records[0].input_tokens == 100
        assert billing_records[0].output_tokens == 200
        assert billing_records[0].total_tokens == 300
        assert billing_records[0].total_cost_cents > 0
        assert billing_records[0].plugin_name == "ddw_llm_gateway"
