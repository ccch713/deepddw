"""org_relay 路由级测试：协议端点矩阵（401/403/404/409/410/429）+ 成员 chat。"""

from __future__ import annotations

import time
from typing import Any, Dict

import httpx
import pytest
from fastapi import FastAPI

from core.llm_gateway.base import ChatResponse
from plugins.ddw_org_relay import router as org_router
from plugins.ddw_org_relay import service

PUB = "/api/v1/relay/org/pub"
PLUGIN = "/api/v1/plugins/ddw-org-relay"
PRODUCT = {"Authorization": "Bearer prod-token-a"}
ADMIN = {"Authorization": "Bearer test-token-deepddw"}  # 根 conftest 设定


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setattr(service, "available_models", lambda: ["mock-model-x"])
    app = FastAPI()
    app.include_router(org_router.build_router())
    return app


@pytest.fixture()
async def client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://testserver") as c:
        yield c


@pytest.fixture(autouse=True)
def _fake_gateway(monkeypatch):
    """网关替身：不出网，返回确定响应。"""

    async def fake_chat(messages, **kwargs):
        return ChatResponse(
            content="hello from deployer-configured gateway",
            model="mock-model-x", provider="deepseek",
            tokens_in=7, tokens_out=11, cost=0.0, latency_ms=5, finish_reason="stop",
        )

    async def fake_stream(messages, **kwargs):
        for tok in ["Hel", "lo ", "world"]:
            yield tok

    monkeypatch.setattr(org_router.llm_gateway, "chat", fake_chat)
    monkeypatch.setattr(org_router.llm_gateway, "stream_chat", fake_stream)


