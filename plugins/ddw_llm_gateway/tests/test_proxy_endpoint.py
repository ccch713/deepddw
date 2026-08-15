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
async def test_chat_completions_proxy(client, mock_deepseek, storage):
    """POST /v1/chat/completions 正确代理到上游并返回 OpenAI 格式"""
    # 创建专用测试模型和路由，确保路由指向该模型
    test_model = ModelRegistration(
        model_id="test-proxy-model",
        provider="test-provider",
        display_name="Test Proxy Model",
        base_url="https://api.test.com/v1",
        api_key="test-key",
        input_price_per_1m=1.0,
        output_price_per_1m=2.0,
        priority=1
    )
    storage.create_model(test_model)
    storage.create_route(RouteRule(
        rule_id="route-test-proxy",
        name="test-proxy",
        scene="test-proxy-model",
        strategy="priority",
        model_chain=["test-proxy-model"]
    ))

    mock_resp = {
        "id": "chatcmpl-proxy",
        "object": "chat.completion",
        "created": 1694268190,
        "model": "test-proxy-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop"
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    }

    with patch('plugins.ddw_llm_gateway.router.call_upstream', AsyncMock(return_value=mock_resp)):  # noqa: E501
        resp = client.post("/v1/chat/completions", json={
            "model": "test-proxy-model",
            "messages": [{"role": "user", "content": "hello"}]
        }, headers={"Authorization": "Bearer sk-ddw-test"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert "choices" in data
        assert data["model"] == "test-proxy-model"
        assert resp.headers.get("x-llm-provider") == "test-provider"
        assert resp.headers.get("x-llm-model") == "test-proxy-model"
