"""ddw-website 插件测试."""
from __future__ import annotations

import os
import sys

# 确保插件目录可导入（pytest 运行时 rootdir 是 ddw-ai-hub）
# __file__ = plugins/ddw_website/tests/test_website.py
# 需要把 plugins/ 加入 sys.path，才能 import ddw_website
_PLUGINS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PLUGINS_DIR not in sys.path:
    sys.path.insert(0, _PLUGINS_DIR)

import tempfile  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# 用临时配置路径避免污染默认配置
TMP_CONFIG = tempfile.mktemp(suffix=".json")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DDW_WEBSITE_CONFIG", TMP_CONFIG)
    from ddw_website.router import router
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c
    if os.path.exists(TMP_CONFIG):
        os.unlink(TMP_CONFIG)


def test_get_theme_default(client):
    resp = client.get("/api/v1/plugins/ddw-website/theme")
    assert resp.status_code == 200
    data = resp.json()
    assert data["theme"] == "standard"
    assert "holiday" in data["available"]
    assert "mourning" in data["available"]


def test_set_theme_valid(client):
    resp = client.put("/api/v1/plugins/ddw-website/theme", json={"theme": "mourning"})
    assert resp.status_code == 200
    assert resp.json()["theme"] == "mourning"

    # 持久化生效
    resp2 = client.get("/api/v1/plugins/ddw-website/theme")
    assert resp2.json()["theme"] == "mourning"


def test_set_theme_invalid(client):
    resp = client.put("/api/v1/plugins/ddw-website/theme", json={"theme": "neon"})
    assert resp.status_code == 400


def test_get_site(client):
    resp = client.get("/api/v1/plugins/ddw-website/site")
    assert resp.status_code == 200
    company = resp.json()["company"]
    assert company["full_name"] == "武汉锐果互动信息技术有限公司"
    assert company["icp"] == "鄂ICP备2026024883号-1"
    assert company["police"] == "鄂公网安备42011102006255号"
    assert company["phone"] == "027-89578881"
    assert company["email"] == "contact@ruigoo.com"


def test_get_pages(client):
    resp = client.get("/api/v1/plugins/ddw-website/pages")
    assert resp.status_code == 200
    pages = resp.json()["pages"]
    assert pages["home"] == "index.html"
    assert pages["industry"] == "industry.html"


def test_update_site(client):
    resp = client.put(
        "/api/v1/plugins/ddw-website/site",
        json={"company": {"phone": "027-88888888"}},
    )
    assert resp.status_code == 200
    resp2 = client.get("/api/v1/plugins/ddw-website/site")
    assert resp2.json()["company"]["phone"] == "027-88888888"
    # 其余字段保持默认
    assert resp2.json()["company"]["full_name"] == "武汉锐果互动信息技术有限公司"
