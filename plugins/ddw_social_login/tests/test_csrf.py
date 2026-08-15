"""CSRF state 测试 —— T3（伪造 state → 401）。"""

from __future__ import annotations


from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# T3: GET /callback/dingtalk?code=test&state=invalid_state → 401 INVALID_STATE
# ---------------------------------------------------------------------------


class TestT3_InvalidState:
    """T3: 伪造/过期的 state 应返回 401。"""

    def test_callback_invalid_state(self, client: TestClient):
        """state 不存在于缓存 → 401 INVALID_STATE。"""
        resp = client.get(
            "/api/v1/plugins/ddw-social-login/callback/dingtalk",
            params={"code": "test_code", "state": "completely_invalid_state"},
            follow_redirects=False,
        )
        assert resp.status_code == 401
        detail = resp.json()
        assert detail["detail"]["code"] == "INVALID_STATE"

    def test_callback_expired_state(self, client: TestClient):
        """state 已过期（被 pop 掉后再次使用）→ 401。"""
        # 注入一个 state 然后手动删除模拟过期
        from plugins.ddw_social_login import services as svc

        svc._state_cache["expired_state_123"] = {"provider": "dingtalk", "created_at": "2026-01-01"}
        # 第一次使用（会 pop）
        svc._state_cache.pop("expired_state_123", None)

        # 第二次使用 → 应该 401
        resp = client.get(
            "/api/v1/plugins/ddw-social-login/callback/dingtalk",
            params={"code": "test_code", "state": "expired_state_123"},
            follow_redirects=False,
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "INVALID_STATE"

    def test_callback_empty_state(self, client: TestClient):
        """空 state → 422（FastAPI 验证失败）。"""
        resp = client.get(
            "/api/v1/plugins/ddw-social-login/callback/dingtalk",
            params={"code": "test_code"},
            follow_redirects=False,
        )
        # 缺少 state 参数 → 422 Unprocessable Entity
        assert resp.status_code == 422


class TestStateCache:
    """测试 state 缓存行为。"""

    def test_state_is_one_time_use(self, client: TestClient):
        """state 使用后应从缓存中删除（一次性）。"""
        from plugins.ddw_social_login import services as svc

        # 注入 state
        svc._state_cache["onetime_state"] = {"provider": "dingtalk", "created_at": "2026-01-01"}

        # 确认存在
        assert "onetime_state" in svc._state_cache

        # 第一次回调（即使后续步骤失败，state 也应该被 pop）
        client.get(
            "/api/v1/plugins/ddw-social-login/callback/dingtalk",
            params={"code": "test_code", "state": "onetime_state"},
            follow_redirects=False,
        )
        # state 应已被删除
        assert "onetime_state" not in svc._state_cache
