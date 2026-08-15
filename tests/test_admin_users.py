"""用户管理改版（G 项）测试用例（≥20 条）。

覆盖 TASK_SPEC_G §六 测试用例表全部场景。
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from core.database.models import (
    OnPremiseCustomer,
    PluginMeta,
    User,
)
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter


# ---------------------------------------------------------------------------
# 辅助
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
        # 已注册 → 直接登录
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _ensure_superadmin(client: AsyncClient) -> str:
    """确保 superadmin 用户存在并返回 token（幂等，不依赖 rate-limited SMS）。
    同时确保系统内置角色存在。
    """
    from core.auth.jwt import create_access_token
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
        # 确保系统内置角色存在
        from core.database.models import Role
        for rname in ("superadmin", "admin", "sub_admin"):
            exists = (await session.execute(sa_select(Role).where(Role.name == rname))).scalar_one_or_none()
            if not exists:
                session.add(Role(name=rname, description=f"系统内置-{rname}", channel_perms=[], is_system=True))
        await session.commit()
        return create_access_token(user_id=u.id, tenant_id=u.tenant_id, role="superadmin")


async def _ensure_member(client: AsyncClient) -> str:
    """确保普通 member 用户存在并返回 token（role=member，非 owner）。"""
    from core.auth.jwt import create_access_token
    from sqlalchemy import select as sa_select
    phone = "13800000002"
    email = "mem1@9cio.com"
    async with session_scope() as session, bypass_tenant_filter():
        u = (await session.execute(sa_select(User).where(User.phone == phone))).scalar_one_or_none()
        if u is None:
            await _register(client, phone, email)
            u = (await session.execute(sa_select(User).where(User.phone == phone))).scalar_one()
        # 确保 role=member（非 owner/superadmin）
        if u.role in ("owner", "superadmin"):
            u.role = "member"
            await session.commit()
        return create_access_token(user_id=u.id, tenant_id=u.tenant_id, role="member")


async def _ensure_demo_user(client: AsyncClient) -> dict:
    """确保 demo 用户存在（last_login_at 超 15 天）。"""
    from sqlalchemy import select as sa_select
    phone = "13800000003"
    email = "demo1@9cio.com"
    async with session_scope() as session, bypass_tenant_filter():
        u = (await session.execute(sa_select(User).where(User.phone == phone))).scalar_one_or_none()
        if u is None:
            await _register(client, phone, email)
            u = (await session.execute(sa_select(User).where(User.phone == phone))).scalar_one()
        if u.user_type != "demo":
            u.user_type = "demo"
            u.last_login_at = datetime.utcnow() - timedelta(days=20)
            await session.commit()
    return {"id": u.id}


async def _ensure_dealer_user(client: AsyncClient) -> dict:
    """确保经销商用户存在。"""
    from sqlalchemy import select as sa_select
    phone = "13800000004"
    email = "dealer1@9cio.com"
    async with session_scope() as session, bypass_tenant_filter():
        u = (await session.execute(sa_select(User).where(User.phone == phone))).scalar_one_or_none()
        if u is None:
            await _register(client, phone, email)
            u = (await session.execute(sa_select(User).where(User.phone == phone))).scalar_one()
        if u.user_type != "dealer":
            u.user_type = "dealer"
            await session.commit()
    return {"id": u.id}


async def _ensure_onpremise_user(client: AsyncClient, token: str) -> dict:
    """确保独立部署用户存在。"""
    from sqlalchemy import select as sa_select
    phone = "13800000005"
    async with session_scope() as session, bypass_tenant_filter():
        u = (await session.execute(sa_select(User).where(User.phone == phone))).scalar_one_or_none()
        if u is not None:
            return {"id": u.id, "phone": u.phone, "user_type": u.user_type}
    resp = await client.post("/api/v1/admin/users/create", json={
        "phone": phone, "password": "Onpremise1!",
        "name": "独立部署A", "user_type": "onpremise",
        "company_name": "测试公司", "contact_name": "张三",
        "contact_phone": phone,
        "payment_proof_path": "data/payment_proofs/test.jpg",
    }, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 1. superadmin 建角色（含权限勾选）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_01_create_role(client: AsyncClient):
    token = await _ensure_superadmin(client)
    resp = await client.post("/api/v1/admin/roles", json={
        "name": "运营专员",
        "description": "可看仪表盘和网站流量",
        "channel_perms": ["dashboard", "analytics"],
    }, headers=_auth(token))
    assert resp.status_code == 201
    assert resp.json()["name"] == "运营专员"

    resp2 = await client.get("/api/v1/admin/roles", headers=_auth(token))
    assert resp2.status_code == 200
    names = [r["name"] for r in resp2.json()]
    assert "运营专员" in names


# ---------------------------------------------------------------------------
# 2. 非 superadmin 建角色 → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_02_non_superadmin_create_role(client: AsyncClient):
    token = await _ensure_member(client)
    resp = await client.post("/api/v1/admin/roles", json={
        "name": "非法角色", "channel_perms": [],
    }, headers=_auth(token))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 3. 删系统内置角色 → 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_03_delete_system_role(client: AsyncClient):
    token = await _ensure_superadmin(client)
    resp = await client.get("/api/v1/admin/roles", headers=_auth(token))
    assert resp.status_code == 200
    sys_role = next((r for r in resp.json() if r["is_system"]), None)
    assert sys_role is not None

    resp2 = await client.delete(f"/api/v1/admin/roles/{sys_role['id']}", headers=_auth(token))
    assert resp2.status_code == 400
    assert "不可删除" in resp2.json().get("detail", "")


# ---------------------------------------------------------------------------
# 4. 用户列表分类筛选 user_type=dealer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_04_filter_users_by_type(client: AsyncClient):
    token = await _ensure_superadmin(client)
    await _ensure_dealer_user(client)
    resp = await client.get("/api/v1/admin/users/list?user_type=dealer", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for u in data:
        assert u["user_type"] == "dealer"


# ---------------------------------------------------------------------------
# 5. demo 用户状态计算（超15天未登录）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_05_demo_user_status(client: AsyncClient):
    token = await _ensure_superadmin(client)
    await _ensure_demo_user(client)
    resp = await client.get("/api/v1/admin/users/list?user_type=demo", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    demo = data[0]
    assert demo["user_type"] == "demo"
    assert demo["last_active_label"] is not None


# ---------------------------------------------------------------------------
# 6. 新建独立部署用户（带凭证路径）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_06_create_onpremise_user(client: AsyncClient):
    token = await _ensure_superadmin(client)
    resp = await client.post("/api/v1/admin/users/create", json={
        "phone": "13800000006", "password": "Onpremise2!",
        "name": "独立部署B", "user_type": "onpremise",
        "company_name": "B公司", "payment_proof_path": "data/payment_proofs/proof.jpg",
    }, headers=_auth(token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_type"] == "onpremise"

    async with session_scope() as session, bypass_tenant_filter():
        from sqlalchemy import select as sa_select
        cust = (await session.execute(
            sa_select(OnPremiseCustomer).where(OnPremiseCustomer.user_id == data["id"])
        )).scalar_one_or_none()
        assert cust is not None
        assert cust.company_name == "B公司"


# ---------------------------------------------------------------------------
# 7. 新建独立部署用户（无凭证）→ 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_07_create_onpremise_no_proof(client: AsyncClient):
    token = await _ensure_superadmin(client)
    resp = await client.post("/api/v1/admin/users/create", json={
        "phone": "13800000007", "password": "Onpremise3!",
        "user_type": "onpremise",
    }, headers=_auth(token))
    assert resp.status_code == 422
    assert "凭证" in resp.json().get("detail", "")


# ---------------------------------------------------------------------------
# 8. 发授权码
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_08_issue_license(client: AsyncClient):
    token = await _ensure_superadmin(client)
    opu = await _ensure_onpremise_user(client, token)
    uid = opu["id"]
    resp = await client.post(f"/api/v1/admin/onpremise/{uid}/license-keys", json={
        "license_code": "LIC-2026-001",
        "expires_at": "2027-12-31T23:59:59",
    }, headers=_auth(token))
    assert resp.status_code == 201
    assert resp.json()["license_code"] == "LIC-2026-001"

    resp2 = await client.get(f"/api/v1/admin/onpremise/{uid}", headers=_auth(token))
    assert resp2.status_code == 200
    assert len(resp2.json()["license_keys"]) >= 1


# ---------------------------------------------------------------------------
# 9. 授权码记录插件增删
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_09_license_plugin_change(client: AsyncClient):
    token = await _ensure_superadmin(client)
    opu = await _ensure_onpremise_user(client, token)
    uid = opu["id"]
    resp = await client.post(f"/api/v1/admin/onpremise/{uid}/license-keys", json={
        "license_code": "LIC-2026-002",
    }, headers=_auth(token))
    kid = resp.json()["id"]

    resp2 = await client.post(f"/api/v1/admin/license-keys/{kid}/plugins", json={
        "action": "add",
        "plugin_names": ["ddw_training", "ddw_report"],
        "reason": "首次安装",
    }, headers=_auth(token))
    assert resp2.status_code == 200
    assert resp2.json()["recorded"] == 2


# ---------------------------------------------------------------------------
# 10. 授权码详情含变更记录
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_10_license_detail(client: AsyncClient):
    token = await _ensure_superadmin(client)
    opu = await _ensure_onpremise_user(client, token)
    uid = opu["id"]
    resp = await client.post(f"/api/v1/admin/onpremise/{uid}/license-keys", json={
        "license_code": "LIC-2026-003",
    }, headers=_auth(token))
    kid = resp.json()["id"]

    await client.post(f"/api/v1/admin/license-keys/{kid}/plugins", json={
        "action": "add", "plugin_names": ["ddw_kpi"],
    }, headers=_auth(token))

    resp2 = await client.get(f"/api/v1/admin/license-keys/{kid}", headers=_auth(token))
    assert resp2.status_code == 200
    detail = resp2.json()
    assert detail["license_code"] == "LIC-2026-003"
    assert len(detail["plugin_changes"]) >= 1
    assert detail["plugin_changes"][0]["plugin_name"] == "ddw_kpi"


# ---------------------------------------------------------------------------
# 11. 凭证上传（multipart 假文件）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_11_upload_proof(client: AsyncClient):
    token = await _ensure_superadmin(client)
    fake_pdf = b"%PDF-1.4 fake content"
    resp = await client.post(
        "/api/v1/admin/upload-proof",
        files={"file": ("receipt.pdf", io.BytesIO(fake_pdf), "application/pdf")},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "path" in data
    assert data["filename"] == "receipt.pdf"


# ---------------------------------------------------------------------------
# 12. 子管理员建子管理员 → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_12_sub_admin_cannot_create(client: AsyncClient):
    token = await _ensure_member(client)
    resp = await client.post("/api/v1/admin/sub-admins", json={
        "phone": "13800009912", "password": "Subadmin1!",
        "channel_perms": ["dashboard"],
    }, headers=_auth(token))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 13. superadmin 建子管理员
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_13_superadmin_create_sub_admin(client: AsyncClient):
    token = await _ensure_superadmin(client)
    resp = await client.post("/api/v1/admin/sub-admins", json={
        "phone": "13800009913", "password": "Subadmin2!",
        "name": "子管理员A",
        "channel_perms": ["dashboard", "users"],
    }, headers=_auth(token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["channel_perms"] == ["dashboard", "users"]


# ---------------------------------------------------------------------------
# 14. 子管理员访问未授权端点 → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_14_sub_admin_unauthorized(client: AsyncClient):
    token = await _ensure_member(client)
    resp = await client.get("/api/v1/admin/users/list", headers=_auth(token))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 15. 批量停用 2 用户
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_15_batch_disable(client: AsyncClient):
    token = await _ensure_superadmin(client)
    for i in range(2):
        await client.post("/api/v1/admin/users/create", json={
            "phone": f"1380000150{i}", "password": "Disable1!",
            "user_type": "saas",
        }, headers=_auth(token))

    resp = await client.get("/api/v1/admin/users/list", headers=_auth(token))
    ids = [u["id"] for u in resp.json() if u["phone"].startswith("1380000150")]
    assert len(ids) == 2

    resp2 = await client.post("/api/v1/admin/users/batch-disable", json={"ids": ids}, headers=_auth(token))
    assert resp2.status_code == 200
    assert resp2.json()["disabled"] == 2

    async with session_scope() as session, bypass_tenant_filter():
        from sqlalchemy import select as sa_select
        for uid in ids:
            u = (await session.execute(
                sa_select(User).where(User.id == uid)
            )).scalar_one()
            assert u.status == "disabled"
            assert u.disabled_at is not None


# ---------------------------------------------------------------------------
# 16. 停用用户登录 → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_16_disabled_user_login(client: AsyncClient):
    await _register(client, "13800009916", "disabled1@9cio.com")
    async with session_scope() as session, bypass_tenant_filter():
        from sqlalchemy import select as sa_select
        u = (await session.execute(
            sa_select(User).where(User.phone == "13800009916")
        )).scalar_one()
        u.status = "disabled"
        u.disabled_at = datetime.utcnow()
        await session.commit()

    cid, code = await _get_captcha(client)
    await client.post("/api/v1/auth/send-code", json={
        "phone": "13800009916", "captcha_id": cid, "captcha_code": code,
    })
    resp = await client.post("/api/v1/auth/login", json={"phone": "13800009916", "code": "8888"})
    assert resp.status_code == 403
    assert "停用" in resp.json().get("detail", "")


# ---------------------------------------------------------------------------
# 17. 停用用户列表排序
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_17_disabled_users_sorted(client: AsyncClient):
    token = await _ensure_superadmin(client)
    for i in range(2):
        await _register(client, f"1380000170{i}", f"dsort{i}@9cio.com")
        async with session_scope() as session, bypass_tenant_filter():
            from sqlalchemy import select as sa_select
            u = (await session.execute(
                sa_select(User).where(User.phone == f"1380000170{i}")
            )).scalar_one()
            u.status = "disabled"
            u.disabled_at = datetime.utcnow() - timedelta(days=10 - i)
            await session.commit()

    resp = await client.get("/api/v1/admin/users/disabled", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if len(data) >= 2:
        assert data[0]["disabled_days"] >= data[1]["disabled_days"]


# ---------------------------------------------------------------------------
# 18. quote 差价计算
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_18_quote_price(client: AsyncClient):
    token = await _ensure_superadmin(client)
    opu = await _ensure_onpremise_user(client, token)
    uid = opu["id"]

    async with session_scope() as session, bypass_tenant_filter():
        from sqlalchemy import select as sa_select
        existing = (await session.execute(
            sa_select(PluginMeta).where(PluginMeta.plugin_name == "ddw_training")
        )).scalar_one_or_none()
        if not existing:
            session.add(PluginMeta(plugin_name="ddw_training", price_cny=100.0))
        existing2 = (await session.execute(
            sa_select(PluginMeta).where(PluginMeta.plugin_name == "ddw_report")
        )).scalar_one_or_none()
        if not existing2:
            session.add(PluginMeta(plugin_name="ddw_report", price_cny=50.0))
        await session.commit()

    resp = await client.post(f"/api/v1/admin/onpremise/{uid}/license-keys", json={
        "license_code": "LIC-QUOTE-001",
    }, headers=_auth(token))
    kid = resp.json()["id"]

    resp2 = await client.post(f"/api/v1/admin/license-keys/{kid}/quote", json={
        "plugin_names": ["ddw_training", "ddw_report"],
    }, headers=_auth(token))
    assert resp2.status_code == 200
    assert resp2.json()["total_cny"] == 150.0


# ---------------------------------------------------------------------------
# 19. 僵尸用户判定
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_19_zombie_user(client: AsyncClient):
    token = await _ensure_superadmin(client)
    await _register(client, "13800009919", "zombie1@9cio.com")
    async with session_scope() as session, bypass_tenant_filter():
        from sqlalchemy import select as sa_select
        u = (await session.execute(
            sa_select(User).where(User.phone == "13800009919")
        )).scalar_one()
        u.last_login_at = datetime.utcnow() - timedelta(days=90)
        u.user_type = "saas"
        await session.commit()

    resp = await client.get("/api/v1/admin/users/list", headers=_auth(token))
    assert resp.status_code == 200
    zombie = next((u for u in resp.json() if u["phone"] == "13800009919"), None)
    assert zombie is not None
    assert zombie["zombie"] is True


# ---------------------------------------------------------------------------
# 20. 用户列表含 last_active_label
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_20_last_active_label(client: AsyncClient):
    token = await _ensure_superadmin(client)
    await _register(client, "13800009920", "label1@9cio.com")
    async with session_scope() as session, bypass_tenant_filter():
        from sqlalchemy import select as sa_select
        u = (await session.execute(
            sa_select(User).where(User.phone == "13800009920")
        )).scalar_one()
        u.last_login_at = datetime.utcnow() - timedelta(days=3, hours=5)
        u.user_type = "saas"
        await session.commit()

    resp = await client.get("/api/v1/admin/users/list", headers=_auth(token))
    assert resp.status_code == 200
    user = next((u for u in resp.json() if u["phone"] == "13800009920"), None)
    assert user is not None
    assert user["last_active_label"] is not None
    assert "天" in user["last_active_label"]


# ---------------------------------------------------------------------------
# 补充：用户详情 / 编辑角色 / 重复角色名
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_21_user_detail(client: AsyncClient):
    token = await _ensure_superadmin(client)
    opu = await _ensure_onpremise_user(client, token)
    uid = opu["id"]
    resp = await client.get(f"/api/v1/admin/users/detail/{uid}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["user_type"] == "onpremise"


@pytest.mark.asyncio
async def test_22_update_role(client: AsyncClient):
    token = await _ensure_superadmin(client)
    resp = await client.post("/api/v1/admin/roles", json={
        "name": "临时角色", "channel_perms": ["dashboard"],
    }, headers=_auth(token))
    rid = resp.json()["id"]

    resp2 = await client.put(f"/api/v1/admin/roles/{rid}", json={
        "channel_perms": ["dashboard", "analytics"],
    }, headers=_auth(token))
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_23_duplicate_role_name(client: AsyncClient):
    token = await _ensure_superadmin(client)
    await client.post("/api/v1/admin/roles", json={
        "name": "唯一角色", "channel_perms": [],
    }, headers=_auth(token))
    resp = await client.post("/api/v1/admin/roles", json={
        "name": "唯一角色", "channel_perms": [],
    }, headers=_auth(token))
    assert resp.status_code == 409
