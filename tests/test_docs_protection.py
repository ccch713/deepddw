"""文档库 URL 级保护测试（签名 URL + Bearer JWT 双通道鉴权）。"""

from __future__ import annotations

import os
import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# 测试前设置环境
os.environ.setdefault("DDW_JWT_SECRET", "test-secret-key-for-testing-32bytes-ok")
os.environ.setdefault("DDW_DOCS_SIGN_SECRET", "test-docs-sign-secret-for-unit-tests")

from core.auth.jwt import create_access_token  # noqa: E402
from core.main import app  # noqa: E402


@pytest.fixture
def admin_token():
    """生成 admin 角色 JWT。"""
    return create_access_token(user_id=1, tenant_id=1, role="admin")


@pytest.fixture
def member_token():
    """生成 member 角色 JWT。"""
    return create_access_token(user_id=2, tenant_id=1, role="member")


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# 1. 无签名访问 → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_auth_returns_401(client):
    resp = await client.get("/docs/fde/unlimited-ocr-demo-sop.html")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. 错误 sig → 401；过期 exp → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bad_sig_returns_401(client):
    resp = await client.get(
        "/docs/fde/unlimited-ocr-demo-sop.html",
        params={"sig": "badsig123", "exp": int(time.time()) + 900},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_sig_returns_401(client):
    resp = await client.get(
        "/docs/fde/unlimited-ocr-demo-sop.html",
        params={"sig": "anysig", "exp": int(time.time()) - 100},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. 合法签名 → 200 且 content-type text/html
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_sig_returns_200(client, admin_token):
    # 先通过 admin token 获取签名 URL
    sign_resp = await client.get(
        "/api/v1/docs/sign",
        params={"path": "fde/unlimited-ocr-demo-sop.html"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert sign_resp.status_code == 200
    url = sign_resp.json()["url"]

    # 用签名 URL 访问文档
    doc_resp = await client.get(url)
    assert doc_resp.status_code == 200
    assert "text/html" in doc_resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# 4. 路径穿越 → 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_path_traversal_returns_400(client):
    resp = await client.get(
        "/docs/fde/..%2F..%2Fetc%2Fpasswd",
        params={"sig": "anysig", "exp": int(time.time()) + 900},
    )
    # FastAPI 会解码 %2F，filename 变成 "../../etc/passwd" 不匹配白名单
    assert resp.status_code in (400, 404, 422)


# ---------------------------------------------------------------------------
# 5. 文件名非法（a.exe）→ 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_illegal_filename_returns_400(client):
    resp = await client.get("/docs/fde/a.exe")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 6. /api/v1/docs/sign 无 token → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sign_no_token_returns_401(client):
    resp = await client.get(
        "/api/v1/docs/sign",
        params={"path": "fde/unlimited-ocr-demo-sop.html"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 7. /api/v1/docs/sign 带 admin token → 200 且返回 url 含 sig
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sign_with_admin_token_returns_url(client, admin_token):
    resp = await client.get(
        "/api/v1/docs/sign",
        params={"path": "fde/unlimited-ocr-demo-sop.html"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert "sig=" in data["url"]
    assert "exp=" in data["url"]
    assert "/docs/fde/unlimited-ocr-demo-sop.html" in data["url"]


# ---------------------------------------------------------------------------
# 8. 签名 URL 访问真实文件（frontend/docs/fde/ 下文件存在）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signed_url_access_real_file(client, admin_token):
    """端到端：admin 获取签名 URL → 用签名 URL 访问真实文件 → 200。"""
    # 生成签名
    sign_resp = await client.get(
        "/api/v1/docs/sign",
        params={"path": "fde/unlimited-ocr-deploy.html"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert sign_resp.status_code == 200
    url = sign_resp.json()["url"]

    # 访问文档
    doc_resp = await client.get(url)
    assert doc_resp.status_code == 200
    assert "text/html" in doc_resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# 附加：member 角色无法生成签名
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sign_with_member_token_returns_403(client, member_token):
    resp = await client.get(
        "/api/v1/docs/sign",
        params={"path": "fde/unlimited-ocr-demo-sop.html"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 附加：非 fde/ 前缀路径 → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sign_non_fde_path_returns_403(client, admin_token):
    resp = await client.get(
        "/api/v1/docs/sign",
        params={"path": "public/some-doc.html"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 403
