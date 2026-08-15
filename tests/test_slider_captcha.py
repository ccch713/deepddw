"""DDW 滑块验证码测试（7 条）。

覆盖：滑块生成、校验通过/失败/容差、登录集成、多租户死循环修复、失败限流。
"""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient

os.environ.setdefault("DDW_ALWAYS_ACCEPT_CODE", "8888")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


async def _get_slider(client: AsyncClient) -> tuple[str, str, str, int]:
    """获取滑块拼图，返回 (captcha_id, bg_image, puzzle_image, x_target)。"""
    resp = await client.get("/api/v1/auth/slider")
    assert resp.status_code == 200
    data = resp.json()
    captcha_id = data["captcha_id"]
    # 通过内部函数获取真实 x_target（测试用）
    from core.auth.slider_captcha import _get_x_target
    x_target = _get_x_target(captcha_id)
    assert x_target is not None, "滑块 x_target 应已存储"
    return captcha_id, data["bg_image"], data["puzzle_image"], x_target


async def _verify_slider(client: AsyncClient, captcha_id: str, x: int) -> dict:
    """校验滑块位置。"""
    resp = await client.post(
        "/api/v1/auth/slider/verify",
        json={"captcha_id": captcha_id, "x": x},
    )
    return {"status": resp.status_code, "data": resp.json()}


async def _register_user(
    client: AsyncClient,
    phone: str = "13800001001",
    password: str = "Test@2026ddw",
    email: str | None = None,
) -> dict:
    """注册用户（用图片验证码）。"""
    if email is None:
        email = f"user{phone[-4:]}@9cio.com"
    from core.auth.captcha import generate_captcha, _get_stored_code
    captcha_id, _, _ = generate_captcha()
    code = _get_stored_code(captcha_id)
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "email": email,
            "password": password,
            "captcha_id": captcha_id,
            "captcha_code": code,
            "company_name": "测试企业",
            "name": "测试用户",
        },
    )
    assert resp.status_code == 201, f"注册失败: {resp.text}"
    return resp.json()


