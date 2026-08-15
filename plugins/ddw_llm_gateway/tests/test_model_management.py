import sys
import os
import pytest

project_root = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.mark.asyncio
async def test_model_crud(client, storage):
    """模型完整 CRUD 流程"""
    # Create
    resp = client.post("/admin/models", json={
        "model_id": "crud-test-model",
        "provider": "test",
        "display_name": "CRUD Test Model",
        "base_url": "https://api.test.com/v1",
        "input_price_per_1m": 1.0,
        "output_price_per_1m": 2.0,
        "priority": 10
    })
    assert resp.status_code == 200

    # List
    resp = client.get("/admin/models")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # Update
    resp = client.put("/admin/models/crud-test-model", json={
        "priority": 5,
        "display_name": "CRUD Test Model v2"
    })
    assert resp.status_code == 200
    assert resp.json()["priority"] == 5
    assert resp.json()["display_name"] == "CRUD Test Model v2"

    # Delete
    resp = client.delete("/admin/models/crud-test-model")
    assert resp.status_code == 200

    # 验证删除后无法访问
    resp = client.get("/admin/models/crud-test-model")
    assert resp.status_code == 404
