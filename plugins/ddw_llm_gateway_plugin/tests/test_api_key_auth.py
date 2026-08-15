"""
API Key 鉴权测试

覆盖:
- APIKeyAuth 初始化
- 单 key 校验
- 多 key 轮换
- 未配置时跳过鉴权
- 环境变量加载
- key 管理（增删）
"""
from __future__ import annotations

import os
from unittest.mock import patch

from ddw_llm_gateway.router import APIKeyAuth


class TestAPIKeyAuth:
    """APIKeyAuth 测试"""

    def test_no_keys_allows_all(self):
        """未配置 key 时放行所有请求"""
        auth = APIKeyAuth()
        assert auth.validate(None) is True
        assert auth.validate("any-key") is True
        assert auth.is_configured() is False

    def test_single_key_validation(self):
        """单 key 校验"""
        auth = APIKeyAuth(keys=["sk-test-123"])
        assert auth.validate("sk-test-123") is True
        assert auth.validate("wrong-key") is False
        assert auth.validate(None) is False
        assert auth.is_configured() is True

    def test_multi_key_rotation(self):
        """多 key 轮换"""
        auth = APIKeyAuth(keys=["sk-key-1", "sk-key-2", "sk-key-3"])
        assert auth.validate("sk-key-1") is True
        assert auth.validate("sk-key-2") is True
        assert auth.validate("sk-key-3") is True
        assert auth.validate("sk-key-4") is False

    def test_add_key(self):
        """运行时添加 key"""
        auth = APIKeyAuth(keys=["sk-key-1"])
        assert auth.validate("sk-key-2") is False
        auth.add_key("sk-key-2")
        assert auth.validate("sk-key-2") is True

    def test_remove_key(self):
        """运行时移除 key"""
        auth = APIKeyAuth(keys=["sk-key-1", "sk-key-2"])
        auth.remove_key("sk-key-1")
        assert auth.validate("sk-key-1") is False
        assert auth.validate("sk-key-2") is True

    def test_remove_nonexistent_key(self):
        """移除不存在的 key 不报错"""
        auth = APIKeyAuth(keys=["sk-key-1"])
        auth.remove_key("nonexistent")
        assert auth.validate("sk-key-1") is True

    def test_list_keys_masked(self):
        """列出脱敏 key"""
        auth = APIKeyAuth(keys=["sk-test-123456", "abcdef"])
        keys = auth.list_keys()
        assert len(keys) == 2
        assert all("***" in k for k in keys)
        assert "sk-t***" in keys or "abcd***" in keys

    def test_from_env(self):
        """从环境变量加载"""
        with patch.dict(os.environ, {"DDW_GATEWAY_API_KEYS": "sk-a,sk-b,sk-c"}):
            auth = APIKeyAuth.from_env()
            assert auth.validate("sk-a") is True
            assert auth.validate("sk-b") is True
            assert auth.validate("sk-c") is True
            assert auth.validate("sk-d") is False

    def test_from_env_empty(self):
        """环境变量为空时无 key"""
        with patch.dict(os.environ, {"DDW_GATEWAY_API_KEYS": ""}):
            auth = APIKeyAuth.from_env()
            assert auth.is_configured() is False

    def test_from_env_whitespace(self):
        """环境变量带空格"""
        with patch.dict(os.environ, {"DDW_GATEWAY_API_KEYS": " sk-a , sk-b "}):
            auth = APIKeyAuth.from_env()
            assert auth.validate("sk-a") is True
            assert auth.validate("sk-b") is True
