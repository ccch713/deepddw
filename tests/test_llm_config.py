"""LLM 配置/测试端点测试（鉴权开发说明 §3：key 不回明文 + LAN 免密/Token 双模式）。"""

from __future__ import annotations

import json
import os
import stat


os.environ.setdefault("DDW_ACCESS_TOKEN", "test-llm-config-token")


_LLM_CONFIG = "/api/v1/llm/config"
_LLM_TEST = "/api/v1/llm/test"


def _token() -> dict:
    return {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}


def _lan() -> dict:
    """内网来源头（LAN 免密场景）。"""
    return {"X-Forwarded-For": "192.168.1.5"}


def _external() -> dict:
    """外网来源头。"""
    return {"X-Forwarded-For": "8.8.8.8"}


# ---------------------------------------------------------------------------
# 鉴权：无 Token / Token / LAN 免密 / 外网 / 关闭免密
# ---------------------------------------------------------------------------


async def test_config_no_token_401(client):
    resp = await client.get(_LLM_CONFIG)
    assert resp.status_code == 401


async def test_config_external_no_token_401(client):
    resp = await client.get(_LLM_CONFIG, headers=_external())
    assert resp.status_code == 401


async def test_config_external_with_token_200(client):
    resp = await client.get(_LLM_CONFIG, headers={**_external(), **_token()})
    assert resp.status_code == 200


async def test_config_lan_no_token_200(client, monkeypatch):
    """内网（X-Forwarded-For 私有段）无 Token → LAN 免密放行。"""
    monkeypatch.setenv("DDW_LAN_BYPASS", "1")
    resp = await client.get(_LLM_CONFIG, headers=_lan())
    assert resp.status_code == 200


async def test_config_lan_bypass_disabled_requires_token(client, monkeypatch):
    """DDW_LAN_BYPASS=0 时内网无 Token 也 401（安全关闭生效）。"""
    monkeypatch.setenv("DDW_LAN_BYPASS", "0")
    resp = await client.get(_LLM_CONFIG, headers=_lan())
    assert resp.status_code == 401
    resp2 = await client.get(_LLM_CONFIG, headers={**_lan(), **_token()})
    assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# key 安全红线：GET 不回明文；POST 写 600 配置
# ---------------------------------------------------------------------------


async def test_config_get_no_plaintext_key(client):
    resp = await client.get(_LLM_CONFIG, headers=_token())
    assert resp.status_code == 200
    body = json.dumps(resp.json(), ensure_ascii=False)
    # 绝不出现明文 key 形态（sk-* / api_key 值）
    assert "sk-" not in body
    assert '"api_key"' not in body
    data = resp.json()
    assert "providers" in data
    for name, p in data["providers"].items():
        assert "has_key" in p  # 只回布尔
        assert isinstance(p["has_key"], bool)


async def test_config_post_saves_key_600(client, tmp_path, monkeypatch):
    """POST /config 写 key 到部署配置（权限 600），响应不回显 key。"""
    import core.api.llm as llm_mod

    target = tmp_path / "deployment.yaml"
    monkeypatch.setattr(llm_mod, "_DEPLOYMENT_YAML", target)

    resp = await client.post(
        _LLM_CONFIG,
        headers=_token(),
        json={
            "provider": "deepseek",
            "api_key": "sk-llm-config-test-123456",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["key_saved"] is True
    assert "sk-" not in json.dumps(data)  # 响应不回显 key

    # 文件已写、权限 600、key 落盘（供重启后加载）
    assert target.exists()
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600, hex(mode)
    content = target.read_text(encoding="utf-8")
    assert "sk-llm-config-test-123456" in content
    assert "deepseek" in content


async def test_config_post_invalid_provider_400(client):
    resp = await client.post(
        _LLM_CONFIG,
        headers=_token(),
        json={"provider": "minimax", "api_key": "x"},
    )
    assert resp.status_code == 400


async def test_config_post_without_key_does_not_erase(client, tmp_path, monkeypatch):
    """只改 base_url 不传 key → 不覆盖已有 key。"""
    import core.api.llm as llm_mod

    target = tmp_path / "deployment.yaml"
    monkeypatch.setattr(llm_mod, "_DEPLOYMENT_YAML", target)
    target.write_text(
        "llm_gateway:\n  providers:\n    deepseek:\n      api_key: keep-me\n",
        encoding="utf-8",
    )

    resp = await client.post(
        _LLM_CONFIG, headers=_token(),
        json={"provider": "deepseek", "base_url": "https://api.deepseek.com/v1"},
    )
    assert resp.status_code == 200
    assert "keep-me" in target.read_text(encoding="utf-8")  # 原 key 未动


# ---------------------------------------------------------------------------
# /test 端点
# ---------------------------------------------------------------------------


async def test_test_endpoint_structure_no_plaintext(client, monkeypatch):
    """POST /test：结构 {ok, provider, model, error}，不含 key；mock 真实 LLM。"""
    import core.api.llm as llm_mod
    from core.llm_gateway.base import ChatResponse

    async def fake_chat(messages, **kwargs):
        return ChatResponse(
            content="pong", model="deepseek-chat",
            provider="deepseek", finish_reason="stop",
        )

    monkeypatch.setattr(llm_mod, "llm_chat", fake_chat)

    resp = await client.post(_LLM_TEST, headers=_token(), json={"provider": "deepseek"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["provider"] == "deepseek"
    assert "model" in data
    assert "error" in data
    assert "sk-" not in json.dumps(data)


async def test_test_endpoint_no_token_401(client):
    resp = await client.post(_LLM_TEST, json={"provider": "deepseek"})
    assert resp.status_code == 401
