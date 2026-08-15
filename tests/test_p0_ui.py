"""P0 UI 三项测试（TASK_SPEC_P0_UI_三项.md §三 5 条用例）。

覆盖：
1. GET /auth/me 返回 name/phone
2. saas-admin.html 右上角渲染用户信息
3. partner-demo-accounts.html 有侧栏
4. GET /admin/llm/usage 返回 cloud/selfhosted 双轨
5. LLM 卡片显示双轨 tag
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient


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


async def _register(client: AsyncClient, phone: str, email: str, name: str = "测试用户", password: str = "Test123456!") -> dict:
    cid, code = await _get_captcha(client)
    resp = await client.post("/api/v1/auth/register", json={
        "phone": phone, "email": email, "password": password,
        "captcha_id": cid, "captcha_code": code, "name": name,
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


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_me_returns_name_and_phone(client: AsyncClient):
    """用例 1：GET /auth/me 返回 name/phone，name 非空。"""
    reg = await _register(client, "13800001001", "p0me1@test.com", name="张三")
    token = reg["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "user" in data
    assert data["user"]["name"]  # name 非空
    assert data["user"]["phone"] == "13800001001"


@pytest.mark.asyncio
async def test_saas_admin_html_contains_user_chip_logic(client: AsyncClient):
    """用例 2：saas-admin.html 包含右上角用户信息渲染逻辑。"""
    html = (Path(__file__).resolve().parents[1] / "frontend" / "saas-admin.html").read_text(encoding="utf-8")
    # 检查 renderUserChip 函数存在
    assert "renderUserChip" in html
    # 检查调用 /auth/me
    assert "/api/v1/auth/me" in html
    # 用户信息渲染：新实现（2026-08-14 起）用 name.charAt(0) 头像 + 用户名，
    # 不再用手机号后六位 slice(-6)；断言用户头像渲染逻辑存在
    assert "charAt(0)" in html
    # 检查角色标签
    assert "管理员" in html or "成员" in html


@pytest.mark.asyncio
async def test_partner_demo_accounts_has_sidebar(client: AsyncClient):
    """用例 3：partner-demo-accounts.html 有侧栏（sidebar 元素存在）。"""
    html = (Path(__file__).resolve().parents[1] / "frontend" / "partner-demo-accounts.html").read_text(encoding="utf-8")
    assert 'class="demo-sidebar"' in html or "demo-sidebar" in html
    # 侧栏应包含导航链接
    assert "客户Demo账号" in html
    assert "付费客户" in html


@pytest.mark.asyncio
async def test_admin_llm_usage_returns_dual_track(client: AsyncClient):
    """用例 4：GET /admin/llm/usage 返回 cloud/selfhosted 双轨。"""
    reg = await _register(client, "13800001002", "p0me2@test.com")
    token = reg["access_token"]
    resp = await client.get("/api/v1/admin/llm/usage?days=7", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "cloud" in data, "缺少 cloud 字段"
    assert "selfhosted" in data, "缺少 selfhosted 字段"
    # cloud 结构
    assert "tokens" in data["cloud"]
    assert "cost_cny" in data["cloud"]
    assert "providers" in data["cloud"]
    # selfhosted 结构
    assert "tokens" in data["selfhosted"]
    assert "saved_cny" in data["selfhosted"]
    assert "providers" in data["selfhosted"]


@pytest.mark.asyncio
async def test_saas_admin_html_contains_dual_track_tags(client: AsyncClient):
    """用例 5：LLM 卡片显示双轨 tag（含"云端"和"自建"字样）。"""
    html = (Path(__file__).resolve().parents[1] / "frontend" / "saas-admin.html").read_text(encoding="utf-8")
    assert "云端" in html
    assert "自建" in html
    # 检查 usage.cloud / usage.selfhosted 引用
    assert "usage.cloud" in html
    assert "usage.selfhosted" in html