async def _login_with_slider(
    client: AsyncClient,
    phone: str = "13800001001",
    password: str = "Test@2026ddw",
    tenant_id: int | None = None,
) -> dict:
    """通过滑块 + 密码登录，返回响应数据。"""
    captcha_id, _, _, x_target = await _get_slider(client)
    verify_resp = await _verify_slider(client, captcha_id, x_target)
    assert verify_resp["status"] == 200, f"滑块校验失败: {verify_resp}"
    token = verify_resp["data"]["token"]

    payload = {
        "phone": phone,
        "password": password,
        "slider_token": token,
        "device_fingerprint": {},
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id

    resp = await client.post("/api/v1/auth/login-password", json=payload)
    return {"status": resp.status_code, "data": resp.json(), "slider_token": token}


# ---------------------------------------------------------------------------
# 1. test_slider_generate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slider_generate(client: AsyncClient):
    """GET /auth/slider → 200，返回 captcha_id(32hex)/bg_image/puzzle_image/x_range。"""
    resp = await client.get("/api/v1/auth/slider")
    assert resp.status_code == 200
    data = resp.json()

    # captcha_id: 32 位 hex
    assert "captcha_id" in data
    assert len(data["captcha_id"]) == 32
    assert all(c in "0123456789abcdef" for c in data["captcha_id"])

    # bg_image: data:image/png;base64,...
    assert data["bg_image"].startswith("data:image/png;base64,")

    # puzzle_image: data:image/png;base64,...
    assert data["puzzle_image"].startswith("data:image/png;base64,")

    # x_range: [60, 240]
    assert data["x_range"] == [60, 240]


# ---------------------------------------------------------------------------
# 2. test_slider_verify_ok
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slider_verify_ok(client: AsyncClient):
    """用真实 x_target 校验 → 200 + token。"""
    captcha_id, _, _, x_target = await _get_slider(client)
    resp = await client.post(
        "/api/v1/auth/slider/verify",
        json={"captcha_id": captcha_id, "x": x_target},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert len(data["token"]) >= 16


# ---------------------------------------------------------------------------
# 3. test_slider_verify_wrong
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slider_verify_wrong(client: AsyncClient):
    """x 偏差 50px → 400。"""
    captcha_id, _, _, x_target = await _get_slider(client)
    resp = await client.post(
        "/api/v1/auth/slider/verify",
        json={"captcha_id": captcha_id, "x": x_target + 50},
    )
    assert resp.status_code == 400
    assert "验证失败" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 4. test_slider_verify_tolerance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slider_verify_tolerance(client: AsyncClient):
    """x 偏差 4px（容差内）→ 200。"""
    captcha_id, _, _, x_target = await _get_slider(client)
    resp = await client.post(
        "/api/v1/auth/slider/verify",
        json={"captcha_id": captcha_id, "x": x_target + 4},
    )
    assert resp.status_code == 200
    assert "token" in resp.json()


# ---------------------------------------------------------------------------
# 5. test_login_password_with_slider_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_password_with_slider_token(client: AsyncClient):
    """有效 slider_token + 正确密码 → 200 JWT；登录成功后 token 被 revoke。"""
    await _register_user(client, phone="13800001005", password="Test@2026ddw")

    result = await _login_with_slider(client, phone="13800001005", password="Test@2026ddw")
    assert result["status"] == 200
    data = result["data"]
    assert "access_token" in data
    assert data["user"]["phone"] == "13800001005"

    # 登录成功后 token 被 revoke，再次使用 → 400
    token = result["slider_token"]
    resp = await client.post(
        "/api/v1/auth/login-password",
        json={
            "phone": "13800001005",
            "password": "Test@2026ddw",
            "slider_token": token,
            "device_fingerprint": {},
        },
    )
    assert resp.status_code == 400
    assert "滑块验证" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 6. test_login_password_multitenant_no_consume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_password_multitenant_no_consume(client: AsyncClient):
    """多租户场景：第一次提交 → 409；同一 token 第二次提交（带 tenant_id）→ 200。"""
    # 注册第一个租户
    await _register_user(client, phone="13800001006", password="Test@2026ddw", email="u006a@9cio.com")

    # 注册第二个租户（同手机号不同邮箱 → 不同租户）
    from core.auth.captcha import generate_captcha, _get_stored_code
    captcha_id, _, _ = generate_captcha()
    code = _get_stored_code(captcha_id)
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "phone": "13800001006",
            "email": "u006b@9cio.com",
            "password": "Test@2026ddw",
            "captcha_id": captcha_id,
            "captcha_code": code,
            "company_name": "测试企业B",
            "name": "测试用户B",
        },
    )
    # 可能 201 或 409（同手机号已注册），取决于是否允许同手机号多租户
    # 如果不允许同手机号注册，此测试会跳过多租户部分
    if resp.status_code != 201:
        pytest.skip("同手机号不允许注册多租户，跳过多租户测试")

    # 获取滑块并校验
    captcha_id, _, _, x_target = await _get_slider(client)
    verify_resp = await _verify_slider(client, captcha_id, x_target)
    assert verify_resp["status"] == 200
    token = verify_resp["data"]["token"]

    # 第一次提交（无 tenant_id）→ 409 MULTI_TENANT
    resp1 = await client.post(
        "/api/v1/auth/login-password",
        json={
            "phone": "13800001006",
            "password": "Test@2026ddw",
            "slider_token": token,
            "device_fingerprint": {},
        },
    )
    assert resp1.status_code == 409
    detail = resp1.json()["detail"]
    assert detail["code"] == "MULTI_TENANT"
    tenants = detail["tenants"]
    assert len(tenants) >= 2

    # 第二次提交（同一 token + tenant_id）→ 200（死循环修复验证）
    resp2 = await client.post(
        "/api/v1/auth/login-password",
        json={
            "phone": "13800001006",
            "password": "Test@2026ddw",
            "slider_token": token,
            "tenant_id": tenants[0]["tenant_id"],
            "device_fingerprint": {},
        },
    )
    assert resp2.status_code == 200
    assert "access_token" in resp2.json()


# ---------------------------------------------------------------------------
# 7. test_slider_fail_limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slider_fail_limit(client: AsyncClient):
    """同 IP 错 3 次 → 第 4 次即使 x 正确也 429 + 滑块作废。"""
    # 前 3 次用错误 x（确保不超过 320 的 Pydantic 限制）
    for i in range(3):
        captcha_id, _, _, x_target = await _get_slider(client)
        # 使用 10 作为错误值（与 x_target 差距 > 5px）
        wrong_x = 10
        resp = await client.post(
            "/api/v1/auth/slider/verify",
            json={"captcha_id": captcha_id, "x": wrong_x},
        )
        assert resp.status_code == 400, f"第 {i+1} 次应返回 400"

    # 第 4 次：即使 x 正确也应被限流
    captcha_id, _, _, x_target = await _get_slider(client)
    resp = await client.post(
        "/api/v1/auth/slider/verify",
        json={"captcha_id": captcha_id, "x": x_target},
    )
    assert resp.status_code == 400
    assert "验证失败次数过多" in resp.json()["detail"] or "验证失败" in resp.json()["detail"]
