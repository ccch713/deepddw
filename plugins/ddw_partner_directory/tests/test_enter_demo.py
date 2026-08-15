"""经销商一键进入 Demo + 付费客户列表测试（≥8 条）。

覆盖 spec 第四节用例表：
1. enter-demo 归属自己 → 200 + demo_token
2. enter-demo 归属别人 → 403
3. 非经销商调 enter-demo → 401（无 token）
4. account 不存在 → 404
5. account.status != active → 403
6. demo-login 兑换合法 token → 200 + 正式 JWT
7. demo-login 重复兑换 → 401
8. paid-customers 返回裸数组 + 字段完整
9. paid-customers 只返回当前经销商名下客户
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# 项目根加入 sys.path
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.auth.jwt import create_access_token
from core.database.models import Tenant, User
from plugins.ddw_partner_directory.models import PartnerDemoAccount


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


async def _seed_demo_env(db, *, dealer_tenant_id=14, client_tenant_id=13):
    """种测试数据：经销商租户 + 客户租户 + demo 用户 + demo 账号。"""
    for tid, name, plan, phone in [
        (dealer_tenant_id, "经销商租户", "enterprise", None),
        (client_tenant_id, "客户租户", "enterprise", "18571998165"),
        (99, "其他经销商", "enterprise", None),
        (20, "其他客户租户", "enterprise", None),
        (21, "停用客户租户", "free", None),
    ]:
        db.add(Tenant(id=tid, name=name, plan=plan, status="active", contact_phone=phone))
    await db.flush()

    demo_user = User(tenant_id=client_tenant_id, phone="18571998165", name="万永刚", role="owner", status="active")
    dealer_user = User(tenant_id=dealer_tenant_id, phone="13800000001", name="江昆鹏", role="owner", status="active")
    db.add_all([demo_user, dealer_user])
    await db.flush()

    demo_acc = PartnerDemoAccount(
        tenant_id=dealer_tenant_id, client_tenant_id=client_tenant_id,
        client_name="嘉必优生物技术", client_industry="生物科技",
        demo_url="https://ddw.9cio.com", demo_phone="18571998165",
        demo_password="demo123", status="active",
    )
    other_acc = PartnerDemoAccount(
        tenant_id=99, client_tenant_id=20,
        client_name="其他客户", demo_url="https://other.9cio.com",
        demo_phone="13900000000", demo_password="other123", status="active",
    )
    inactive_acc = PartnerDemoAccount(
        tenant_id=dealer_tenant_id, client_tenant_id=21,
        client_name="已停用客户", demo_url="https://disabled.9cio.com",
        demo_phone="13700000000", demo_password="disabled123", status="inactive",
    )
    db.add_all([demo_acc, other_acc, inactive_acc])
    await db.commit()
    for obj in (demo_user, dealer_user, demo_acc, other_acc, inactive_acc):
        await db.refresh(obj)

    return {
        "dealer_user": dealer_user, "demo_user": demo_user,
        "demo_acc": demo_acc, "other_acc": other_acc, "inactive_acc": inactive_acc,
        "dealer_tenant_id": dealer_tenant_id, "client_tenant_id": client_tenant_id,
    }


def _dealer_token(tenant_id: int, user_id: int) -> str:
    return create_access_token(user_id=user_id, tenant_id=tenant_id, role="owner")


@asynccontextmanager
async def _mock_session_scope(session_factory):
    """用测试 DB 替代生产 session_scope。"""
    async with session_factory() as s:
        try:
            yield s
        except Exception:
            await s.rollback()
            raise


# ---------------------------------------------------------------------------
# enter-demo 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enter_demo_success(seeded_db, session_factory):
    """#1 经销商调 enter-demo 且 account 归属自己 → 200 + demo_token。"""
    env = await _seed_demo_env(seeded_db)
    token = _dealer_token(env["dealer_tenant_id"], env["dealer_user"].id)

    import plugins.ddw_partner_directory.router as router_mod
    from plugins.ddw_partner_directory.router import build_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(build_router())

    original = router_mod.session_scope
    router_mod.session_scope = lambda: _mock_session_scope(session_factory)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/plugins/ddw-partner-directory/enter-demo",
                json={"account_id": env["demo_acc"].id},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "demo_token" in data
        assert len(data["demo_token"]) > 20
        assert data["demo_url"] == "https://ddw.9cio.com"
        assert data["expires_in"] == 900
    finally:
        router_mod.session_scope = original


@pytest.mark.asyncio
async def test_enter_demo_forbidden_other_dealer(seeded_db, session_factory):
    """#2 经销商调 enter-demo 但 account 归属别人 → 403。"""
    env = await _seed_demo_env(seeded_db)
    token = _dealer_token(env["dealer_tenant_id"], env["dealer_user"].id)

    import plugins.ddw_partner_directory.router as router_mod
    from plugins.ddw_partner_directory.router import build_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(build_router())

    original = router_mod.session_scope
    router_mod.session_scope = lambda: _mock_session_scope(session_factory)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/plugins/ddw-partner-directory/enter-demo",
                json={"account_id": env["other_acc"].id},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403
    finally:
        router_mod.session_scope = original


