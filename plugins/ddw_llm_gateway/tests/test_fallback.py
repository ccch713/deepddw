import sys
import os
import pytest
from unittest.mock import patch

project_root = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.mark.asyncio
async def test_fallback_on_upstream_error(client, mock_providers):
    """主模型返回 500 时自动 fallback 到下一个模型"""
    mock_minimax = mock_providers["minimax-chat"]

    with patch('plugins.ddw_llm_gateway.router.call_upstream') as mock_call:
        mock_call.side_effect = [
            Exception("Upstream error 500"), mock_minimax.return_value]

        resp = client.post("/v1/chat/completions", json={
            "model": "default",
            "messages": [{"role": "user", "content": "hello"}]
        }, headers={"Authorization": "Bearer sk-ddw-test"})

        assert resp.status_code == 200
        assert resp.headers.get("x-llm-model") == "minimax-chat"


@pytest.mark.asyncio
async def test_all_providers_failed(client, mock_providers):
    """所有 provider 均失败时返回 503"""
    with patch('plugins.ddw_llm_gateway.router.call_upstream') as mock_call:
        mock_call.side_effect = Exception("Upstream error 500")

        resp = client.post("/v1/chat/completions", json={
            "model": "default",
            "messages": [{"role": "user", "content": "hello"}]
        }, headers={"Authorization": "Bearer sk-ddw-test"})

        assert resp.status_code == 503
        assert "All providers failed" in resp.json()["detail"]["error"]["message"]
