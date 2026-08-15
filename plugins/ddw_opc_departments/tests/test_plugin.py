import sys
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure the plugin package is importable
PLUGIN_DIR = Path(__file__).resolve().parent.parent.parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from ddw_opc_departments import PLUGIN_NAME, VERSION  # noqa: E402
from ddw_opc_departments.router import build_router  # noqa: E402


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(build_router())
    return TestClient(app)


@pytest.fixture()
def departments_yaml():
    data_path = Path(__file__).resolve().parent.parent / "departments.yaml"
    with open(data_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# 1. test_load_departments
def test_load_departments(departments_yaml):
    depts = departments_yaml.get("departments", {})
    assert len(depts) == 11


# 2. test_health
def test_health(client):
    resp = client.get(f"/api/v1/plugins/{PLUGIN_NAME}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plugin"] == PLUGIN_NAME
    assert body["version"] == VERSION
    assert body["status"] == "ok"
    assert body["departments"] == 11


# 3. test_list_departments
def test_list_departments(client):
    resp = client.get(f"/api/v1/plugins/{PLUGIN_NAME}/departments")
    assert resp.status_code == 200
    depts = resp.json()
    assert len(depts) == 11
    # ceo should be first (priority 100)
    assert depts[0]["id"] == "ceo"
    # sorted descending by priority
    priorities = [d["priority"] for d in depts]
    assert priorities == sorted(priorities, reverse=True)


# 4. test_route_keyword
def test_route_keyword(client):
    resp = client.post(
        f"/api/v1/plugins/{PLUGIN_NAME}/route",
        json={"text": "帮我分析竞品"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["department"] == "product"
    assert body["method"] == "keyword"


# 5. test_route_explicit
def test_route_explicit(client):
    resp = client.post(
        f"/api/v1/plugins/{PLUGIN_NAME}/route",
        json={"text": "@财务 本月开销"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["department"] == "finance"
    assert body["method"] == "explicit"


# 6. test_route_fallback
def test_route_fallback(client):
    resp = client.post(
        f"/api/v1/plugins/{PLUGIN_NAME}/route",
        json={"text": "随便聊聊"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["department"] == "admin"
    assert body["method"] == "fallback"


# 7. test_quant_enabled
def test_quant_enabled(client, departments_yaml):
    depts = departments_yaml.get("departments", {})
    assert "quant" in depts
    resp = client.get(f"/api/v1/plugins/{PLUGIN_NAME}/departments")
    dept_ids = [d["id"] for d in resp.json()]
    assert "quant" in dept_ids
    resp_cfg = client.get(f"/api/v1/plugins/{PLUGIN_NAME}/config")
    assert resp_cfg.json()["departments"]["quant"]["enabled"] is True


# 8. test_collaboration
def test_collaboration(client):
    resp = client.get(f"/api/v1/plugins/{PLUGIN_NAME}/collaboration/product")
    assert resp.status_code == 200
    targets = resp.json()
    assert len(targets) > 0
    assert "ceo" in targets