async def _create_org(client, name="Acme", **kw) -> Dict[str, Any]:
    r = await client.post(f"{PLUGIN}/admin/orgs", json={"name": name, **kw}, headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()


async def _issue_code(client, org_id, **kw) -> str:
    r = await client.post(f"{PLUGIN}/admin/orgs/{org_id}/bindcode", json=kw or {}, headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["codes"][0]


# ---------------- 鉴权与限速 ----------------

async def test_pub_endpoints_require_product_token(client):
    for method, path in (("post", f"{PUB}/bind"), ("post", f"{PUB}/unbind"), ("get", f"{PUB}/me")):
        call = getattr(client, method)
        if method == "post":
            r = await call(path, json={})
        else:
            r = await call(path)
        assert r.status_code == 401, (path, r.status_code)


async def test_pub_wrong_token_401(client):
    r = await client.post(f"{PUB}/bind", json={"user_id": "u", "code": "x"},
                    headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


async def test_x_product_key_header_accepted(client):
    org = await _create_org(client)
    code = await _issue_code(client, org["org_id"])
    r = await client.post(f"{PUB}/bind", json={"user_id": "u1", "code": code},
                    headers={"X-Product-Key": "prod-token-b"})
    assert r.status_code == 200 and r.json()["bound"] is True


async def test_rate_limit_429(client, monkeypatch):
    monkeypatch.setenv("DDW_ORG_RELAY_RATE_LIMIT", "3")
    org_router.reset_rate_buckets()
    ok = 0
    last = None
    for _ in range(4):
        r = await client.get(f"{PUB}/me", params={"user_id": "u"}, headers=PRODUCT)
        last = r
        if r.status_code == 429:
            break
        ok += 1
    assert last.status_code == 429 and ok == 3
    assert "retry-after" in {k.lower() for k in last.headers}


async def test_admin_requires_instance_token(client):
    r = await client.post(f"{PLUGIN}/admin/orgs", json={"name": "X"})
    assert r.status_code == 401
    r = await client.post(f"{PLUGIN}/admin/orgs", json={"name": "X"},
                    headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


# ---------------- 协议三件全链路 ----------------

async def test_full_protocol_flow(client):
    org = await _create_org(client, "Acme Clinic", plan="light")
    assert org["org_secret"] and org["org_id"].startswith("org_")
    code = await _issue_code(client, org["org_id"], ttl_min=15, max_uses=5)

    # bind：org 对象含 §3.1 可选字段
    r = await client.post(f"{PUB}/bind", json={"user_id": "staff-1", "code": code}, headers=PRODUCT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bound"] is True
    o = body["org"]
    assert o["org_id"] == org["org_id"] and o["name"] == "Acme Clinic" and o["plan"] == "light"
    assert o["server_base_url"].startswith("http") and o["server_base_url"].endswith(PLUGIN)
    assert o["access_token"].startswith("orgm_")
    assert o["models"] == ["mock-model-x"]
    assert "org_secret" not in o  # org_secret 永不出现在响应
    access_token = o["access_token"]

    # me
    r = await client.get(f"{PUB}/me", params={"user_id": "staff-1"}, headers=PRODUCT)
    assert r.status_code == 200
    me = r.json()
    assert me["bound"] is True and me["org_consumed_total"] == 0

    # 成员令牌直连本实例 LLM 端点（OpenAI 兼容形状）
    r = await client.post(f"{PLUGIN}/chat/completions",
                    json={"messages": [{"role": "user", "content": "hi"}]},
                    headers={"Authorization": f"Bearer {access_token}"})
    assert r.status_code == 200, r.text
    chat = r.json()
    assert chat["object"] == "chat.completion"
    assert chat["choices"][0]["message"]["role"] == "assistant"
    assert chat["usage"]["total_tokens"] == 18

    # 用量进入组织对账
    r = await client.get(f"{PUB}/me", params={"user_id": "staff-1"}, headers=PRODUCT)
    assert r.json()["org_consumed_total"] == 1

    # unbind → me 回未绑定；成员令牌立即失效
    r = await client.post(f"{PUB}/unbind", json={"user_id": "staff-1"}, headers=PRODUCT)
    assert r.status_code == 200 and r.json() == {"bound": False}
    r = await client.get(f"{PUB}/me", params={"user_id": "staff-1"}, headers=PRODUCT)
    assert r.json()["bound"] is False
    r = await client.post(f"{PLUGIN}/chat/completions",
                    json={"messages": [{"role": "user", "content": "hi"}]},
                    headers={"Authorization": f"Bearer {access_token}"})
    assert r.status_code == 401


async def test_stream_chat(client):
    org = await _create_org(client)
    code = await _issue_code(client, org["org_id"])
    r = await client.post(f"{PUB}/bind", json={"user_id": "u", "code": code}, headers=PRODUCT)
    token = r.json()["org"]["access_token"]
    async with client.stream("POST", f"{PLUGIN}/chat/completions",
                             json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
                             headers={"Authorization": f"Bearer {token}"}) as r:
        assert r.status_code == 200
        body = b"".join([chunk async for chunk in r.aiter_raw()])
    assert b"chat.completion.chunk" in body and b"[DONE]" in body


# ---------------- 错误码矩阵 ----------------

async def test_malformed_code_403(client):
    await _create_org(client)
    r = await client.post(f"{PUB}/bind", json={"user_id": "u", "code": "garbage"}, headers=PRODUCT)
    assert r.status_code == 403


async def test_forged_signature_403(client):
    org = await _create_org(client)
    await _issue_code(client, org["org_id"])
    r = await client.post(f"{PUB}/bind",
                    json={"user_id": "u", "code": "DDWORG-b3JnX2FiY2QzNGVm.0000000000000000"},
                    headers=PRODUCT)
    assert r.status_code == 403


async def test_expired_code_410(client):
    org = await _create_org(client)
    code = await _issue_code(client, org["org_id"], ttl_min=1)
    # 直接把库中该码的 exp_ts 回拨到过去（码内嵌 exp_ts 同步重签）
    from plugins.ddw_org_relay import store, bindcode as bc
    with store.get_conn() as conn:
        row = conn.execute("SELECT * FROM orgs WHERE org_id=?", (org["org_id"],)).fetchone()
        secret = store.row_to_org(row, with_secret=True)["secret"]
        past = int(time.time()) - 5
        expired = bc.issue_code(org["org_id"], secret, past)
        conn.execute("UPDATE org_codes SET code=?, exp_ts=? WHERE code=?", (expired, past, code))
    r = await client.post(f"{PUB}/bind", json={"user_id": "u", "code": expired}, headers=PRODUCT)
    assert r.status_code == 410


async def test_exhausted_code_409(client):
    org = await _create_org(client)
    code = await _issue_code(client, org["org_id"], max_uses=1)
    r1 = await client.post(f"{PUB}/bind", json={"user_id": "a", "code": code}, headers=PRODUCT)
    r2 = await client.post(f"{PUB}/bind", json={"user_id": "b", "code": code}, headers=PRODUCT)
    assert r1.status_code == 200 and r2.status_code == 409


async def test_revoked_code_404(client):
    org = await _create_org(client)
    code = await _issue_code(client, org["org_id"])
    r = await client.post(f"{PLUGIN}/admin/orgs/{org['org_id']}/revoke-codes",
                    json={"code": code}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["revoked"] == 1
    r = await client.post(f"{PUB}/bind", json={"user_id": "a", "code": code}, headers=PRODUCT)
    assert r.status_code == 404


async def test_already_bound_other_org_409(client):
    org1, org2 = await _create_org(client, "A"), await _create_org(client, "B")
    c1, c2 = await _issue_code(client, org1["org_id"]), await _issue_code(client, org2["org_id"])
    r1 = await client.post(f"{PUB}/bind", json={"user_id": "u", "code": c1}, headers=PRODUCT)
    r2 = await client.post(f"{PUB}/bind", json={"user_id": "u", "code": c2}, headers=PRODUCT)
    assert r1.status_code == 200 and r2.status_code == 409


async def test_org_quota_429_on_chat(client):
    org = await _create_org(client, quota_requests=1)
    code = await _issue_code(client, org["org_id"])
    r = await client.post(f"{PUB}/bind", json={"user_id": "u", "code": code}, headers=PRODUCT)
    token = r.json()["org"]["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}
    first = await client.post(f"{PLUGIN}/chat/completions",
                              json={"messages": [{"role": "user", "content": "1"}]}, headers=hdr)
    second = await client.post(f"{PLUGIN}/chat/completions",
                               json={"messages": [{"role": "user", "content": "2"}]}, headers=hdr)
    assert first.status_code == 200 and second.status_code == 429


async def test_bad_role_400(client):
    org = await _create_org(client)
    code = await _issue_code(client, org["org_id"])
    r = await client.post(f"{PUB}/bind", json={"user_id": "u", "code": code}, headers=PRODUCT)
    token = r.json()["org"]["access_token"]
    r = await client.post(f"{PLUGIN}/chat/completions",
                    json={"messages": [{"role": "wizard", "content": "x"}]},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


# ---------------- 管理端 ----------------

async def test_admin_org_lifecycle_and_rotation(client):
    org = await _create_org(client, "Rotate Co")
    code = await _issue_code(client, org["org_id"], ttl_min=30)
    rotated = (await client.post(f"{PLUGIN}/admin/orgs/{org['org_id']}/rotate-secret",
                                 headers=ADMIN)).json()
    assert rotated["org_secret"] != org["org_secret"]
    # 轮换后旧码时效内仍有效
    r = await client.post(f"{PUB}/bind", json={"user_id": "u", "code": code}, headers=PRODUCT)
    assert r.status_code == 200

    detail = (await client.get(f"{PLUGIN}/admin/orgs/{org['org_id']}", headers=ADMIN)).json()
    assert detail["org"]["org_id"] == org["org_id"] and detail["members"]
    assert all("secret" not in m for m in detail["members"])

    usage = (await client.get(f"{PLUGIN}/admin/usage", params={"org_id": org["org_id"]},
                              headers=ADMIN)).json()
    assert usage["total"] == 1

    # 管理员强制解绑
    r = await client.post(f"{PLUGIN}/admin/unbind", json={"user_id": "u"}, headers=ADMIN)
    assert r.json() == {"bound": False}
    me = await client.get(f"{PUB}/me", params={"user_id": "u"}, headers=PRODUCT)
    assert me.json()["bound"] is False


async def test_health_declares_protocol_version(client):
    r = await client.get(f"{PLUGIN}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["protocol"] == "bindcode" and body["protocol_version"] == "1"


async def test_server_base_url_config_override(client, monkeypatch):
    monkeypatch.setenv("DDW_ORG_RELAY_SERVER_BASE_URL", "https://ddw.example.co")
    org = await _create_org(client)
    code = await _issue_code(client, org["org_id"])
    body = (await client.post(f"{PUB}/bind", json={"user_id": "u", "code": code},
                              headers=PRODUCT)).json()
    assert body["org"]["server_base_url"] == "https://ddw.example.co"
