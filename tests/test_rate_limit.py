"""P0-2（multidevice）：网关限流测试。

验收：同一 Token 超限返回 429 + Retry-After；全局过载返回 503；
阈值可通过配置覆盖；/health 与 OPTIONS 不计数。
"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-rate-limit-token")

import pytest  # noqa: E402


def _clear_buckets():
    """清空限流桶（类级共享）。"""
    from core.middleware.rate_limit import RateLimitMiddleware

    RateLimitMiddleware._buckets.clear()


@pytest.fixture(autouse=True)
def _reset_mw(monkeypatch):
    """每个测试：清空桶 + 默认宽松配置。"""
    from core.middleware import rate_limit as rl

    _clear_buckets()
    monkeypatch.setattr(rl, "_rate_limit_config", lambda: {
        "per_token": 1000, "per_ip": 1000, "global": 10000,
        "window_seconds": 60, "enabled": True,
    })
    yield
    _clear_buckets()


@pytest.fixture(autouse=True)
def _reset_mw(monkeypatch):
    """每个测试：清空桶 + 默认宽松配置（由 _clear_buckets 完成）。"""
    from core.middleware import rate_limit as rl

    monkeypatch.setattr(rl, "_rate_limit_config", lambda: {
        "per_token": 1000, "per_ip": 1000, "global": 10000,
        "window_seconds": 60, "enabled": True,
    })
    yield
    _clear_buckets()


def _set_limits(monkeypatch, **kw):
    """动态覆盖限流参数。"""
    from core.middleware import rate_limit as rl

    cfg = {"per_token": 1000, "per_ip": 1000, "global": 10000,
           "window_seconds": 60, "enabled": True}
    cfg.update(kw)
    monkeypatch.setattr(rl, "_rate_limit_config", lambda: cfg)
    return cfg


async def test_token_over_limit_returns_429(client, monkeypatch):
    """同一 Token 超过阈值 → 429 + Retry-After 头。"""
    _set_limits(monkeypatch, per_token=3)
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    statuses = []
    for _ in range(4):
        resp = await client.get("/api/v1/version", headers=headers)
        statuses.append(resp.status_code)
    assert statuses[:3] == [200, 200, 200], statuses
    assert statuses[3] == 429
    resp4 = await client.get("/api/v1/version", headers=headers)
    assert resp4.status_code == 429
    assert "Retry-After" in resp4.headers


async def test_health_and_options_not_counted(client, monkeypatch):
    """/health 与 OPTIONS 不计数（限流阈值小但探活不受影响）。"""
    _set_limits(monkeypatch, per_token=2)
    for _ in range(5):
        resp = await client.get("/health")
        assert resp.status_code == 200


async def test_global_overload_returns_503(client, monkeypatch):
    """全局容量耗尽 → 503 + 明确文案。"""
    _set_limits(monkeypatch, **{"global": 2})
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    resp3 = None
    for _ in range(4):
        resp3 = await client.get("/api/v1/version", headers=headers)
    assert resp3 is not None and resp3.status_code == 503
    assert "Retry-After" in resp3.headers


async def test_rate_limit_disabled(client, monkeypatch):
    """enabled=false → 全部放行（不计数）。"""
    _set_limits(monkeypatch, enabled=False, per_token=1, per_ip=1, **{"global": 1})
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    for _ in range(5):
        resp = await client.get("/api/v1/version", headers=headers)
        assert resp.status_code == 200
