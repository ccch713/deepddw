"""DDW 渠道授权与结算插件 — 最简导入 + 健康检查测试。"""

from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_health_endpoint_returns_ok(client):
    """健康检查端点返回 200 + ok status。"""
    resp = await client.get("/api/v1/plugins/ddw-channel-auth/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plugin"] == "ddw-channel-auth"
    assert data["version"] == "1.0.0"
    assert data["status"] == "ok"


@pytest.mark.anyio
async def test_modules_importable():
    """所有模块可导入，无语法错误。"""
    from plugins.ddw_channel_auth import PLUGIN_NAME, VERSION

    assert PLUGIN_NAME == "ddw-channel-auth"
    assert VERSION == "1.0.0"
