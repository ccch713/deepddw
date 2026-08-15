import sys
import os
import pytest
from unittest.mock import patch

project_root = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.mark.asyncio
async def test_priority_routing(client, mock_providers):
    """优先级路由：code 场景应优先使用 deepseek-coder"""
    with patch('plugins.ddw_llm_gateway.router.call_upstream', mock_providers["deepseek-coder"]):  # noqa: E501
        resp = client.post("/v1/chat/completions", json={
            "model": "code",
            "messages": [{"role": "user", "content": "写个快排"}]
        }, headers={"Authorization": "Bearer sk-ddw-test"})

        assert resp.status_code == 200
        assert resp.headers.get("x-llm-model") == "deepseek-coder"


@pytest.mark.asyncio
async def test_cost_routing(client, mock_providers):
    """成本路由：translate 场景应选择成本最低的 provider"""
    with patch('plugins.ddw_llm_gateway.router.call_upstream', mock_providers["minimax-chat"]):  # noqa: E501
        resp = client.post("/v1/chat/completions", json={
            "model": "translate",
            "messages": [{"role": "user", "content": "翻译这段话"}]
        }, headers={"Authorization": "Bearer sk-ddw-test"})

        assert resp.status_code == 200
        assert resp.headers.get("x-llm-model") == "minimax-chat"
