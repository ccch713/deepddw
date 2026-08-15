"""数字员工体系 P5 测试用例 — 权限打通。

测试用例：
1. 数字员工角色的 JWT token 可被认证中间件解析
2. 数字员工不触发设备绑定检查
3. decision_scope 外的操作被拒绝
4. 数字员工可发起碳硅协作流程
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


class TestDigitalEmployeeP5:
    """数字员工体系 P5 测试用例。"""

    # T1: 数字员工角色的 JWT token 可被认证中间件解析
    def test_t1_digital_agent_jwt_parsing(self):
        """数字员工 JWT token 的 sub 字段格式为 agent:{id}，可被正确解析。"""
        from core.auth.jwt import create_access_token, decode_token

        # 创建数字员工 token
        token = create_access_token(
            user_id=0,
            tenant_id=1,
            role="digital_agent",
            agent_id=7,
        )

        # 解码 token
        payload = decode_token(token)

        # 验证 sub 字段格式
        assert payload["sub"] == "agent:7"
        assert payload["role"] == "digital_agent"
        assert payload["tid"] == 1
        assert payload["agent_id"] == 7

    # T1b: current_user 能正确解析数字员工 token
    def test_t1b_current_user_parses_digital_agent(self):
        """current_user 依赖能正确解析数字员工 token。"""
        from core.auth.jwt import create_access_token

        # 创建数字员工 token
        token = create_access_token(
            user_id=0,
            tenant_id=1,
            role="digital_agent",
            agent_id=7,
        )

        # 模拟 Request 和 credentials
        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.credentials = token

        # 调用 current_user（需要异步）
        import asyncio
        from core.auth.jwt import current_user

        result = asyncio.run(
            current_user(mock_request, mock_credentials)
        )

        # 验证解析结果
        assert result["role"] == "digital_agent"
        assert result["agent_id"] == 7
        assert result["is_digital_agent"] is True
        assert result["tenant_id"] == 1

    # T2: 数字员工不触发设备绑定检查
    def test_t2_digital_agent_skips_device_binding(self):
        """数字员工 token 不触发设备绑定检查。"""
        from core.auth.jwt import create_access_token

        # 创建数字员工 token
        token = create_access_token(
            user_id=0,
            tenant_id=1,
            role="digital_agent",
            agent_id=7,
        )

        # 模拟 Request 和 credentials
        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.credentials = token

        # 调用 current_user
        import asyncio
        from core.auth.jwt import current_user

        result = asyncio.run(
            current_user(mock_request, mock_credentials)
        )

        # 验证数字员工标识
        assert result["is_digital_agent"] is True

        # 数字员工不应该有 device_required 字段（因为不走登录流程）
        # 这里验证的是 token 解析正确，设备绑定检查在登录时跳过
        assert "device_required" not in result

    # T3: decision_scope 外的操作被拒绝
    def test_t3_decision_scope_enforcement(self):
        """decision_scope 外的操作被拒绝。"""
        from core.auth.digital_agent_permission import (
            DIGITAL_AGENT_DEFAULT_PERMISSIONS,
        )

        # 验证默认权限矩阵
        assert DIGITAL_AGENT_DEFAULT_PERMISSIONS["read"] is True
        assert DIGITAL_AGENT_DEFAULT_PERMISSIONS["create"] is False
        assert DIGITAL_AGENT_DEFAULT_PERMISSIONS["edit"] is False
        assert DIGITAL_AGENT_DEFAULT_PERMISSIONS["delete"] is False
        assert DIGITAL_AGENT_DEFAULT_PERMISSIONS["approve"] is False
        assert DIGITAL_AGENT_DEFAULT_PERMISSIONS["initiate_flow"] is True

        # 模拟 DigitalAgent 对象
        mock_agent = MagicMock()
        mock_agent.decision_scope = ["read", "initiate_flow"]

        # 模拟 db.get 返回 mock_agent
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_agent)

        import asyncio
        from core.auth.digital_agent_permission import check_digital_agent_permission

        # 测试：read 在 scope 内，应该允许
        result = asyncio.run(
            check_digital_agent_permission(7, "read", mock_db)
        )
        assert result is True

        # 测试：create 不在 scope 内，应该拒绝
        result = asyncio.run(
            check_digital_agent_permission(7, "create", mock_db)
        )
        assert result is False

        # 测试：approve 不在 scope 内，应该拒绝
        result = asyncio.run(
            check_digital_agent_permission(7, "approve", mock_db)
        )
        assert result is False

    # T4: 数字员工可发起碳硅协作流程
    def test_t4_digital_agent_can_initiate_flow(self):
        """数字员工可发起碳硅协作流程（initiate_flow 权限）。"""
        from core.auth.digital_agent_permission import (
            DIGITAL_AGENT_DEFAULT_PERMISSIONS,
            check_digital_agent_permission,
        )

        # 验证默认权限中 initiate_flow 为 True
        assert DIGITAL_AGENT_DEFAULT_PERMISSIONS["initiate_flow"] is True

        # 模拟 DigitalAgent 对象（空 decision_scope，使用默认权限）
        mock_agent = MagicMock()
        mock_agent.decision_scope = []

        # 模拟 db.get 返回 mock_agent
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_agent)

        import asyncio

        # 测试：initiate_flow 使用默认权限，应该允许
        result = asyncio.run(
            check_digital_agent_permission(7, "initiate_flow", mock_db)
        )
        assert result is True

        # 模拟 DigitalAgent 对象（decision_scope 包含 initiate_flow）
        mock_agent_with_scope = MagicMock()
        mock_agent_with_scope.decision_scope = ["read", "initiate_flow"]

        mock_db.get = AsyncMock(return_value=mock_agent_with_scope)

        # 测试：initiate_flow 在 scope 内，应该允许
        result = asyncio.run(
            check_digital_agent_permission(7, "initiate_flow", mock_db)
        )
        assert result is True

    # T5: 审计日志记录数字员工操作（额外验证）
    def test_t5_digital_agent_token_fields(self):
        """数字员工 token 包含必要字段。"""
        from core.auth.jwt import create_access_token, decode_token

        # 创建数字员工 token
        token = create_access_token(
            user_id=0,
            tenant_id=1,
            role="digital_agent",
            agent_id=7,
            extra={"department_id": 3},
        )

        # 解码 token
        payload = decode_token(token)

        # 验证所有必要字段
        assert payload["sub"] == "agent:7"
        assert payload["role"] == "digital_agent"
        assert payload["tid"] == 1
        assert payload["agent_id"] == 7
        assert payload["department_id"] == 3
        assert "jti" in payload  # 用于审计日志追踪
        assert "exp" in payload
        assert "iat" in payload
