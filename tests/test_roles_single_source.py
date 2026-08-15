"""角色白单单一来源测试（8 条）。

覆盖 TASK_SPEC P1 表格全部用例：
1. superadmin /auth/me → can_access_admin=True, redirect=/saas-admin.html
2. owner /auth/me → can_access_admin=True
3. admin /auth/me → can_access_admin=True
4. member /auth/me → can_access_admin=False, redirect=/index.html
5. partner /auth/me → can_access_admin=False
6. ROLE_VALUES 与数据库 role 去重值一致
7. current_admin 拒绝 member → 403
8. current_admin 拒绝 partner → 403
"""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient

os.environ.setdefault("DDW_ALWAYS_ACCEPT_CODE", "8888")

from core.auth.jwt import create_access_token
from core.constants.roles import ROLE_VALUES


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

async def _ensure_user(client: AsyncClient, role: str) -> int:
    """在测试 DB 中插入 tenant + user，返回 user_id。"""
    from core.database.session import session_scope
    from core.database.models import Tenant, User
    from core.api.auth import hash_password
    from datetime import datetime

    phone = f"1380000{role:0>5}"[:11]
    async with session_scope() as session:
        # 复用或创建 tenant
        from sqlalchemy import select
        tenant = (await session.execute(select(Tenant).where(Tenant.id == 1))).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(id=1, name="test", plan="free", status="active")
            session.add(tenant)
            await session.flush()
        # 复用或创建 user
        user = (await session.execute(
            select(User).where(User.phone == phone, User.tenant_id == tenant.id)
        )).scalar_one_or_none()
        if user is None:
            user = User(
                tenant_id=tenant.id,
                phone=phone,
                email=f"{role}@test.com",
                password_hash=hash_password("test123456"),
                name=f"test_{role}",
                role=role,
                status="active",
                password_changed_at=datetime.utcnow(),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user.id


def _auth_header(user_id: int, role: str) -> dict:
    token = create_access_token(user_id=user_id, tenant_id=1, role=role)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1-5: /auth/me 各角色返回
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_01_superadmin_me(client: AsyncClient):
    uid = await _ensure_user(client, "superadmin")
    resp = await client.get("/api/v1/auth/me", headers=_auth_header(uid, "superadmin"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_access_admin"] is True
    # 2026-08-11 定案：所有角色统一进入 DDW Pal 工作台（经销商进客户演示中心）
    assert data["redirect_target"] == "/pal.html"


@pytest.mark.asyncio
async def test_02_owner_me(client: AsyncClient):
    uid = await _ensure_user(client, "owner")
    resp = await client.get("/api/v1/auth/me", headers=_auth_header(uid, "owner"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_access_admin"] is True


@pytest.mark.asyncio
async def test_03_admin_me(client: AsyncClient):
    uid = await _ensure_user(client, "admin")
    resp = await client.get("/api/v1/auth/me", headers=_auth_header(uid, "admin"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_access_admin"] is True


@pytest.mark.asyncio
async def test_04_member_me(client: AsyncClient):
    uid = await _ensure_user(client, "member")
    resp = await client.get("/api/v1/auth/me", headers=_auth_header(uid, "member"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_access_admin"] is False
    assert data["redirect_target"] == "/pal.html"


@pytest.mark.asyncio
async def test_05_partner_me(client: AsyncClient):
    uid = await _ensure_user(client, "partner")
    resp = await client.get("/api/v1/auth/me", headers=_auth_header(uid, "partner"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_access_admin"] is False


# ---------------------------------------------------------------------------
# 6: ROLE_VALUES 完整性
# ---------------------------------------------------------------------------

def test_06_role_values_completeness():
    """ROLE_VALUES 包含所有 Role 枚举值。"""
    expected = {"superadmin", "owner", "admin", "member", "partner", "finance", "auditor", "digital_agent"}
    assert set(ROLE_VALUES) == expected


# ---------------------------------------------------------------------------
# 7-8: current_admin 拒绝非管理员
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_07_current_admin_rejects_member(client: AsyncClient):
    uid = await _ensure_user(client, "member")
    # 用 member token 访问需要 admin 权限的端点（如 /admin/plugins）
    resp = await client.get("/api/v1/admin/plugins", headers=_auth_header(uid, "member"))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_08_current_admin_rejects_partner(client: AsyncClient):
    uid = await _ensure_user(client, "partner")
    resp = await client.get("/api/v1/admin/plugins", headers=_auth_header(uid, "partner"))
    assert resp.status_code == 403
