import sys
import os
import pytest

project_root = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from plugins.ddw_llm_gateway.models import BudgetPolicy  # noqa: E402


@pytest.mark.asyncio
async def test_budget_exceeded_blocks_request(client, storage):
    """超预算时返回 403"""
    policy = BudgetPolicy(
        policy_id="test-budget",
        name="Test Budget",
        scope="key",
        scope_id="test-key-id",
        limit_cents=100,
        period="monthly",
        action_on_exceed="block"
    )
    storage.create_budget(policy)
    storage.update_budget("test-budget", {"current_usage_cents": 100})

    resp = client.post("/v1/chat/completions", json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "hello"}]
    }, headers={"Authorization": "Bearer sk-ddw-test"})

    assert resp.status_code == 403
    assert "budget" in resp.json()["detail"]["error"]["message"].lower()