@pytest.mark.asyncio
async def test_enter_demo_no_auth():
    """#3 非经销商（无 token）调 enter-demo → 401。"""
    from plugins.ddw_partner_directory.router import build_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(build_router())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/plugins/ddw-partner-directory/enter-demo",
            json={"account_id": 1},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_enter_demo_account_not_found(seeded_db, session_factory):
    """#4 account 不存在 → 404。"""
    env = await _seed_demo_env(seeded_db)
    token = _dealer_token(env["dealer_tenant_id"], env["dealer_user"].id)

    import plugins.ddw_partner_directory.router as router_mod
    from plugins.ddw_partner_directory.router import build_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(build_router())

    original = router_mod.session_scope
    router_mod.session_scope = lambda: _mock_session_scope(session_factory)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/plugins/ddw-partner-directory/enter-demo",
                json={"account_id": 99999},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404
    finally:
        router_mod.session_scope = original


@pytest.mark.asyncio
async def test_enter_demo_inactive_account(seeded_db, session_factory):
    """#5 account.status != active → 403。"""
    env = await _seed_demo_env(seeded_db)
    token = _dealer_token(env["dealer_tenant_id"], env["dealer_user"].id)

    import plugins.ddw_partner_directory.router as router_mod
    from plugins.ddw_partner_directory.router import build_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(build_router())

    original = router_mod.session_scope
    router_mod.session_scope = lambda: _mock_session_scope(session_factory)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/plugins/ddw-partner-directory/enter-demo",
                json={"account_id": env["inactive_acc"].id},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403
    finally:
        router_mod.session_scope = original


# ---------------------------------------------------------------------------
# demo-login 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_demo_login_success(seeded_db, session_factory):
    """#6 demo-login 兑换合法 token → 200 + 正式会话 JWT。"""
    env = await _seed_demo_env(seeded_db)

    demo_token = create_access_token(
        user_id=env["demo_user"].id, tenant_id=env["client_tenant_id"],
        role="owner", extra={"scope": "demo_enter", "jti": "test_jti_001"}, expires_minutes=15,
    )

    import core.api.auth as auth_mod
    from core.api.auth import router as auth_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(auth_router)

    original = auth_mod.session_scope
    auth_mod.session_scope = lambda: _mock_session_scope(session_factory)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/auth/demo-login", json={"demo_token": demo_token})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["id"] == env["demo_user"].id
        assert data["tenant"]["id"] == env["client_tenant_id"]
    finally:
        auth_mod.session_scope = original


@pytest.mark.asyncio
async def test_demo_login_double_redeem(seeded_db, session_factory):
    """#7 demo-login 重复兑换同一 token → 401。"""
    env = await _seed_demo_env(seeded_db)

    demo_token = create_access_token(
        user_id=env["demo_user"].id, tenant_id=env["client_tenant_id"],
        role="owner", extra={"scope": "demo_enter", "jti": "test_jti_002"}, expires_minutes=15,
    )

    import core.api.auth as auth_mod
    from core.api.auth import router as auth_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(auth_router)

    original = auth_mod.session_scope
    auth_mod.session_scope = lambda: _mock_session_scope(session_factory)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp1 = await ac.post("/api/v1/auth/demo-login", json={"demo_token": demo_token})
            assert resp1.status_code == 200

            resp2 = await ac.post("/api/v1/auth/demo-login", json={"demo_token": demo_token})
            assert resp2.status_code == 401
    finally:
        auth_mod.session_scope = original


# ---------------------------------------------------------------------------
# paid-customers 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paid_customers_returns_array(seeded_db, session_factory):
    """#8 paid-customers 返回裸数组 + 字段完整。"""
    env = await _seed_demo_env(seeded_db)
    token = _dealer_token(env["dealer_tenant_id"], env["dealer_user"].id)

    import plugins.ddw_partner_directory.router as router_mod
    from plugins.ddw_partner_directory.router import build_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(build_router())

    original = router_mod.session_scope
    router_mod.session_scope = lambda: _mock_session_scope(session_factory)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/plugins/ddw-partner-directory/paid-customers",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        item = data[0]
        assert "client_name" in item
        assert "plan" in item
        assert "status" in item
        assert "contact_phone" in item
        assert "client_tenant_id" in item
    finally:
        router_mod.session_scope = original


@pytest.mark.asyncio
async def test_paid_customers_only_own(seeded_db, session_factory):
    """#9 paid-customers 只返回当前经销商名下客户。"""
    env = await _seed_demo_env(seeded_db)
    token = _dealer_token(env["dealer_tenant_id"], env["dealer_user"].id)

    import plugins.ddw_partner_directory.router as router_mod
    from plugins.ddw_partner_directory.router import build_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(build_router())

    original = router_mod.session_scope
    router_mod.session_scope = lambda: _mock_session_scope(session_factory)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/plugins/ddw-partner-directory/paid-customers",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        client_ids = [c["client_tenant_id"] for c in data]
        assert 13 in client_ids
        assert 20 not in client_ids
    finally:
        router_mod.session_scope = original
