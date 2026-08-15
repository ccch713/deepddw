"""API 端点测试 —— T1/T2/T5/T6/T7/T8。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# T1: GET /auth/dingtalk（钉钉未配置）→ 400 CHANNEL_NOT_CONFIGURED
# ---------------------------------------------------------------------------


class TestT1_AuthNotConfigured:
    """T1: 未配置的通道应返回 400。"""

    def test_auth_qq_not_configured(self, client: TestClient, config_manager):
        """qq 通道未配置 appid → 400。"""
        # 确保 qq 通道的 appid 为空
        config_manager._config.setdefault("channels", {})["qq"] = {
            "enabled": False,
            "appid": None,
            "app_secret": None,
        }
        resp = client.get("/api/v1/plugins/ddw-social-login/auth/qq", follow_redirects=False)
        assert resp.status_code == 400
        detail = resp.json()
        assert detail["detail"]["code"] == "CHANNEL_NOT_CONFIGURED"

    def test_auth_invalid_provider(self, client: TestClient):
        """无效 provider → 400。"""
        resp = client.get("/api/v1/plugins/ddw-social-login/auth/invalid", follow_redirects=False)
        # 即使 provider 无效，也应返回 CHANNEL_NOT_CONFIGURED
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T2: POST /config → GET /auth/dingtalk → 302 redirect
# ---------------------------------------------------------------------------


class TestT2_ConfigThenAuth:
    """T2: 保存配置后，auth 应返回 302。"""

    @patch("plugins.ddw_social_login.services._state_cache")
    @patch("senweaver_oauth.AuthRequest")
    def test_config_save_then_auth_redirect(
        self, mock_auth_req_cls, mock_state_cache, client: TestClient, config_manager
    ):
        """保存钉钉配置后，GET /auth/dingtalk 应 302 到 oauth.dingtalk.com。"""
        # Mock state cache
        mock_state_cache.__setitem__ = MagicMock()
        mock_state_cache.__contains__ = MagicMock(return_value=False)

        # Mock AuthRequest.build().authorize() 返回 URL
        mock_auth_instance = MagicMock()
        mock_auth_instance.authorize.return_value = "https://oauth.dingtalk.com/connect/qrconnect?appid=xxx"
        mock_auth_req_cls.build.return_value = mock_auth_instance

        resp = client.get("/api/v1/plugins/ddw-social-login/auth/dingtalk", follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers.get("location", "")
        assert "oauth.dingtalk.com" in location


# ---------------------------------------------------------------------------
# T5: 同一 openid 第二次扫码登录 → 不重复创建 User
# ---------------------------------------------------------------------------


class TestT5_SecondLoginNoDuplicate:
    """T5: 同一 openid 第二次扫码登录 → 不重复创建 User。"""

    @pytest.mark.asyncio
    @patch("plugins.ddw_social_login.services.create_access_token", return_value="test_token_abc")
    @patch("plugins.ddw_social_login.services._write_login_audit", new_callable=AsyncMock)
    @patch("plugins.ddw_social_login.services.session_scope")
    @patch("plugins.ddw_social_login.services.asyncio.to_thread")
    async def test_second_login_reuses_user(
        self,
        mock_to_thread,
        mock_session_scope,
        mock_audit,
        mock_create_token,
        app,
        config_manager,
        mock_auth_response_success,
        mock_social_user,
        seeded_db,
    ):
        """第二次扫码应复用已有 User，不新建。"""
        from contextlib import asynccontextmanager
        from httpx import AsyncClient, ASGITransport
        from core.database.models import User, UserBinding

        # 先创建一个用户和绑定
        user = User(
            phone="wx_test_openid_1234",
            password_hash="hashed",
            name="测试用户",
            role="member",
            status="active",
            tenant_id=1,
        )
        seeded_db.add(user)
        await seeded_db.flush()

        binding = UserBinding(
            user_id=user.id,
            tenant_id=1,
            provider="dingtalk",
            provider_uid="test_openid_1234567890abcdef",
            provider_name="测试用户",
            binding_type="login",
            is_primary=True,
            is_active=True,
        )
        seeded_db.add(binding)
        await seeded_db.commit()

        # Mock session_scope 返回测试 session
        @asynccontextmanager
        async def _mock_session_scope():
            yield seeded_db

        mock_session_scope.side_effect = _mock_session_scope

        # Mock to_thread 返回成功响应
        async def _mock_to_thread(func, *args):
            return mock_auth_response_success

        mock_to_thread.side_effect = _mock_to_thread

        # 注入有效 state 到缓存
        from plugins.ddw_social_login import services as svc

        svc._state_cache["valid_state_t5"] = {"provider": "dingtalk", "created_at": "2026-01-01"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/plugins/ddw-social-login/callback/dingtalk",
                params={"code": "test_code", "state": "valid_state_t5"},
                follow_redirects=False,
            )
        # 应成功重定向（带 token）
        assert resp.status_code == 302
        assert "access_token=" in resp.headers.get("location", "")


# ---------------------------------------------------------------------------
# T6: POST /config 保存后 GET /config → secret 脱敏
# ---------------------------------------------------------------------------


class TestT6_ConfigSecretMasked:
    """T6: GET /config 应返回脱敏的 secret。"""

    def test_config_secret_masked(self, app, config_manager):
        """保存配置后查看，secret 应被脱敏。"""
        from fastapi.testclient import TestClient
        from core.auth.jwt import current_admin

        # 用 dependency_overrides 覆盖 admin 认证
        async def _mock_admin():
            return {"user_id": 1, "tenant_id": 1, "role": "admin"}

        app.dependency_overrides[current_admin] = _mock_admin
        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/v1/plugins/ddw-social-login/config")
                assert resp.status_code == 200
                data = resp.json()
                # 找到 dingtalk 通道
                dingtalk_cfg = next(ch for ch in data if ch["provider"] == "dingtalk")
                # secret 应被脱敏：前4位 + ****
                assert dingtalk_cfg["app_secret"].endswith("****")
                assert dingtalk_cfg["app_secret"] == "ding****"
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# T7: POST /bind/wechat_open（已登录用户绑定）
# ---------------------------------------------------------------------------


class TestT7_BindProvider:
    """T7: 已登录用户绑定第三方。"""

    @patch("plugins.ddw_social_login.services.session_scope")
    @patch("plugins.ddw_social_login.services.asyncio.to_thread")
    def test_bind_wechat_success(
        self,
        mock_to_thread,
        mock_session_scope,
        app,
        config_manager,
        mock_auth_response_success,
        seeded_db,
    ):
        """绑定微信应成功。"""
        from contextlib import asynccontextmanager
        from fastapi.testclient import TestClient
        from core.auth.jwt import current_user

        # Mock current_user via dependency_overrides
        async def _mock_user():
            return {"user_id": 100, "tenant_id": 1, "role": "member"}

        app.dependency_overrides[current_user] = _mock_user

        # Mock session_scope
        @asynccontextmanager
        async def _mock_session_scope():
            yield seeded_db

        mock_session_scope.side_effect = _mock_session_scope

        # Mock to_thread 返回成功
        async def _mock_to_thread(func, *args):
            return mock_auth_response_success

        mock_to_thread.side_effect = _mock_to_thread

        # 注入 state
        from plugins.ddw_social_login import services as svc

        svc._state_cache["bind_state_1"] = {"provider": "wechat_open", "created_at": "2026-01-01"}

        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post(
                    "/api/v1/plugins/ddw-social-login/bind/wechat_open",
                    params={"code": "test_code", "state": "bind_state_1"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["ok"] is True
                assert data["provider"] == "wechat_open"
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# T8: DELETE /bind/wechat_open（解绑）
# ---------------------------------------------------------------------------


class TestT8_UnbindProvider:
    """T8: 解绑第三方账号。"""

    @patch("plugins.ddw_social_login.services.session_scope")
    def test_unbind_wechat_success(
        self,
        mock_session_scope,
        app,
        seeded_db,
    ):
        """解绑微信应成功。"""
        from contextlib import asynccontextmanager
        from fastapi.testclient import TestClient
        from core.auth.jwt import current_user
        from core.database.models import UserBinding

        # Mock current_user via dependency_overrides
        async def _mock_user():
            return {"user_id": 100, "tenant_id": 1, "role": "member"}

        app.dependency_overrides[current_user] = _mock_user

        # 先创建一个绑定记录
        binding = UserBinding(
            user_id=100,
            tenant_id=1,
            provider="wechat_open",
            provider_uid="wx_openid_123",
            provider_name="微信用户",
            binding_type="login",
            is_primary=False,
            is_active=True,
        )
        seeded_db.add(binding)
        seeded_db.commit()

        # Mock session_scope
        @asynccontextmanager
        async def _mock_session_scope():
            yield seeded_db

        mock_session_scope.side_effect = _mock_session_scope

        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.delete("/api/v1/plugins/ddw-social-login/bind/wechat_open")
                assert resp.status_code == 200
                data = resp.json()
                assert data["ok"] is True
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 额外：GET /channels 测试
# ---------------------------------------------------------------------------


class TestChannels:
    """测试通道列表端点。"""

    def test_get_channels(self, client: TestClient):
        """应返回全部 4 个通道的状态。"""
        resp = client.get("/api/v1/plugins/ddw-social-login/channels")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4
        providers = {c["provider"] for c in data}
        assert providers == {"wechat_open", "qq", "dingtalk", "feishu"}

    def test_channels_display_names(self, client: TestClient):
        """每个通道应有正确的 display_name。"""
        resp = client.get("/api/v1/plugins/ddw-social-login/channels")
        data = resp.json()
        name_map = {c["provider"]: c["display_name"] for c in data}
        assert name_map["wechat_open"] == "微信扫码"
        assert name_map["qq"] == "QQ 登录"
        assert name_map["dingtalk"] == "钉钉登录"
        assert name_map["feishu"] == "飞书登录"




# ---------------------------------------------------------------------------
# T9: GET /auth/dingtalk?next=/wenqu/student.html → next 存入 state 缓存
# ---------------------------------------------------------------------------


class TestT9_NextParamStored:
    """T9: next 参数应存入 state 缓存。"""

    @patch("plugins.ddw_social_login.services._state_cache", new_callable=dict)
    @patch("senweaver_oauth.AuthRequest")
    def test_next_stored_in_state_cache(
        self, mock_auth_req_cls, mock_state_cache, client: TestClient, config_manager
    ):
        """GET /auth/dingtalk?next=/wenqu/student.html → state 缓存含 next。"""
        mock_auth_instance = MagicMock()
        mock_auth_instance.authorize.return_value = "https://oauth.dingtalk.com/connect/qrconnect?appid=xxx"
        mock_auth_req_cls.build.return_value = mock_auth_instance

        resp = client.get(
            "/api/v1/plugins/ddw-social-login/auth/dingtalk?next=/wenqu/student.html",
            follow_redirects=False,
        )
        assert resp.status_code == 302

        # 验证 state 缓存里有 next
        assert len(mock_state_cache) == 1
        state_key = next(iter(mock_state_cache))
        entry = mock_state_cache[state_key]
        assert entry["next"] == "/wenqu/student.html"
        assert entry["provider"] == "dingtalk"


# ---------------------------------------------------------------------------
# T10: GET /callback/dingtalk?state=valid → 302 跳转到 next
# ---------------------------------------------------------------------------


class TestT10_CallbackRedirectsToNext:
    """T10: callback 应从 state 缓存读取 next 并跳转。"""

    def test_callback_redirects_to_next_from_state(self, client: TestClient):
        """callback 带 next=/wenqu/student.html 的 state → 302 到该页面。"""
        from plugins.ddw_social_login.services import _state_cache

        # 手动注入 state 缓存
        test_state = "test_state_next_123"
        _state_cache[test_state] = {
            "provider": "dingtalk",
            "created_at": "2026-08-13T00:00:00",
            "next": "/wenqu/student.html",
        }

        with patch("plugins.ddw_social_login.router.handle_callback") as mock_handle:
            mock_handle.return_value = {
                "access_token": "test_jwt_token",
                "user": {"id": 1, "name": "测试学生", "role": "student"},
            }
            resp = client.get(
                f"/api/v1/plugins/ddw-social-login/callback/dingtalk?code=test_code&state={test_state}",
                follow_redirects=False,
            )

        assert resp.status_code == 302
        location = resp.headers.get("location", "")
        assert location.startswith("/wenqu/student.html#access_token=")


# ---------------------------------------------------------------------------
# T11: GET /auth/dingtalk?next=http://evil.com → 安全校验拦截
# ---------------------------------------------------------------------------


class TestT11_OpenRedirectBlocked:
    """T11: 非法 next 参数应被拦截，回退到 /pal.html。"""

    @patch("plugins.ddw_social_login.services._state_cache", new_callable=dict)
    @patch("senweaver_oauth.AuthRequest")
    def test_evil_next_sanitized_to_pal(
        self, mock_auth_req_cls, mock_state_cache, client: TestClient, config_manager
    ):
        """GET /auth/dingtalk?next=http://evil.com → state 缓存 next=/pal.html。"""
        mock_auth_instance = MagicMock()
        mock_auth_instance.authorize.return_value = "https://oauth.dingtalk.com/connect/qrconnect?appid=xxx"
        mock_auth_req_cls.build.return_value = mock_auth_instance

        resp = client.get(
            "/api/v1/plugins/ddw-social-login/auth/dingtalk?next=http://evil.com",
            follow_redirects=False,
        )
        assert resp.status_code == 302

        # next 应被校验为 /pal.html
        state_key = next(iter(mock_state_cache))
        entry = mock_state_cache[state_key]
        assert entry["next"] == "/pal.html"

    @patch("plugins.ddw_social_login.services._state_cache", new_callable=dict)
    @patch("senweaver_oauth.AuthRequest")
    def test_javascript_uri_blocked(
        self, mock_auth_req_cls, mock_state_cache, client: TestClient, config_manager
    ):
        """GET /auth/dingtalk?next=javascript:alert(1) → state 缓存 next=/pal.html。"""
        mock_auth_instance = MagicMock()
        mock_auth_instance.authorize.return_value = "https://oauth.dingtalk.com/connect/qrconnect?appid=xxx"
        mock_auth_req_cls.build.return_value = mock_auth_instance

        resp = client.get(
            "/api/v1/plugins/ddw-social-login/auth/dingtalk?next=javascript:alert(1)",
            follow_redirects=False,
        )
        assert resp.status_code == 302

        state_key = next(iter(mock_state_cache))
        entry = mock_state_cache[state_key]
        assert entry["next"] == "/pal.html"
