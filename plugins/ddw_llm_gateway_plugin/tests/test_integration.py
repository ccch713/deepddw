"""
LLM Gateway 集成测试 — 真实 Provider API 模拟

覆盖:
1. 渠道配置加载 + 初始化
2. 负载均衡选择渠道
3. 请求转发流程（mock Provider）
4. 流式 SSE 转发（mock Provider）
5. 失败重试机制
6. 自动禁用/恢复

使用 mock 替代真实 Provider API 调用，但测试完整的转发流程。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 确保插件目录在 sys.path 中并设置虚拟包
_plugin_dir = Path(__file__).parent.parent
if str(_plugin_dir) not in sys.path:
    sys.path.insert(0, str(_plugin_dir))

# 创建虚拟包让相对导入 work (from .models import Channel)
import types as _types  # noqa: E402

if "ddw_llm_gateway" not in sys.modules:
    _pkg = _types.ModuleType("ddw_llm_gateway")
    _pkg.__path__ = [str(_plugin_dir)]
    _pkg.__package__ = "ddw_llm_gateway"
    sys.modules["ddw_llm_gateway"] = _pkg

from ddw_llm_gateway.channel_manager import ChannelManager, ChannelStatus  # noqa: E402
from ddw_llm_gateway.channel_types import ChannelType  # noqa: E402
from ddw_llm_gateway.circuit_breaker import CircuitBreaker  # noqa: E402
from ddw_llm_gateway.load_balancer import ChannelCandidate, LoadBalancer  # noqa: E402
from ddw_llm_gateway.relay import Relay, RelayRequest  # noqa: E402
from ddw_llm_gateway.stream_handler import StreamHandler  # noqa: E402

# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def channel_manager() -> ChannelManager:
    """创建带测试渠道的渠道管理器"""
    cm = ChannelManager()
    # 创建支持 gpt-4 的主渠道
    cm.create(
        name="https://api.openai.com",
        channel_type=ChannelType.OPENAI,
        key="sk-test-openai",
        base_url="https://api.openai.com",
        models=["gpt-4", "gpt-3.5-turbo"],
        priority=10,
        weight=100,
        group="default",
    )
    # 创建支持 gpt-4 的备用渠道
    cm.create(
        name="https://api.deepseek.com",
        channel_type=ChannelType.DEEPSEEK,
        key="sk-test-deepseek",
        base_url="https://api.deepseek.com",
        models=["gpt-4", "deepseek-chat"],
        priority=5,
        weight=80,
        group="default",
    )
    # 创建仅支持 deepseek-chat 的渠道
    cm.create(
        name="https://api.minimax.chat",
        channel_type=ChannelType.MINIMAX,
        key="sk-test-minimax",
        base_url="https://api.minimax.chat",
        models=["deepseek-chat"],
        priority=5,
        weight=60,
        group="premium",
    )
    return cm


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """创建断路器"""
    return CircuitBreaker(disable_threshold=3, retest_interval=300)


@pytest.fixture
def load_balancer() -> LoadBalancer:
    """创建负载均衡器"""
    return LoadBalancer(success_rate_threshold=0.5)


@pytest.fixture
def relay(load_balancer, circuit_breaker) -> Relay:
    """创建转发器"""
    return Relay(
        load_balancer=load_balancer,
        circuit_breaker=circuit_breaker,
    )


@pytest.fixture
def stream_handler() -> StreamHandler:
    """创建流式处理器"""
    return StreamHandler(buffer_size=1024, timeout=30.0)


# ── 1. 渠道配置加载 + 初始化 ───────────────────────────────────


class TestChannelConfigLoading:
    """测试渠道配置加载和初始化"""

    def test_load_channels_from_config(self):
        """从 YAML 配置加载渠道"""
        cm = ChannelManager()
        config = [
            {
                "name": "openai-primary",
                "type": ChannelType.OPENAI,
                "api_keys": ["sk-test-key"],
                "base_url": "https://api.openai.com",
                "models": ["gpt-4", "gpt-3.5-turbo"],
                "priority": 10,
                "weight": 100,
                "group": "default",
            },
            {
                "name": "deepseek-backup",
                "type": ChannelType.DEEPSEEK,
                "api_keys": ["sk-ds-key"],
                "models": ["deepseek-chat"],
                "priority": 5,
                "weight": 80,
            },
        ]
        count = cm.load_from_config(config)

        assert count == 2
        channels = cm.list_all()
        assert len(channels) == 2

        # 验证渠道属性
        openai_ch = next(c for c in channels if c.name == "openai-primary")
        assert openai_ch.type == ChannelType.OPENAI
        assert openai_ch.priority == 10
        assert openai_ch.status == ChannelStatus.ENABLED

    def test_channel_model_support(self):
        """渠道模型支持检查"""
        cm = ChannelManager()
        ch = cm.create(
            name="test",
            channel_type=ChannelType.OPENAI,
            key="sk-test",
            models=["gpt-4", "gpt-3.5-turbo"],
        )
        assert ch.supports_model("gpt-4") is True
        assert ch.supports_model("gpt-3.5-turbo") is True
        assert ch.supports_model("deepseek-chat") is False

    def test_channel_empty_models_supports_all(self):
        """未指定模型列表的渠道支持所有模型"""
        cm = ChannelManager()
        ch = cm.create(
            name="test",
            channel_type=ChannelType.OPENAI,
            key="sk-test",
            models=None,
        )
        assert ch.supports_model("any-model") is True


# ── 2. 负载均衡选择渠道 ────────────────────────────────────────


class TestLoadBalancing:
    """测试负载均衡选择"""

    def test_select_highest_priority(self, load_balancer):
        """优先选择最高优先级渠道"""
        candidates = [
            ChannelCandidate(
                id=1, name="low-pri", priority=5, weight=100,
                response_time=100, balance=100.0, success_rate=1.0,
            ),
            ChannelCandidate(
                id=2, name="high-pri", priority=10, weight=100,
                response_time=200, balance=100.0, success_rate=1.0,
            ),
        ]
        selected = load_balancer.select(candidates, model="gpt-4")
        assert selected.id == 2  # 高优先级被选中

    def test_select_weighted_random(self, load_balancer):
        """同优先级内按权重随机选择"""
        candidates = [
            ChannelCandidate(
                id=1, name="ch1", priority=10, weight=100,
                response_time=100, balance=100.0, success_rate=1.0,
            ),
            ChannelCandidate(
                id=2, name="ch2", priority=10, weight=1,
                response_time=100, balance=100.0, success_rate=1.0,
            ),
        ]
        # 多次选择，高权重渠道应该更频繁被选中
        selections = [load_balancer.select(candidates).id for _ in range(100)]
        assert selections.count(1) > selections.count(2)

    def test_filter_by_model(self, load_balancer):
        """按模型过滤渠道"""
        candidates = [
            ChannelCandidate(
                id=1, name="ch1", priority=10, weight=100,
                response_time=100, balance=100.0, success_rate=1.0,
                models=["gpt-4"],
            ),
            ChannelCandidate(
                id=2, name="ch2", priority=10, weight=100,
                response_time=100, balance=100.0, success_rate=1.0,
                models=["deepseek-chat"],
            ),
        ]
        selected = load_balancer.select(candidates, model="gpt-4")
        assert selected.id == 1

    def test_skip_low_success_rate(self, load_balancer):
        """跳过成功率过低的渠道"""
        candidates = [
            ChannelCandidate(
                id=1, name="bad-ch", priority=10, weight=100,
                response_time=100, balance=100.0, success_rate=0.3,
            ),
            ChannelCandidate(
                id=2, name="good-ch", priority=5, weight=100,
                response_time=100, balance=100.0, success_rate=1.0,
            ),
        ]
        selected = load_balancer.select(candidates)
        assert selected.id == 2  # 低成功率渠道被跳过

    def test_select_empty_candidates(self, load_balancer):
        """空候选列表返回 None"""
        selected = load_balancer.select([])
        assert selected is None

    def test_ignore_first_priority_for_retry(self, load_balancer):
        """重试时跳过最高优先级渠道"""
        candidates = [
            ChannelCandidate(
                id=1, name="high", priority=10, weight=100,
                response_time=100, balance=100.0, success_rate=1.0,
            ),
            ChannelCandidate(
                id=2, name="low", priority=5, weight=100,
                response_time=100, balance=100.0, success_rate=1.0,
            ),
        ]
        selected = load_balancer.select(candidates, ignore_first_priority=True)
        assert selected.id == 2  # 重试时选次优先级


# ── 3. 请求转发流程（mock Provider）─────────────────────────────


class TestRelayWithMockProvider:
    """测试请求转发流程（mock 上游 Provider）"""

    @pytest.mark.asyncio
    async def test_relay_chat_success(self, relay, channel_manager):
        """成功转发 Chat Completion 请求"""
        candidates = [
            ChannelCandidate(
                id=1, name="https://api.openai.com", priority=10, weight=100,
                response_time=0, balance=100.0, success_rate=1.0,
                models=["gpt-4"],
            ),
        ]

        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            user_id=1,
        )

        # Mock HTTP 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hi!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

        with patch.object(relay, '_get_http_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await relay.relay_chat(request, candidates)

        assert result.success is True
        assert result.status_code == 200
        assert result.total_tokens == 15
        assert result.channel_name == "https://api.openai.com"

    @pytest.mark.asyncio
    async def test_relay_chat_no_available_channel(self, relay):
        """无可用渠道时返回 503"""
        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )

        result = await relay.relay_chat(request, candidates=[])

        assert result.success is False
        assert result.status_code == 503
        assert "无可用渠道" in result.error_message

    @pytest.mark.asyncio
    async def test_relay_chat_with_pre_consume(self, relay):
        """请求转发时调用预消费"""
        candidates = [
            ChannelCandidate(
                id=1, name="test-channel", priority=10, weight=100,
                response_time=0, balance=100.0, success_rate=1.0,
            ),
        ]

        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            user_id=1,
        )

        # Mock token_manager
        mock_token_manager = AsyncMock()
        mock_token_manager.pre_consume = AsyncMock(return_value={"allowed": True})
        relay._token_manager = mock_token_manager

        # Mock HTTP 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hi"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }

        with patch.object(relay, '_get_http_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await relay.relay_chat(request, candidates)

        assert result.success is True
        mock_token_manager.pre_consume.assert_called_once_with(
            user_id=1, model="gpt-4"
        )


# ── 4. 流式 SSE 转发（mock Provider）────────────────────────────


class TestStreamSSE:
    """测试流式 SSE 转发"""

    @pytest.mark.asyncio
    async def test_relay_stream_success(self, relay):
        """成功转发流式请求"""
        candidates = [
            ChannelCandidate(
                id=1, name="test-stream", priority=10, weight=100,
                response_time=0, balance=100.0, success_rate=1.0,
            ),
        ]

        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,
        )

        # Mock 流式响应
        async def mock_stream():
            yield 'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"Hi"}}]}\n'
            yield 'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":" there"}}]}\n'
            yield "data: [DONE]\n"

        mock_response = AsyncMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_response.aiter_lines.return_value = mock_stream()

        with patch.object(relay, '_get_http_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.stream.return_value = mock_response
            mock_get_client.return_value = mock_client

            chunks = []
            async for chunk in relay.relay_stream(request, candidates):
                chunks.append(chunk)

        assert len(chunks) > 0
        # 至少有一行 SSE 数据
        assert any("data:" in c for c in chunks)

    def test_parse_sse_line(self):
        """SSE 数据行解析"""
        # 正常数据行
        result = StreamHandler.parse_sse_line(
            'data: {"id":"1","choices":[{"delta":{"content":"Hi"}}]}'
        )
        assert result is not None
        assert result["id"] == "1"

        # DONE 标记
        result = StreamHandler.parse_sse_line("data: [DONE]")
        assert result is None

        # 非数据行
        result = StreamHandler.parse_sse_line("event: ping")
        assert result is None

    def test_build_sse_chunk(self):
        """构建 SSE 数据块"""
        chunk = StreamHandler.build_sse_chunk({"content": "Hello"})
        assert chunk.startswith("data: ")
        assert '"content": "Hello"' in chunk

        chunk = StreamHandler.build_sse_chunk("[DONE]")
        assert chunk == "data: [DONE]\n\n"


# ── 5. 失败重试机制 ────────────────────────────────────────────


class TestRetryMechanism:
    """测试失败重试"""

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, relay):
        """请求失败后自动重试"""
        candidates = [
            ChannelCandidate(
                id=1, name="ch1", priority=10, weight=100,
                response_time=0, balance=100.0, success_rate=1.0,
                models=["gpt-4"],
            ),
            ChannelCandidate(
                id=2, name="ch2", priority=5, weight=100,
                response_time=0, balance=100.0, success_rate=1.0,
                models=["gpt-4"],
            ),
        ]

        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )

        call_count = 0

        async def mock_forward(channel, req):
            nonlocal call_count
            call_count += 1
            if channel.id == 1:
                return {"success": False, "error": "timeout"}
            return {
                "success": True,
                "status_code": 200,
                "data": {"choices": []},
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            }

        with patch.object(relay, '_forward_request', side_effect=mock_forward):
            result = await relay.relay_chat(request, candidates, max_retries=3)

        assert result.success is True
        assert call_count == 2  # 第一次失败，第二次成功

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, relay):
        """所有重试都失败"""
        candidates = [
            ChannelCandidate(
                id=1, name="ch1", priority=10, weight=100,
                response_time=0, balance=100.0, success_rate=1.0,
            ),
        ]

        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )

        async def always_fail(channel, req):
            return {"success": False, "error": "provider error"}

        with patch.object(relay, '_forward_request', side_effect=always_fail):
            result = await relay.relay_chat(request, candidates, max_retries=3)

        assert result.success is False
        assert result.status_code == 502
        assert "所有重试均失败" in result.error_message


# ── 6. 自动禁用/恢复 ────────────────────────────────────────────


class TestAutoDisableRecovery:
    """测试渠道自动禁用和恢复"""

    def test_auto_disable_on_consecutive_failures(self, circuit_breaker):
        """连续失败后自动禁用渠道"""
        channel_id = 1

        # 模拟连续 3 次失败（阈值=3）
        for _ in range(3):
            circuit_breaker.record_failure(channel_id)

        health = circuit_breaker.get_health(channel_id)
        assert health.status == ChannelStatus.AUTO_DISABLED

    def test_success_resets_failure_count(self, circuit_breaker):
        """成功请求重置失败计数"""
        channel_id = 1

        # 连续 2 次失败（未达到阈值）
        for _ in range(2):
            circuit_breaker.record_failure(channel_id)

        # 成功一次
        circuit_breaker.record_success(channel_id)

        health = circuit_breaker.get_health(channel_id)
        assert health.consecutive_failures == 0
        assert health.status == ChannelStatus.ENABLED

    def test_success_rate_calculation(self, circuit_breaker):
        """成功率计算"""
        channel_id = 1

        # 8 次成功 + 2 次失败
        for _ in range(8):
            circuit_breaker.record_success(channel_id)
        for _ in range(2):
            circuit_breaker.record_failure(channel_id)

        rate = circuit_breaker.get_success_rate(channel_id)
        assert rate == pytest.approx(0.8, abs=0.01)

    def test_auto_disabled_channel_recovery(self, circuit_breaker):
        """自动禁用渠道恢复正常"""
        channel_id = 1

        # 触发自动禁用
        for _ in range(3):
            circuit_breaker.record_failure(channel_id)

        assert circuit_breaker.get_health(channel_id).status == ChannelStatus.AUTO_DISABLED

        # 模拟测试成功后恢复
        circuit_breaker.record_success(channel_id)

        health = circuit_breaker.get_health(channel_id)
        assert health.status == ChannelStatus.ENABLED
        assert health.consecutive_failures == 0

    def test_get_channels_needing_retest(self, circuit_breaker):
        """获取需要重测的渠道"""
        # 渠道 1: 自动禁用但未到重测时间
        circuit_breaker.record_failure(1)
        circuit_breaker.record_failure(1)
        circuit_breaker.record_failure(1)

        # 渠道 2: 自动禁用且已过重测时间（通过 mock time）
        circuit_breaker.record_failure(2)
        circuit_breaker.record_failure(2)
        circuit_breaker.record_failure(2)
        # 手动设置过期时间
        health2 = circuit_breaker.get_health(2)
        health2.auto_disabled_at = time.time() - 400  # 400秒前禁用

        needing_retest = circuit_breaker.get_channels_needing_retest()
        assert 2 in needing_retest


# ── 7. 断路器 + 渠道管理器集成 ──────────────────────────────────


class TestCircuitBreakerChannelIntegration:
    """断路器与渠道管理器集成"""

    def test_auto_disable_updates_channel_manager(self, channel_manager, circuit_breaker):
        """断路器自动禁用后更新渠道管理器状态"""
        channels = channel_manager.list_enabled()
        assert len(channels) == 3  # 3 个启用渠道

        # 对第一个渠道记录连续失败
        ch_id = channels[0].id
        for _ in range(3):
            circuit_breaker.record_failure(ch_id)

        # 断路器触发自动禁用
        health = circuit_breaker.get_health(ch_id)
        assert health.status == ChannelStatus.AUTO_DISABLED

        # 同步更新渠道管理器
        channel_manager.auto_disable(ch_id)

        # 验证渠道管理器状态
        updated_ch = channel_manager.get(ch_id)
        assert updated_ch.status == ChannelStatus.AUTO_DISABLED

        # 仅剩 2 个启用渠道
        enabled = channel_manager.list_enabled()
        assert len(enabled) == 2
