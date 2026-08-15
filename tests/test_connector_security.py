"""假实现+安全硬伤修复测试（ddw_connector 密文存储 / ddw_esg_payment webhook 验签）。

覆盖：
1. connector：Fernet 加解密闭环 / 未配置密钥拒绝 / 注册后内部无明文 /
   缺密钥 400 / scan 解密链路
2. esg_payment：webhook 签名校验（正确 200 / 错误 401 / 未配置密钥 401）
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

ENC_KEY = Fernet.generate_key().decode()
WEBHOOK_SECRET = "test-webhook-secret"


# ---------------------------------------------------------------------------
# 1. ddw_connector 凭据密文存储
# ---------------------------------------------------------------------------


def test_connector_encrypt_decrypt_roundtrip(monkeypatch):
    """加密→解密还原完整 dict（含中文与嵌套）。"""
    monkeypatch.setenv("DDW_CONNECTOR_ENC_KEY", ENC_KEY)
    from plugins.ddw_connector.security import decrypt_conn_info, encrypt_conn_info

    conn_info = {"connection_string": "sqlite:///:memory:", "password": "p@ssw0rd中文"}
    token = encrypt_conn_info(conn_info)
    assert token != json.dumps(conn_info)  # 非明文
    assert "p@ssw0rd" not in token
    assert decrypt_conn_info(token) == conn_info


def test_connector_missing_key_rejected(monkeypatch):
    """未配置加密密钥 → 拒绝加密（fail-secure，绝不降级明文）。"""
    monkeypatch.delenv("DDW_CONNECTOR_ENC_KEY", raising=False)
    from plugins.ddw_connector.security import encrypt_conn_info

    with pytest.raises(ValueError) as exc:
        encrypt_conn_info({"password": "x"})
    assert "DDW_CONNECTOR_ENC_KEY" in str(exc.value)


def _connector_client(tmp_path, monkeypatch) -> AsyncClient:
    monkeypatch.setenv("DDW_CONNECTOR_ENC_KEY", ENC_KEY)
    from plugins.ddw_connector.router import build_router

    app = FastAPI()
    app.include_router(build_router())
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_router_create_stores_ciphertext(tmp_path, monkeypatch):
    """注册后内部注册表只存密文，不泄漏明文凭据。"""
    async with _connector_client(tmp_path, monkeypatch) as ac:
        resp = await ac.post(
            "/api/v1/plugins/ddw-connector/datasources",
            json={
                "name": "订单库",
                "ds_type": "sql_readonly",
                "conn_info": {
                    "connection_string": "sqlite:///x.db",
                    "password": "SECRET-PW-123",
                },
                "description": "测试",
            },
        )
        assert resp.status_code == 201, resp.text

    from plugins.ddw_connector import router as connector_router

    stored = list(connector_router._datasources.values())[0]
    assert "conn_info_enc" in stored
    assert "conn_info" not in stored  # 不再存明文字段
    assert "SECRET-PW-123" not in json.dumps(stored)
    assert "SECRET-PW-123" not in stored["conn_info_enc"]


async def test_router_create_missing_key_400(tmp_path, monkeypatch):
    """未配置密钥 → 注册数据源 400 + 明确文案。"""
    monkeypatch.delenv("DDW_CONNECTOR_ENC_KEY", raising=False)
    from plugins.ddw_connector.router import build_router

    app = FastAPI()
    app.include_router(build_router())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/plugins/ddw-connector/datasources",
            json={
                "name": "x",
                "ds_type": "sql_readonly",
                "conn_info": {"connection_string": "sqlite:///x.db"},
            },
        )
    assert resp.status_code == 400, resp.text
    assert "DDW_CONNECTOR_ENC_KEY" in resp.json()["detail"]


async def test_router_scan_uses_decrypted_conn(tmp_path, monkeypatch):
    """scan 走解密链路：注册（密文）→ 扫描 sqlite 数据源成功。"""
    db_path = tmp_path / "sample.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users (name) VALUES ('a')")
    conn.commit()
    conn.close()

    async with _connector_client(tmp_path, monkeypatch) as ac:
        resp = await ac.post(
            "/api/v1/plugins/ddw-connector/datasources",
            json={
                "name": "样本库",
                "ds_type": "sql_readonly",
                "conn_info": {"connection_string": f"sqlite:///{db_path}"},
            },
        )
        assert resp.status_code == 201, resp.text
        ds_id = resp.json()["id"]

        scan = await ac.post(f"/api/v1/plugins/ddw-connector/datasources/{ds_id}/scan")
        assert scan.status_code == 200, scan.text
        tables = [t["name"] for t in scan.json()["tables"]]
        assert "users" in tables


# ---------------------------------------------------------------------------
# 2. ddw_esg_payment webhook 签名校验
# ---------------------------------------------------------------------------


def _webhook_sig(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def test_webhook_verify_signature_unit(monkeypatch):
    """签名校验单元：正确/错误/缺密钥。"""
    monkeypatch.setenv("DDW_ESG_PAYMENT_WEBHOOK_SECRET", WEBHOOK_SECRET)
    from plugins.ddw_esg_payment.payment_gateway import verify_webhook_signature

    payload = b'{"order_id": "1", "paid": true}'
    assert verify_webhook_signature(payload, _webhook_sig(payload)) is True
    assert verify_webhook_signature(payload, "deadbeef") is False
    assert verify_webhook_signature(payload, "") is False

    monkeypatch.delenv("DDW_ESG_PAYMENT_WEBHOOK_SECRET", raising=False)
    assert verify_webhook_signature(payload, _webhook_sig(payload)) is False


async def test_webhook_endpoint_valid_signature_200(monkeypatch):
    """配置密钥 + 正确签名 → 200（幂等安全行为）。"""
    monkeypatch.setenv("DDW_ESG_PAYMENT_WEBHOOK_SECRET", WEBHOOK_SECRET)
    from plugins.ddw_esg_payment.routes import register_routes

    app = FastAPI()
    register_routes(app.router)
    payload = b'{"test": true}'
    headers = {"signature": _webhook_sig(payload), "content-type": "application/json"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/webhook/wechat", content=payload, headers=headers)
        assert resp.status_code == 200, resp.text
        resp2 = await ac.post("/webhook/alipay", content=payload, headers=headers)
        assert resp2.status_code == 200, resp2.text


async def test_webhook_endpoint_invalid_signature_401(monkeypatch):
    """错误签名 → 401 + 明确文案。"""
    monkeypatch.setenv("DDW_ESG_PAYMENT_WEBHOOK_SECRET", WEBHOOK_SECRET)
    from plugins.ddw_esg_payment.routes import register_routes

    app = FastAPI()
    register_routes(app.router)
    payload = b'{"test": true}'

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/webhook/wechat",
            content=payload,
            headers={"signature": "forged-sig", "content-type": "application/json"},
        )
    assert resp.status_code == 401, resp.text
    assert "签名校验失败" in resp.json()["detail"]


async def test_webhook_endpoint_missing_secret_401(monkeypatch):
    """未配置密钥 → 拒绝一切回调（fail-secure，防伪造支付成功）。"""
    monkeypatch.delenv("DDW_ESG_PAYMENT_WEBHOOK_SECRET", raising=False)
    from plugins.ddw_esg_payment.routes import register_routes

    app = FastAPI()
    register_routes(app.router)
    payload = b'{"test": true}'

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/webhook/wechat",
            content=payload,
            headers={
                "signature": _webhook_sig(payload),
                "content-type": "application/json",
            },
        )
    assert resp.status_code == 401, resp.text
    assert "DDW_ESG_PAYMENT_WEBHOOK_SECRET" in resp.json()["detail"]
