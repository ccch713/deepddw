"""DDW 密码生命周期补丁测试（9 条）。

覆盖：自助改密、密码强度策略、定期更换（密码过期）、注册强度校验。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

# 测试环境：启用万能码
os.environ.setdefault("DDW_ALWAYS_ACCEPT_CODE", "8888")


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


async def _register_user(
    client: AsyncClient,
    phone: str = "13800000001",
    password: str = "Test1234",
    email: str | None = None,
) -> dict:
    """注册用户并返回响应数据。"""
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
            "company_name": "测试企业",
            "name": "测试用户",
        },
    )
    assert resp.status_code == 201, f"注册失败: {resp.text}"
    return resp.json()


async def _login_password(client: AsyncClient, phone: str, password: str) -> dict:
    """密码登录并返回响应数据（滑块验证）。"""
    resp_slider = await client.get("/api/v1/auth/slider")
    assert resp_slider.status_code == 200
    slider_data = resp_slider.json()
    captcha_id = slider_data["captcha_id"]
    from core.auth.slider_captcha import _get_x_target
    x_target = _get_x_target(captcha_id)
    verify_resp = await client.post(
        "/api/v1/auth/slider/verify",
        json={"captcha_id": captcha_id, "x": x_target},
    )
    assert verify_resp.status_code == 200
    token = verify_resp.json()["token"]
    resp = await client.post(
        "/api/v1/auth/login-password",
        json={
            "phone": phone,
            "password": password,
            "slider_token": token,
        },
    )
    return resp.json() if resp.status_code == 200 else {"status": resp.status_code, **resp.json()}


# ---------------------------------------------------------------------------
# 1. test_change_password_success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_password_success(client: AsyncClient):
    """登录拿 token → 改密成功 → 新密码可登录、旧密码失败。"""
    reg = await _register_user(client, "13810000001", "OldPass123")
    token = reg["access_token"]

    # 改密
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "OldPass123", "new_password": "NewPass456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["changed"] is True

    # 新密码登录成功
    login_data = await _login_password(client, "13810000001", "NewPass456")
    assert "access_token" in login_data

    # 旧密码登录失败
    resp = await _login_password(client, "13810000001", "OldPass123")
    assert resp.get("status") == 401 or resp.get("detail") == "账号或密码错误"


# ---------------------------------------------------------------------------
# 2. test_change_password_wrong_old
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_password_wrong_old(client: AsyncClient):
    """旧密码错 → 400 "原密码错误"。"""
    reg = await _register_user(client, "13810000002", "Correct123")
    token = reg["access_token"]

    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "WrongOld1", "new_password": "NewPass456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "原密码错误" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 3. test_change_password_weak_new
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_password_weak_new(client: AsyncClient):
    """新密码纯数字 → 400 强度错误。"""
    reg = await _register_user(client, "13810000003", "Correct123")
    token = reg["access_token"]

    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "Correct123", "new_password": "12345678"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "纯数字" in resp.json()["detail"] or "字母" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 4. test_change_password_same_as_old
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_password_same_as_old(client: AsyncClient):
    """新旧相同 → 400。"""
    reg = await _register_user(client, "13810000004", "SamePass1")
    token = reg["access_token"]

    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "SamePass1", "new_password": "SamePass1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "不能与原密码相同" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 5. test_change_password_requires_auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_password_requires_auth(client: AsyncClient):
    """无 token → 401。"""
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "anything1", "new_password": "NewPass456"},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 6. test_register_sets_password_changed_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_sets_password_changed_at(client: AsyncClient):
    """注册后 password_changed_at 非空 → 登录 must_change=False。"""
    reg = await _register_user(client, "13810000006", "RegPass123")
    assert reg["must_change"] is False

    # 登录确认
    login_data = await _login_password(client, "13810000006", "RegPass123")
    assert login_data.get("must_change") is False


# ---------------------------------------------------------------------------
# 7. test_legacy_user_must_change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_user_must_change(client: AsyncClient):
    """password_changed_at=NULL 用户登录 → must_change=True。"""
    reg = await _register_user(client, "13810000007", "Legacy123")

    # 手动清空 password_changed_at 模拟存量账号
    from core.database.models import User
    from core.database.session import session_scope
    from core.database.tenant_filter import bypass_tenant_filter
    from sqlalchemy import select

    async with session_scope() as session, bypass_tenant_filter():
        user = (await session.execute(select(User).where(User.phone == "13810000007"))).scalar_one_or_none()
        assert user is not None
        user.password_changed_at = None
        await session.commit()

    # 登录应返回 must_change=True
    login_data = await _login_password(client, "13810000007", "Legacy123")
    assert login_data.get("must_change") is True


# ---------------------------------------------------------------------------
# 8. test_password_expired_must_change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_password_expired_must_change(client: AsyncClient):
    """password_changed_at 超 90 天 → 登录 must_change=True。"""
    reg = await _register_user(client, "13810000008", "Expir1234")

    # 手动设置 password_changed_at 为 100 天前
    from core.database.models import User
    from core.database.session import session_scope
    from core.database.tenant_filter import bypass_tenant_filter
    from sqlalchemy import select

    async with session_scope() as session, bypass_tenant_filter():
        user = (await session.execute(select(User).where(User.phone == "13810000008"))).scalar_one_or_none()
        assert user is not None
        user.password_changed_at = datetime.utcnow() - timedelta(days=100)
        await session.commit()

    # 登录应返回 must_change=True + password_expired=True
    login_data = await _login_password(client, "13810000008", "Expir1234")
    assert login_data.get("must_change") is True
    assert login_data.get("password_expired") is True


# ---------------------------------------------------------------------------
# 9. test_strength_rejects_weak
# ---------------------------------------------------------------------------


def test_strength_rejects_weak():
    """validate_password_strength 单元测试：纯数字/纯字母/常见弱密码/连续字符 → 拒绝。"""
    from core.auth.password_policy import validate_password_strength

    # 纯数字
    assert validate_password_strength("12345678") is not None
    # 纯字母
    assert validate_password_strength("abcdefgh") is not None
    # 常见弱密码
    assert validate_password_strength("password") is not None
    assert validate_password_strength("admin123") is not None
    # 连续递增
    assert validate_password_strength("12345678") is not None
    # 连续递减
    assert validate_password_strength("87654321") is not None
    # 全部相同
    assert validate_password_strength("11111111") is not None
    # 太短
    assert validate_password_strength("Ab1") is not None
    # 无数字
    assert validate_password_strength("abcdefghi") is not None
    # 无字母
    assert validate_password_strength("12345678") is not None

    # 合格密码
    assert validate_password_strength("MyP4ssw0rd") is None
    assert validate_password_strength("Hello2024") is None
    assert validate_password_strength("Xk9mN2pQ") is None
