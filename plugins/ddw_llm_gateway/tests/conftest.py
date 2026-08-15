import sys
import os
import pytest
import asyncio
from typing import Dict, Generator
from unittest.mock import AsyncMock, MagicMock, patch

# 确保项目根目录在 sys.path 中
project_root = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from plugins.ddw_llm_gateway.plugin import Plugin  # noqa: E402
from plugins.ddw_llm_gateway.storage import Storage  # noqa: E402
from plugins.ddw_llm_gateway.models import ModelRegistration, RouteRule, KeyCredential  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI()
    return app


@pytest.fixture
def storage(tmp_path) -> Generator[Storage, None, None]:
    """创建临时存储"""
    db_path = tmp_path / "test_llm_gateway.db"
    storage = Storage(db_path=str(db_path))
    storage.init_db()
    yield storage
    storage.close()


@pytest.fixture
def plugin(app, storage) -> Plugin:
    """创建插件实例"""
    with patch('plugins.ddw_llm_gateway.plugin.PluginBase') as mock_base:
        mock_base.__init__ = MagicMock(return_value=None)
        plugin = Plugin(app=app, config={})
        plugin.storage = storage
        yield plugin


@pytest.fixture
def client(app, storage) -> Generator[TestClient, None, None]:
    """创建测试客户端"""
    from plugins.ddw_llm_gateway.router import router, set_storage

    # 设置路由使用的 storage
    set_storage(storage)

    # 注册路由
    app.include_router(router)

    # 创建测试模型
    models = [
        ModelRegistration(
            model_id="deepseek-chat",
            provider="deepseek",
            display_name="DeepSeek Chat",
            base_url="https://api.deepseek.com/v1",
            api_key="test-key",
            input_price_per_1m=1.0,
            output_price_per_1m=2.0,
            priority=10
        ),
        ModelRegistration(
            model_id="minimax-chat",
            provider="minimax",
            display_name="MiniMax Chat",
            base_url="https://api.minimax.chat/v1",
            api_key="test-key",
            input_price_per_1m=0.5,
            output_price_per_1m=1.5,
            priority=20
        ),
        ModelRegistration(
            model_id="deepseek-coder",
            provider="deepseek",
            display_name="DeepSeek Coder",
            base_url="https://api.deepseek.com/v1",
            api_key="test-key",
            input_price_per_1m=1.0,
            output_price_per_1m=2.0,
            priority=5
        ),
        ModelRegistration(
            model_id="ollama/qwen2.5:72b",
            provider="ollama",
            display_name="Qwen 2.5 72B",
            base_url="http://localhost:11434/v1",
            api_key="",
            input_price_per_1m=0.0,
            output_price_per_1m=0.0,
            priority=30,
            is_local=True
        )
    ]

    for model in models:
        storage.create_model(model)

    # 创建测试路由规则
    routes = [
        RouteRule(
            rule_id="route-default",
            name="default",
            scene="default",
            strategy="priority",
            model_chain=["deepseek-chat", "minimax-chat", "ollama/qwen2.5:72b"]
        ),
        RouteRule(
            rule_id="route-code",
            name="code",
            scene="code",
            strategy="priority",
            model_chain=["deepseek-coder", "ollama/qwen2.5:72b"]
        ),
        RouteRule(
            rule_id="route-translate",
            name="translate",
            scene="translate",
            strategy="cost",
            model_chain=["minimax-chat", "deepseek-chat"]
        )
    ]

    for route in routes:
        storage.create_route(route)

    # 创建测试 API Key
    import hashlib
    test_key = "sk-ddw-test"
    key_hash = hashlib.sha256(test_key.encode()).hexdigest()

    key_credential = KeyCredential(
        key_id="test-key-id",
        key_prefix="sk-ddw-tes...est",
        key_hash=key_hash,
        name="Test Key",
        plugin_name="ddw_test",
        user_id="test-user"
    )
    storage.create_key(key_credential)

    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_deepseek():
    """模拟 DeepSeek 响应"""
    mock = AsyncMock()
    mock.return_value = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1694268190,
        "model": "deepseek-chat",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! How can I assist you today?"
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }
    return mock


@pytest.fixture
def mock_providers(mock_deepseek):
    """模拟所有 providers"""
    mocks = {
        "deepseek-chat": mock_deepseek,
        "minimax-chat": AsyncMock(return_value={
            "id": "chatcmpl-456",
            "object": "chat.completion",
            "created": 1694268190,
            "model": "minimax-chat",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Hello from MiniMax!"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 15,
                "total_tokens": 25
            }
        }),
        "deepseek-coder": AsyncMock(return_value={
            "id": "chatcmpl-789",
            "object": "chat.completion",
            "created": 1694268190,
            "model": "deepseek-coder",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Here is the code:"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 30,
                "total_tokens": 45
            }
        })
    }
    return mocks


@pytest.fixture
def admin_headers():
    """管理员请求头"""
    return {"Authorization": "Bearer admin-token"}


@pytest.fixture
def mock_completion():
    """模拟完成响应"""
    def _mock_completion(usage: Dict[str, int] = None):
        return {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1694268190,
            "model": "deepseek-chat",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Hello! How can I assist you today?"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": usage or {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }
    return _mock_completion
