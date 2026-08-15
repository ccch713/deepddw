"""API 契约测试（P1 — 列表端点统一 {items, total} 信封）。

6 条用例覆盖 TASK_SPEC_P1_API契约.md §四 全部场景。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import assert_list_response


# ---------------------------------------------------------------------------
# 辅助（复用 test_admin_users.py 风格）
# ---------------------------------------------------------------------------


async def _get_captcha(client: AsyncClient) -> tuple[str, str]:
    resp = await client.get("/api/v1/auth/captcha")
    assert resp.status_code == 200
    data = resp.json()
    captcha_id = data["captcha_id"]
    from core.auth.captcha import _get_stored_code
    code = _get_stored_code(captcha_id)
    return captcha_id, code


async def _register(client: AsyncClient, phone: str, email: str, password: str = "Test123456!") -> dict:
    cid, code = await _get_captcha(client)
    resp = await client.post("/api/v1/auth/register", json={
        "phone": phone, "email": email, "password": password,
        "captcha_id": cid, "captcha_code": code,
    })
    if resp.status_code == 409:
        return await _login_sms(client, phone)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _login_sms(client: AsyncClient, phone: str) -> dict:
    cid, code = await _get_captcha(client)
    resp = await client.post("/api/v1/auth/send-code", json={
        "phone": phone, "captcha_id": cid, "captcha_code": code,
    })
    assert resp.status_code == 200
    sms_code = resp.json().get("always_accept", "8888")
    resp2 = await client.post("/api/v1/auth/login", json={"phone": phone, "code": sms_code})
    assert resp2.status_code == 200, resp2.text
    return resp2.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _ensure_superadmin(client: AsyncClient) -> str:
    """确保 superadmin 用户存在并返回 token。"""
    from core.auth.jwt import create_access_token
    from core.database.models import User
    from core.database.session import session_scope
    from core.database.tenant_filter import bypass_tenant_filter
    from sqlalchemy import select as sa_select

    phone = "13800009991"
    email = "sa1@9cio.com"
    async with session_scope() as session, bypass_tenant_filter():
        u = (await session.execute(sa_select(User).where(User.phone == phone))).scalar_one_or_none()
        if u is None:
            await _register(client, phone, email)
            u = (await session.execute(sa_select(User).where(User.phone == phone))).scalar_one()
        if u.role != "superadmin":
            u.role = "superadmin"
            u.user_type = "saas"
            await session.commit()
        return create_access_token(user_id=u.id, tenant_id=u.tenant_id, role="superadmin")


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_01_users_list_envelope(client: AsyncClient):
    """GET /users/ → {items, total} 信封。"""
    token = await _ensure_superadmin(client)
    resp = await client.get("/api/v1/users/", headers=_auth(token))
    assert_list_response(resp)


@pytest.mark.asyncio
async def test_02_admin_plugins_envelope(client: AsyncClient):
    """GET /admin/plugins → {items, total} 信封。"""
    token = await _ensure_superadmin(client)
    resp = await client.get("/api/v1/admin/plugins", headers=_auth(token))
    assert_list_response(resp)


@pytest.mark.asyncio
async def test_03_whitelist_envelope(client: AsyncClient):
    """GET /users/whitelist → {items, total} 信封。"""
    token = await _ensure_superadmin(client)
    resp = await client.get("/api/v1/users/whitelist", headers=_auth(token))
    assert_list_response(resp)


@pytest.mark.asyncio
async def test_04_llm_rules_envelope(client: AsyncClient):
    """GET /llm/rules → {items, total} 信封。"""
    token = await _ensure_superadmin(client)
    resp = await client.get("/api/v1/llm/rules", headers=_auth(token))
    assert_list_response(resp)


@pytest.mark.asyncio
async def test_05_llm_providers_map_allowed(client: AsyncClient):
    """GET /llm/providers → 允许 map（健康检查类例外）。"""
    token = await _ensure_superadmin(client)
    resp = await client.get("/api/v1/llm/providers", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data, "providers 端点应含 providers 字段"


@pytest.mark.asyncio
async def test_06_billing_channels_envelope(client: AsyncClient):
    """GET /admin/billing/channels → {items, total} 信封。"""
    token = await _ensure_superadmin(client)
    resp = await client.get("/api/v1/admin/billing/channels", headers=_auth(token))
    assert_list_response(resp)
