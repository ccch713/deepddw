"""DDW AI Hub 后端集成测试。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


async def _get_captcha(client: AsyncClient) -> tuple[str, str]:
    """获取验证码，返回 (captcha_id, captcha_code)。"""
    resp = await client.get("/api/v1/auth/captcha")
    assert resp.status_code == 200
    data = resp.json()
    captcha_id = data["captcha_id"]
    from core.auth.captcha import _get_stored_code
    code = _get_stored_code(captcha_id)
    assert code is not None
    return captcha_id, code


async def _register_via_captcha(
    client: AsyncClient,
    phone: str,
    password: str = "test123456",
    email: str | None = None,
    **kwargs,
) -> dict:
    """通过验证码注册用户。"""
    if email is None:
        email = f"user{phone[-4:]}@9cio.com"
    captcha_id, code = await _get_captcha(client)
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "email": email,
            "password": password,
            "captcha_id": captcha_id,
            "captcha_code": code,
            **kwargs,
        },
    )
    assert resp.status_code == 201, f"注册失败: {resp.text}"
    return resp.json()


async def _login_password(
    client: AsyncClient,
    phone: str,
    password: str,
    device_fingerprint: dict | None = None,
) -> dict:
    """通过密码登录（滑块验证）。"""
    # 获取滑块并校验
    resp = await client.get("/api/v1/auth/slider")
    assert resp.status_code == 200
    slider_data = resp.json()
    captcha_id = slider_data["captcha_id"]
    from core.auth.slider_captcha import _get_x_target
    x_target = _get_x_target(captcha_id)
    verify_resp = await client.post(
        "/api/v1/auth/slider/verify",
        json={"captcha_id": captcha_id, "x": x_target},
    )
    assert verify_resp.status_code == 200
    token = verify_resp.json()["token"]

    body = {
        "phone": phone,
        "password": password,
        "slider_token": token,
    }
    if device_fingerprint:
        body["device_fingerprint"] = device_fingerprint
    resp = await client.post("/api/v1/auth/login-password", json=body)
    return resp


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_send_code(client: AsyncClient):
    """send-code 现在需要图形验证码。"""
    captcha_id, code = await _get_captcha(client)
    resp = await client.post(
        "/api/v1/auth/send-code",
        json={"phone": "13800138000", "captcha_id": captcha_id, "captcha_code": code},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] is True


@pytest.mark.asyncio
async def test_register_and_me(client: AsyncClient):
    # 注册（新流程：手机号+密码+图形验证码）
    reg_data = await _register_via_captcha(
        client, "13800138001",
        company_name="测试企业", name="测试用户",
    )
    assert "access_token" in reg_data
    assert reg_data["user"]["phone"] == "13800138001"
    assert reg_data["user"]["role"] == "owner"
    token = reg_data["access_token"]

    # /me
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    me = resp.json()
    assert me["user"]["phone"] == "13800138001"
    assert me["tenant"]["name"] == "测试企业"


@pytest.mark.asyncio
async def test_login_password(client: AsyncClient):
    # 注册 admin（owner 角色）
    reg_data = await _register_via_captcha(client, "13800138002", "pass123456")
    admin_token = reg_data["access_token"]

    # 邀请一个 member 用户
    await client.post(
        "/api/v1/admin/users/invite",
        json={"phone": "13800138050", "name": "普通成员", "role": "member"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # member 用户用万能码登录（验证码登录）
    resp = await client.post(
        "/api/v1/auth/login",
        json={"phone": "13800138050", "code": "8888"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()

    # owner 用户密码登录（需要设备验证 — device_required 默认 False，不卡）
    resp = await _login_password(
        client, "13800138002", "pass123456",
        device_fingerprint={"serial_number": "D9CXVC9Q5L"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_password_wrong(client: AsyncClient):
    # 注册 admin
    reg_data = await _register_via_captcha(client, "13800138003", "correct123")
    admin_token = reg_data["access_token"]

    # 邀请 member 用户
    await client.post(
        "/api/v1/admin/users/invite",
        json={"phone": "13800138051", "name": "测试用户", "role": "member"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # owner 用户错误密码（提供设备指纹）
    resp = await _login_password(
        client, "13800138003", "wrong123",
        device_fingerprint={"serial_number": "D9CXVC9Q5L"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_overview(client: AsyncClient):
    # 注册 admin
    reg_data = await _register_via_captcha(client, "13800138010", "admin123456")
    token = reg_data["access_token"]

    # overview
    resp = await client.get("/api/v1/admin/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "tokens_used" in data
    assert "user" in data


@pytest.mark.asyncio
async def test_admin_users_pagination(client: AsyncClient):
    # 注册 admin
    reg_data = await _register_via_captcha(client, "13800138011", "admin123456")
    token = reg_data["access_token"]

    # 用户列表（分页）
    resp = await client.get(
        "/api/v1/admin/users?page=1&size=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data
    assert "page" in data


@pytest.mark.asyncio
async def test_admin_apikeys(client: AsyncClient):
    # 注册 admin
    reg_data = await _register_via_captcha(client, "13800138012", "admin123456")
    token = reg_data["access_token"]

    # 创建 API Key
    resp = await client.post(
        "/api/v1/admin/apikeys",
        json={"name": "test-key"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    key_data = resp.json()
    assert key_data["name"] == "test-key"
    assert "raw_key" in key_data

    # 列表
    resp = await client.get(
        "/api/v1/admin/apikeys",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_admin_billing(client: AsyncClient):
    # 注册 admin
    reg_data = await _register_via_captcha(client, "13800138013", "admin123456")
    token = reg_data["access_token"]

    resp = await client.get(
        "/api/v1/admin/billing",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == "free"


@pytest.mark.asyncio
async def test_user_bindings(client: AsyncClient):
    # 注册用户
    reg_data = await _register_via_captcha(client, "13800138020", "user123456")
    token = reg_data["access_token"]

    # 查询绑定（空）
    resp = await client.get(
        "/api/v1/user/bindings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []

    # 绑定微信
    resp = await client.post(
        "/api/v1/user/bindings/wechat",
        json={"code": "test_code_123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    binding = resp.json()
    assert binding["provider"] == "wechat"
    binding_id = binding["id"]

    # 再次查询
    resp = await client.get(
        "/api/v1/user/bindings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(resp.json()) == 1

    # 解绑
    resp = await client.delete(
        f"/api/v1/user/bindings/{binding_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # 解绑后查询
    resp = await client.get(
        "/api/v1/user/bindings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.json() == []


@pytest.mark.asyncio
async def test_device_binding_module():
    from core.auth.device_binding import verify_device

    # 匹配 serial
    ok, reason = verify_device({"serial_number": "D9CXVC9Q5L"})
    assert ok is True
    assert "32G-Mac-mini" in reason

    # 匹配 screen
    ok, reason = verify_device({"screen_resolution": "3456x2234"})
    assert ok is True
    assert "128G-MBP" in reason

    # 不匹配
    ok, reason = verify_device({"serial_number": "UNKNOWN"})
    assert ok is False

    # 空指纹
    ok, reason = verify_device({})
    assert ok is False
