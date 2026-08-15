import sys
import os
import pytest

project_root = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.mark.asyncio
async def test_key_crud(client, storage):
    """Key 完整 CRUD 流程"""
    # Create
    resp = client.post("/admin/keys", json={
        "name": "test-key-crud",
        "plugin_name": "ddw_test"
    })
    assert resp.status_code == 200
    key_data = resp.json()
    assert "api_key" in key_data
    key_id = key_data["key_id"]

    # Read
    resp = client.get(f"/admin/keys/{key_id}")
    assert resp.status_code == 200

    # Update
    resp = client.put(f"/admin/keys/{key_id}", json={"name": "updated"})
    assert resp.status_code == 200

    # Delete
    resp = client.delete(f"/admin/keys/{key_id}")
    assert resp.status_code == 200

    # 验证删除后无法访问
    resp = client.get(f"/admin/keys/{key_id}")
    assert resp.status_code == 404
