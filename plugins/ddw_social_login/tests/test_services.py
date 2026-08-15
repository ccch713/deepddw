"""服务层测试 —— T4（自动注册 + 首次登录签发 token）。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.database.models import User, UserBinding


# ---------------------------------------------------------------------------
# T4: 首次扫码自动注册 + 签发 token
# ---------------------------------------------------------------------------


class TestT4_AutoRegister:
    """T4: state 有效 + mock senweaver 返回 → 自动注册 + 签发 token。"""

    @patch("plugins.ddw_social_login.services.create_access_token", return_value="mock_jwt_token_xyz")
    @patch("plugins.ddw_social_login.services._write_login_audit", new_callable=AsyncMock)
    @patch("plugins.ddw_social_login.services.session_scope")
    @patch("plugins.ddw_social_login.services.asyncio.to_thread")
    def test_callback_auto_register(
        self,
        mock_to_thread,
        mock_session_scope,
        mock_audit,
        mock_create_token,
        client,
        config_manager,
        mock_auth_response_success,
        mock_social_user,
        seeded_db,
    ):
        """首次扫码应自动创建 User + UserBinding，并签发 token。"""
        # Mock session_scope 返回测试 session
        @asynccontextmanager
        async def _mock_session_scope():
            yield seeded_db

        mock_session_scope.side_effect = _mock_session_scope

        # Mock to_thread 返回成功响应
        async def _mock_to_thread(func, *args):
            return mock_auth_response_success

        mock_to_thread.side_effect = _mock_to_thread

        # 注入有效 state
        from plugins.ddw_social_login import services as svc

        svc._state_cache["test_state_t4"] = {"provider": "dingtalk", "created_at": "2026-01-01"}

        # 发起回调
        resp = client.get(
            "/api/v1/plugins/ddw-social-login/callback/dingtalk",
            params={"code": "test_code", "state": "test_state_t4"},
            follow_redirects=False,
        )

        # 应 302 重定向到 /pal.html#access_token=...
        assert resp.status_code == 302
        location = resp.headers.get("location", "")
        assert "access_token=mock_jwt_token_xyz" in location

        # 验证 create_access_token 被调用
        mock_create_token.assert_called_once()
        call_kwargs = mock_create_token.call_args
        assert call_kwargs.kwargs["tenant_id"] == 1 or call_kwargs[1]["tenant_id"] == 1

        # 验证审计被写入
        mock_audit.assert_called_once()


class TestAutoRegisterLogic:
    """测试 _resolve_or_create_user 和 _auto_register 的单元逻辑。"""

    @pytest.mark.asyncio
    async def test_auto_register_creates_user_and_binding(self, seeded_db):
        """_auto_register 应创建 User + UserBinding。"""
        from plugins.ddw_social_login.services import _auto_register

        mock_social = MagicMock()
        mock_social.uuid = "auto_reg_openid_1234567890"
        mock_social.nickname = "自动注册用户"

        user = await _auto_register(seeded_db, "dingtalk", mock_social, default_tenant_id=1)
        await seeded_db.commit()

        # 验证用户创建
        assert user.id is not None
        assert user.phone == "dt_auto_reg_openid_"  # dt_ + uuid[:16]
        assert user.name == "自动注册用户"
        assert user.role == "member"
        assert user.status == "active"
        assert user.tenant_id == 1

        # 验证绑定记录
        from sqlalchemy import select

        result = await seeded_db.execute(
            select(UserBinding).where(UserBinding.user_id == user.id)
        )
        binding = result.scalar_one()
        assert binding.provider == "dingtalk"
        assert binding.provider_uid == "auto_reg_openid_1234567890"
        assert binding.is_active is True
        assert binding.is_primary is True

    @pytest.mark.asyncio
    async def test_resolve_existing_binding(self, seeded_db):
        """已有绑定应直接返回已有用户，不新建。"""
        from plugins.ddw_social_login.services import _resolve_or_create_user

        # 先创建用户和绑定
        user = User(
            phone="wx_existing_user_12345",
            password_hash="hashed",
            name="已有用户",
            role="member",
            status="active",
            tenant_id=1,
        )
        seeded_db.add(user)
        await seeded_db.flush()

        binding = UserBinding(
            user_id=user.id,
            tenant_id=1,
            provider="wechat_open",
            provider_uid="existing_openid_1234567890",
            provider_name="已有用户",
            binding_type="login",
            is_primary=True,
            is_active=True,
        )
        seeded_db.add(binding)
        await seeded_db.commit()

        # 再次解析同一 openid
        mock_social = MagicMock()
        mock_social.uuid = "existing_openid_1234567890"
        mock_social.nickname = "已有用户"

        resolved_user, is_new = await _resolve_or_create_user(
            session=seeded_db,
            provider="wechat_open",
            social_user=mock_social,
            openid="existing_openid_1234567890",
            auto_register=True,
            default_tenant_id=1,
        )

        assert is_new is False
        assert resolved_user.id == user.id

    @pytest.mark.asyncio
    async def test_no_binding_no_auto_register_raises(self, seeded_db):
        """未开启自动注册 + 无绑定 → 应抛 401。"""
        from fastapi import HTTPException

        from plugins.ddw_social_login.services import _resolve_or_create_user

        mock_social = MagicMock()
        mock_social.uuid = "noexist_openid_1234567"

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_or_create_user(
                session=seeded_db,
                provider="dingtalk",
                social_user=mock_social,
                openid="noexist_openid_1234567",
                auto_register=False,
                default_tenant_id=1,
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == "ACCOUNT_NOT_FOUND"


class TestPhonePrefix:
    """测试不同 provider 的占位手机号前缀。"""

    @pytest.mark.asyncio
    async def test_wechat_prefix(self, seeded_db):
        """微信 → wx_ 前缀。"""
        from plugins.ddw_social_login.services import _auto_register

        mock_social = MagicMock()
        mock_social.uuid = "wechat_openid_1234567890"
        mock_social.nickname = None

        user = await _auto_register(seeded_db, "wechat_open", mock_social, 1)
        assert user.phone.startswith("wx_")

    @pytest.mark.asyncio
    async def test_qq_prefix(self, seeded_db):
        """QQ → qq_ 前缀。"""
        from plugins.ddw_social_login.services import _auto_register

        mock_social = MagicMock()
        mock_social.uuid = "qq_openid_1234567890123"
        mock_social.nickname = None

        user = await _auto_register(seeded_db, "qq", mock_social, 1)
        assert user.phone.startswith("qq_")

    @pytest.mark.asyncio
    async def test_feishu_prefix(self, seeded_db):
        """飞书 → fs_ 前缀。"""
        from plugins.ddw_social_login.services import _auto_register

        mock_social = MagicMock()
        mock_social.uuid = "feishu_openid_123456789"
        mock_social.nickname = None

        user = await _auto_register(seeded_db, "feishu", mock_social, 1)
        assert user.phone.startswith("fs_")


# ---------------------------------------------------------------------------
# T12: 自动注册时 default_role 参数生效（问渠部署配 student）
# ---------------------------------------------------------------------------


class TestT12_DefaultRole:
    """T12: _auto_register 应使用 default_role 参数。"""

    @pytest.mark.asyncio
    async def test_default_role_student(self, seeded_db):
        """default_role='student' → user.role == 'student'。"""
        from plugins.ddw_social_login.services import _auto_register

        mock_social = MagicMock()
        mock_social.uuid = "wx_student_test_openid"
        mock_social.nickname = "测试学生"

        user = await _auto_register(seeded_db, "wechat_open", mock_social, 1, default_role="student")
        assert user.role == "student"
        assert user.phone.startswith("wx_")

    @pytest.mark.asyncio
    async def test_default_role_member_fallback(self, seeded_db):
        """default_role 未传 → user.role == 'member'（默认值）。"""
        from plugins.ddw_social_login.services import _auto_register

        mock_social = MagicMock()
        mock_social.uuid = "dt_member_test_openid"
        mock_social.nickname = None

        user = await _auto_register(seeded_db, "dingtalk", mock_social, 1)
        assert user.role == "member"
        assert user.phone.startswith("dt_")
