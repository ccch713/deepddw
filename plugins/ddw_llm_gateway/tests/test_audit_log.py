import sys
import os
import pytest
from unittest.mock import patch

project_root = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.mark.asyncio
async def test_model_create_audit(client, storage):
    """创建模型后生成审计日志"""
    resp = client.post("/admin/models", json={
        "model_id": "test-model-audit",
        "provider": "test",
        "display_name": "Test Model",
        "base_url": "http://localhost:11434"
    })

    assert resp.status_code == 200

    logs = storage.get_audit_logs(action="model.create", limit=5)
    assert len(logs) >= 1
    found = any(log["target_id"] == "test-model-audit" for log in logs)
    assert found


@pytest.mark.asyncio
async def test_fallback_audit(client, storage):
    """Fallback 事件记录审计日志"""
    with patch('plugins.ddw_llm_gateway.router.call_upstream') as mock_call:
        mock_call.side_effect = [
            Exception("Upstream error"),
            {
                "id": "chatcmpl-123",
                "object": "chat.completion",
                "created": 1694268190,
                "model": "minimax-chat",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],  # noqa: E501
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}  # noqa: E501
            }
        ]

        resp = client.post("/v1/chat/completions", json={
            "model": "default",
            "messages": [{"role": "user", "content": "hello"}]
        }, headers={"Authorization": "Bearer sk-ddw-test"})

        assert resp.status_code == 200

        logs = storage.get_audit_logs(action="request.fallback", limit=5)
        assert len(logs) >= 1
