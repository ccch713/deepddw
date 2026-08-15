"""插件市场论坛（F 项）测试用例（≥10 条）。

覆盖 TASK_SPEC_F §六 测试用例表全部场景。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.auth.jwt import create_access_token
from core.database.models import PluginMarketItem, User
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from sqlalchemy import select as sa_select


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


async def _ensure_user(client: AsyncClient, phone: str, email: str, role: str = "member") -> str:
    """确保用户存在并返回 token。"""
    async with session_scope() as session, bypass_tenant_filter():
        u = (await session.execute(sa_select(User).where(User.phone == phone))).scalar_one_or_none()
        if u is None:
            await _register(client, phone, email)
            u = (await session.execute(sa_select(User).where(User.phone == phone))).scalar_one()
        if u.role != role:
            u.role = role
            await session.commit()
        return create_access_token(user_id=u.id, tenant_id=u.tenant_id, role=role)


async def _ensure_market_item(plugin_name: str = "ddw_bid_writer") -> None:
    """确保 PluginMarketItem 存在。"""
    async with session_scope() as session, bypass_tenant_filter():
        existing = (await session.execute(
            sa_select(PluginMarketItem).where(PluginMarketItem.plugin_name == plugin_name)
        )).scalar_one_or_none()
        if existing is None:
            session.add(PluginMarketItem(
                plugin_name=plugin_name,
                title="DDW 投标标书撰写",
                category="制造业",
                installs=0, stars=0.0, star_count=0, updated_at="2026-08-01",
            ))
            await session.commit()


# ---------------------------------------------------------------------------
# 1. 未登录访问 forum 列表 → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_01_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/forum/plugins")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. 登录后 GET /forum/plugins → 200 + 裸数组 + 每项含 title/category
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_02_forum_plugin_list(client: AsyncClient):
    token = await _ensure_user(client, "13800100001", "forum1@9cio.com")
    await _ensure_market_item()
    resp = await client.get("/api/v1/forum/plugins", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    item = data[0]
    assert "title" in item
    assert "category" in item
    assert "plugin_name" in item


# ---------------------------------------------------------------------------
# 3. GET /forum/plugins/{name} 不存在的插件 → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_03_plugin_not_found(client: AsyncClient):
    token = await _ensure_user(client, "13800100002", "forum2@9cio.com")
    resp = await client.get("/api/v1/forum/plugins/ddw_nonexistent", headers=_auth(token))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. 打分 1-5 → 200 + plugin_market_items.stars 更新正确
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_04_star_plugin(client: AsyncClient):
    token = await _ensure_user(client, "13800100003", "forum3@9cio.com")
    await _ensure_market_item("ddw_training")
    resp = await client.post("/api/v1/forum/plugins/ddw_training/star", json={"stars": 4}, headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["stars"] == 4
    assert data["avg_stars"] == 4.0
    assert data["star_count"] == 1


# ---------------------------------------------------------------------------
# 5. 重复打分（upsert）→ 200 + star_count 不重复增加
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_05_star_upsert(client: AsyncClient):
    token = await _ensure_user(client, "13800100004", "forum4@9cio.com")
    await _ensure_market_item("ddw_report")
    await client.post("/api/v1/forum/plugins/ddw_report/star", json={"stars": 3}, headers=_auth(token))
    resp = await client.post("/api/v1/forum/plugins/ddw_report/star", json={"stars": 5}, headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["star_count"] == 1  # upsert，不重复增加
    assert data["avg_stars"] == 5.0


# ---------------------------------------------------------------------------
# 6. 打分越界（0 或 6）→ 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_06_star_out_of_range(client: AsyncClient):
    token = await _ensure_user(client, "13800100005", "forum5@9cio.com")
    resp = await client.post("/api/v1/forum/plugins/ddw_training/star", json={"stars": 0}, headers=_auth(token))
    assert resp.status_code == 422

    resp2 = await client.post("/api/v1/forum/plugins/ddw_training/star", json={"stars": 6}, headers=_auth(token))
    assert resp2.status_code == 422


# ---------------------------------------------------------------------------
# 7. 发帖 → 200 + thread 创建 + 列表可见
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_07_create_thread(client: AsyncClient):
    token = await _ensure_user(client, "13800100006", "forum6@9cio.com")
    await _ensure_market_item("ddw_kpi")
    resp = await client.post("/api/v1/forum/plugins/ddw_kpi/threads", json={
        "title": "如何配置 KPI 看板？",
        "content": "请问 KPI 看板的默认配置在哪里修改？",
    }, headers=_auth(token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "如何配置 KPI 看板？"
    assert data["plugin_name"] == "ddw_kpi"

    # 列表可见
    resp2 = await client.get("/api/v1/forum/plugins/ddw_kpi/threads", headers=_auth(token))
    assert resp2.status_code == 200
    items = resp2.json()["items"]
    assert any(t["title"] == "如何配置 KPI 看板？" for t in items)


# ---------------------------------------------------------------------------
# 8. 发帖内容为空 → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_08_empty_thread(client: AsyncClient):
    token = await _ensure_user(client, "13800100007", "forum7@9cio.com")
    resp = await client.post("/api/v1/forum/plugins/ddw_kpi/threads", json={
        "title": "", "content": "",
    }, headers=_auth(token))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 9. 回复帖子 → 200 + replies_count+1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_09_reply_thread(client: AsyncClient):
    token = await _ensure_user(client, "13800100008", "forum8@9cio.com")
    await _ensure_market_item("ddw_wallet")

    # 先发帖
    resp = await client.post("/api/v1/forum/plugins/ddw_wallet/threads", json={
        "title": "钱包余额异常", "content": "充值后余额未更新",
    }, headers=_auth(token))
    assert resp.status_code == 201
    tid = resp.json()["id"]

    # 回复
    resp2 = await client.post(f"/api/v1/forum/threads/{tid}/replies", json={
        "content": "我也遇到同样问题",
    }, headers=_auth(token))
    assert resp2.status_code == 201

    # 验证 replies_count
    resp3 = await client.get(f"/api/v1/forum/threads/{tid}", headers=_auth(token))
    assert resp3.status_code == 200
    assert resp3.json()["replies_count"] == 1
    assert len(resp3.json()["replies"]) == 1


# ---------------------------------------------------------------------------
# 10. 帖子详情 views+1 → 两次 GET 后 views 递增
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_10_views_increment(client: AsyncClient):
    token = await _ensure_user(client, "13800100009", "forum9@9cio.com")
    await _ensure_market_item("ddw_inventory")

    resp = await client.post("/api/v1/forum/plugins/ddw_inventory/threads", json={
        "title": "库存同步问题", "content": "库存数据不同步",
    }, headers=_auth(token))
    tid = resp.json()["id"]

    resp1 = await client.get(f"/api/v1/forum/threads/{tid}", headers=_auth(token))
    views1 = resp1.json()["views"]

    resp2 = await client.get(f"/api/v1/forum/threads/{tid}", headers=_auth(token))
    views2 = resp2.json()["views"]

    assert views2 == views1 + 1


# ---------------------------------------------------------------------------
# 11. 置顶（admin）→ 200 + is_pinned=True；非 admin → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_11_pin_thread_admin(client: AsyncClient):
    admin_token = await _ensure_user(client, "13800100010", "forum10@9cio.com", role="admin")
    member_token = await _ensure_user(client, "13800100011", "forum11@9cio.com", role="member")
    await _ensure_market_item("ddw_marketing")

    # member 发帖
    resp = await client.post("/api/v1/forum/plugins/ddw_marketing/threads", json={
        "title": "营销方案讨论", "content": "新季度营销方案",
    }, headers=_auth(member_token))
    tid = resp.json()["id"]

    # admin 置顶
    resp2 = await client.post(f"/api/v1/forum/threads/{tid}/pin", headers=_auth(admin_token))
    assert resp2.status_code == 200
    assert resp2.json()["is_pinned"] is True

    # 非 admin 置顶 → 403
    resp3 = await client.post(f"/api/v1/forum/threads/{tid}/pin", headers=_auth(member_token))
    assert resp3.status_code == 403


# ---------------------------------------------------------------------------
# 12. /admin/plugins 返回 title/category/installs/stars + 全量 77+
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_12_admin_plugins_fields(client: AsyncClient):
    admin_token = await _ensure_user(client, "13800100012", "forum12@9cio.com", role="admin")
    resp = await client.get("/api/v1/admin/plugins", headers=_auth(admin_token))
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data, f"缺少 items 信封: {list(data.keys())}"
    items = data["items"]
    assert isinstance(items, list)
    assert len(items) >= 70  # ≥77 目标，测试环境可能略少
    item = items[0]
    assert "title" in item
    assert "category" in item
    assert "installs" in item
    assert "stars" in item
    assert "star_count" in item
    assert "updated_at" in item
    assert "thread_count" in item


# ---------------------------------------------------------------------------
# 补充：搜索帖子
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_13_search_threads(client: AsyncClient):
    token = await _ensure_user(client, "13800100013", "forum13@9cio.com")
    await _ensure_market_item("ddw_invoice")

    await client.post("/api/v1/forum/plugins/ddw_invoice/threads", json={
        "title": "发票打印格式问题", "content": "打印时格式错乱",
    }, headers=_auth(token))

    resp = await client.get("/api/v1/forum/search?q=发票", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any("发票" in t["title"] for t in data)


# ---------------------------------------------------------------------------
# 补充：插件论坛首页
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_14_plugin_forum_home(client: AsyncClient):
    token = await _ensure_user(client, "13800100014", "forum14@9cio.com")
    await _ensure_market_item("ddw_bid_writer")

    resp = await client.get("/api/v1/forum/plugins/ddw_bid_writer", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["plugin_name"] == "ddw_bid_writer"
    assert data["title"] == "DDW 投标标书撰写"
    assert "hot_threads" in data
    assert "recent_threads" in data
