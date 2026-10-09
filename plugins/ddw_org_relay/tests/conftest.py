"""org_relay 插件测试夹具：独立 DB、令牌、限速隔离。"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _org_relay_env(tmp_path, monkeypatch):
    """每测试：独立 DB 文件 + 固定令牌 + 宽松限速（限速专项用例单独收紧）。"""
    monkeypatch.setenv("DDW_ORG_RELAY_DB", str(tmp_path / "org_relay_test.db"))
    monkeypatch.setenv("DDW_ORG_RELAY_ENABLED", "1")
    monkeypatch.setenv("DDW_ORG_RELAY_PRODUCT_TOKENS", "prod-token-a,prod-token-b")
    monkeypatch.setenv("DDW_ORG_RELAY_SERVER_BASE_URL", "")
    monkeypatch.setenv("DDW_ORG_RELAY_RATE_LIMIT", "1000")
    from plugins.ddw_org_relay import router as org_router

    org_router.reset_rate_buckets()
    yield
    org_router.reset_rate_buckets()
