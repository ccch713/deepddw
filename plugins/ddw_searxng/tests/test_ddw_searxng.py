"""DDW SearXNG 插件测试（不连真实 SearXNG，用 monkeypatch）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import Response

# 项目根加入 sys.path
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-token-for-deepddw-unit-tests")

from core.security.token_gate import get_access_token  # noqa: E402
from plugins.ddw_searxng.router import build_router  # noqa: E402


@pytest.fixture
def admin_token():
    """deepDDW 静态访问 Token（无账号体系）。"""
    return get_access_token()


@pytest_asyncio.fixture
async def client():
    """创建包含 searxng router 的测试 app。"""
    test_app = FastAPI()
    test_app.include_router(build_router())
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Mock SearXNG responses
# ---------------------------------------------------------------------------

MOCK_SEARCH_BODY = {
    "results": [
        {
            "title": "人工智能 - 维基百科",
            "url": "https://zh.wikipedia.org/wiki/人工智能",
            "content": "人工智能（AI）是计算机科学的一个分支...",
            "engine": "wikipedia",
            "score": 10.0,
        },
        {
            "title": "AI 技术前沿",
            "url": "https://example.com/ai-frontier",
            "content": "最新 AI 技术发展趋势...",
            "engine": "google",
            "score": 8.5,
        },
    ],
    "unresponsive_engines": [["bing", "timeout"]],
}


def _mock_searxng_handler(request: Request) -> Response:
    """Mock SearXNG HTTP 响应。"""
    return Response(200, json=MOCK_SEARCH_BODY)


def _mock_searxng_timeout(request: Request) -> Response:
    """模拟 SearXNG 超时。"""
    raise Exception("Connection timed out")


def _mock_searxng_unavailable(request: Request) -> Response:
    """模拟 SearXNG 不可达。"""
    raise Exception("Connection refused")


# ---------------------------------------------------------------------------
# 1. search 成功
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_success(client, admin_token, monkeypatch):
    """search 成功 → 200、data 归一化正确、total=len。"""
    import plugins.ddw_searxng.router as router_mod

    async def mock_search(query, limit=5, engines=None):
        from plugins.ddw_searxng.services import _normalize
        data = _normalize(MOCK_SEARCH_BODY["results"])[:limit]
        return {
            "data": data,
            "total": len(data),
            "elapsed_ms": 42,
            "unresponsive_engines": MOCK_SEARCH_BODY["unresponsive_engines"],
        }

    monkeypatch.setattr(router_mod, "search", mock_search)

    resp = await client.get(
        "/api/v1/plugins/ddw-searxng/search",
        params={"q": "人工智能", "limit": 5},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["data"]) == 2
    assert data["total"] == 2
    assert data["data"][0]["title"] == "人工智能 - 维基百科"
    assert data["data"][0]["url"] == "https://zh.wikipedia.org/wiki/人工智能"
    assert data["data"][0]["engine"] == "wikipedia"
    assert data["elapsed_ms"] == 42
    assert data["unresponsive_engines"] == [["bing", "timeout"]]


# ---------------------------------------------------------------------------
# 2. search 时 SearXNG 超时/ConnectionError → 500 + error=SEARXNG_UNREACHABLE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_searxng_unreachable(client, admin_token, monkeypatch):
    """SearXNG 不可达 → 200 但 success=false, error=SEARXNG_UNREACHABLE。"""
    import plugins.ddw_searxng.router as router_mod
    from plugins.ddw_searxng.services import SearXNGUnavailable

    async def mock_search_fail(query, limit=5, engines=None):
        raise SearXNGUnavailable("Connection refused")

    monkeypatch.setattr(router_mod, "search", mock_search_fail)

    resp = await client.get(
        "/api/v1/plugins/ddw-searxng/search",
        params={"q": "test"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "SEARXNG_UNREACHABLE"


# ---------------------------------------------------------------------------
# 3. search 缺 q → 422；limit=50 → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_missing_q_returns_422(client, admin_token):
    resp = await client.get(
        "/api/v1/plugins/ddw-searxng/search",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_limit_exceeds_max_returns_422(client, admin_token):
    resp = await client.get(
        "/api/v1/plugins/ddw-searxng/search",
        params={"q": "test", "limit": 50},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. health 成功/失败两态
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_success(client, admin_token, monkeypatch):
    import plugins.ddw_searxng.router as router_mod

    async def mock_health():
        return {
            "ok": True,
            "searxng_url": "http://127.0.0.1:8888",
            "engines": {"wikipedia": True, "google": True},
        }

    monkeypatch.setattr(router_mod, "health_check", mock_health)

    resp = await client.get(
        "/api/v1/plugins/ddw-searxng/health",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "engines" in data


@pytest.mark.asyncio
async def test_health_failure(client, admin_token, monkeypatch):
    import plugins.ddw_searxng.router as router_mod

    async def mock_health_fail():
        return {
            "ok": False,
            "searxng_url": "http://127.0.0.1:8888",
            "engines": {},
            "detail": "Connection refused",
        }

    monkeypatch.setattr(router_mod, "health_check", mock_health_fail)

    resp = await client.get(
        "/api/v1/plugins/ddw-searxng/health",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["detail"] == "Connection refused"


# ---------------------------------------------------------------------------
# 5. 无 token → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_no_token_returns_401(client):
    resp = await client.get(
        "/api/v1/plugins/ddw-searxng/search",
        params={"q": "test"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health_no_token_returns_401(client):
    resp = await client.get("/api/v1/plugins/ddw-searxng/health")
    assert resp.status_code == 401
