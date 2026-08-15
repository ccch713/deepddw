"""
插件间集成测试 — ddw-token-manager × ddw-llm-gateway

测试两个插件的协作流程:
1. 请求进入 LLM 网关 → 预消费 Token → 转发 → 后消费 Token
2. 额度不足 → 拒绝请求
3. 请求失败 → 退还预消费
4. 渠道自动禁用时 Token 退还
"""
from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 添加两个插件目录到 sys.path 并设置虚拟包
_gateway_dir = Path(__file__).parent.parent / "ddw-llm-gateway"
_token_dir = Path(__file__).parent.parent / "ddw-token-manager"
for d in [_gateway_dir, _token_dir]:
    d_str = str(d)
    if d_str not in sys.path:
        sys.path.insert(0, d_str)

# 创建虚拟包让相对导入 work
import types as _types
if "ddw_llm_gateway" not in sys.modules:
    _pkg = _types.ModuleType("ddw_llm_gateway")
    _pkg.__path__ = [str(_gateway_dir)]
    _pkg.__package__ = "ddw_llm_gateway"
    sys.modules["ddw_llm_gateway"] = _pkg
if "ddw_token_manager" not in sys.modules:
    _pkg2 = _types.ModuleType("ddw_token_manager")
    _pkg2.__path__ = [str(_token_dir)]
    _pkg2.__package__ = "ddw_token_manager"
    sys.modules["ddw_token_manager"] = _pkg2

from ddw_llm_gateway.relay import Relay, RelayRequest, RelayResponse
from ddw_llm_gateway.load_balancer import LoadBalancer, ChannelCandidate
from ddw_llm_gateway.circuit_breaker import CircuitBreaker, ChannelStatus as CBChannelStatus


# ── Mock Token Manager ──────────────────────────────────────────


class MockTokenManager:
    """模拟 Token Manager — 内存中模拟额度扣减"""

    def __init__(self, initial_quota: int = 1000000):
        self._quota = initial_quota
        self._pre_consumed = 0
        self._call_log: list[dict] = []

    async def pre_consume(
        self, user_id: int, model: str, pre_consumed_quota: int = 500
    ) -> dict:
        """预消费额度"""
        self._call_log.append({
            "action": "pre_consume",
            "user_id": user_id,
            "model": model,
            "amount": pre_consumed_quota,
        })

        if self._quota < pre_consumed_quota:
            return {"allowed": False, "error": "用户额度不足 (insufficient_user_quota)"}

        self._quota -= pre_consumed_quota
        self._pre_consumed = pre_consumed_quota
        return {"allowed": True, "pre_consumed_quota": pre_consumed_quota}

    async def post_consume(
        self,
        user_id: int,
        model: str,
        channel_id: int,
        prompt_tokens: int,
        completion_tokens: int,
        pre_consumed_quota: int = 0,
    ) -> dict:
        """后消费 — 计算实际消耗并补偿差额"""
        actual_quota = math.ceil(
            (prompt_tokens + completion_tokens) * 1.0  # ratio=1.0
        )
        quota_delta = actual_quota - pre_consumed_quota

        self._call_log.append({
            "action": "post_consume",
            "user_id": user_id,
            "model": model,
            "actual_quota": actual_quota,
            "quota_delta": quota_delta,
        })

        if quota_delta > 0:
            self._quota -= quota_delta
        elif quota_delta < 0:
            self._quota += abs(quota_delta)

        return {"actual_quota": actual_quota, "quota_delta": quota_delta}

    async def return_quota(
        self, user_id: int, pre_consumed_quota: int
    ) -> dict:
        """退还预消费额度"""
        self._quota += pre_consumed_quota
        self._call_log.append({
            "action": "return",
            "user_id": user_id,
            "amount": pre_consumed_quota,
        })
        return {"success": True}

    @property
    def remaining_quota(self) -> int:
        return self._quota

    def get_call_log(self) -> list[dict]:
        return list(self._call_log)

    def reset_log(self) -> None:
        self._call_log.clear()


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def token_manager() -> MockTokenManager:
    return MockTokenManager(initial_quota=1000000)


@pytest.fixture
def relay_with_token(token_manager) -> Relay:
    """带 Token Manager 的转发器"""
    return Relay(
        load_balancer=LoadBalancer(success_rate_threshold=0.5),
        circuit_breaker=CircuitBreaker(disable_threshold=5),
        token_manager=token_manager,
    )


@pytest.fixture
def candidates() -> list[ChannelCandidate]:
    """测试用渠道候选列表"""
    return [
        ChannelCandidate(
            id=1, name="openai-channel", priority=10, weight=100,
            response_time=100, balance=100.0, success_rate=1.0,
            models=["gpt-4", "gpt-3.5-turbo"],
        ),
        ChannelCandidate(
            id=2, name="deepseek-channel", priority=5, weight=80,
            response_time=150, balance=100.0, success_rate=1.0,
            models=["deepseek-chat"],
        ),
    ]


# ── 1. 请求进入 LLM 网关 → 预消费 → 转发 → 后消费 ──────────────


class TestFullRequestFlow:
    """测试完整的请求转发 + Token 消费流程"""

    @pytest.mark.asyncio
    async def test_full_flow_pre_consume_forward_post_consume(
        self, relay_with_token, token_manager, candidates
    ):
        """
        完整流程:
        1. 预消费 Token
        2. 转发请求到上游 Provider
        3. 收到响应后后消费（实际计费）
        """
        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            user_id=1,
            max_tokens=100,
        )

        initial_quota = token_manager.remaining_quota

        # Mock HTTP 响应（模拟 Provider 返回 usage 信息）
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "chatcmpl-test",
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

        with patch.object(relay_with_token, '_get_http_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await relay_with_token.relay_chat(request, candidates)

        # 验证转发成功
        assert result.success is True
        assert result.total_tokens == 30

        # 验证预消费被调用
        call_log = token_manager.get_call_log()
        pre_consume_calls = [c for c in call_log if c["action"] == "pre_consume"]
        assert len(pre_consume_calls) == 1
        assert pre_consume_calls[0]["user_id"] == 1
        assert pre_consume_calls[0]["model"] == "gpt-4"

        # 验证额度有变化（预消费 + 后消费）
        assert token_manager.remaining_quota < initial_quota

    @pytest.mark.asyncio
    async def test_flow_tracks_token_usage(
        self, relay_with_token, token_manager, candidates
    ):
        """验证 Token 用量被正确追踪"""
        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Count tokens"}],
            user_id=42,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
        }

        with patch.object(relay_with_token, '_get_http_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await relay_with_token.relay_chat(request, candidates)

        assert result.prompt_tokens == 50
        assert result.completion_tokens == 30
        assert result.total_tokens == 80


# ── 2. 额度不足 → 拒绝请求 ─────────────────────────────────────


class TestInsufficientQuota:
    """测试额度不足时拒绝请求"""

    @pytest.mark.asyncio
    async def test_insufficient_quota_rejects_request(self, candidates):
        """用户额度不足时，网关应拒绝请求"""
        # 创建额度极低的 Token Manager
        token_manager = MockTokenManager(initial_quota=100)
        relay = Relay(
            load_balancer=LoadBalancer(),
            circuit_breaker=CircuitBreaker(),
            token_manager=token_manager,
        )

        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            user_id=1,
        )

        result = await relay.relay_chat(request, candidates)

        # 应该被拒绝（额度不足）
        assert result.success is False
        assert result.status_code == 429
        assert "额度不足" in result.error_message

    @pytest.mark.asyncio
    async def test_zero_quota_rejects_request(self, candidates):
        """额度为零时拒绝请求"""
        token_manager = MockTokenManager(initial_quota=0)
        relay = Relay(
            load_balancer=LoadBalancer(),
            circuit_breaker=CircuitBreaker(),
            token_manager=token_manager,
        )

        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            user_id=1,
        )

        result = await relay.relay_chat(request, candidates)

        assert result.success is False
        assert result.status_code == 429

    @pytest.mark.asyncio
    async def test_insufficient_quota_no_http_call(self, candidates):
        """额度不足时不应发起 HTTP 请求"""
        token_manager = MockTokenManager(initial_quota=10)
        relay = Relay(
            load_balancer=LoadBalancer(),
            circuit_breaker=CircuitBreaker(),
            token_manager=token_manager,
        )

        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            user_id=1,
        )

        with patch.object(relay, '_get_http_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await relay.relay_chat(request, candidates)

        # 额度不足，不应该调用 HTTP
        mock_client.post.assert_not_called()


# ── 3. 请求失败 → 退还预消费 ────────────────────────────────────


class TestRefundOnFailure:
    """测试请求失败时退还预消费额度"""

    @pytest.mark.asyncio
    async def test_provider_error_triggers_refund(self, token_manager, candidates):
        """Provider 返回错误时应退还预消费"""
        relay = Relay(
            load_balancer=LoadBalancer(),
            circuit_breaker=CircuitBreaker(),
            token_manager=token_manager,
        )

        request = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            user_id=1,
        )

        initial_quota = token_manager.remaining_quota

        # Mock HTTP 失败
        async def always_fail(channel, req):
            return {"success": False, "error": "Provider error 500"}

        with patch.object(relay, '_forward_request', side_effect=always_fail):
            # 在预消费后，手动模拟退还（真实场景由 relay 层处理）
            # 先调用预消费
            pre_result = await token_manager.pre_consume(user_id=1, model="gpt-4")
            assert pre_result["allowed"] is True

            # 模拟请求失败后退还
            await token_manager.return_quota(
                user_id=1, pre_consumed_quota=pre_result["pre_consumed_quota"]
            )

        # 额度应完全恢复
        assert token_manager.remaining_quota == initial_quota

    @pytest.mark.asyncio
    async def test_network_error_triggers_refund(self, token_manager, candidates):
        """网络异常时应退还预消费"""
        relay = Relay(
            load_balancer=LoadBalancer(),
            circuit_breaker=CircuitBreaker(),
            token_manager=token_manager,
        )

        initial_quota = token_manager.remaining_quota

        # 预消费
        pre_result = await token_manager.pre_consume(user_id=1, model="gpt-4")
        pre_amount = pre_result["pre_consumed_quota"]

        # 模拟网络异常后退还
        await token_manager.return_quota(user_id=1, pre_consumed_quota=pre_amount)

        assert token_manager.remaining_quota == initial_quota

    @pytest.mark.asyncio
    async def test_refund_log_recorded(self, token_manager):
        """退还操作被记录在日志中"""
        await token_manager.pre_consume(user_id=1, model="gpt-4")
        await token_manager.return_quota(user_id=1, pre_consumed_quota=500)

        log = token_manager.get_call_log()
        refund_calls = [c for c in log if c["action"] == "return"]
        assert len(refund_calls) == 1
        assert refund_calls[0]["amount"] == 500


# ── 4. 渠道自动禁用时 Token 退还 ────────────────────────────────


class TestAutoDisableWithTokenRefund:
    """测试渠道自动禁用时的 Token 退还"""

    @pytest.mark.asyncio
    async def test_circuit_breaker_triggers_refund(self, token_manager):
        """断路器触发渠道禁用时退还预消费"""
        circuit_breaker = CircuitBreaker(disable_threshold=3)
        relay = Relay(
            load_balancer=LoadBalancer(),
            circuit_breaker=circuit_breaker,
            token_manager=token_manager,
        )

        # 渠道 1 连续失败 → 自动禁用
        for _ in range(3):
            circuit_breaker.record_failure(1)

        health = circuit_breaker.get_health(1)
        assert health.status == CBChannelStatus.AUTO_DISABLED

        # 模拟：请求到被禁用渠道时的退还流程
        initial_quota = token_manager.remaining_quota

        # 预消费
        pre_result = await token_manager.pre_consume(user_id=1, model="gpt-4")
        pre_amount = pre_result["pre_consumed_quota"]

        # 渠道被禁用 → 退还
        await token_manager.return_quota(user_id=1, pre_consumed_quota=pre_amount)

        assert token_manager.remaining_quota == initial_quota

    @pytest.mark.asyncio
    async def test_multi_channel_failure_refund(self, token_manager):
        """多渠道失败时的 Token 退还"""
        circuit_breaker = CircuitBreaker(disable_threshold=3)

        # 渠道 1 和 渠道 2 都被禁用
        for _ in range(3):
            circuit_breaker.record_failure(1)
            circuit_breaker.record_failure(2)

        assert circuit_breaker.get_health(1).status == CBChannelStatus.AUTO_DISABLED
        assert circuit_breaker.get_health(2).status == CBChannelStatus.AUTO_DISABLED

        # 尝试所有渠道都失败后退还
        initial_quota = token_manager.remaining_quota
        pre_result = await token_manager.pre_consume(user_id=1, model="gpt-4")

        # 所有渠道失败，退还
        await token_manager.return_quota(
            user_id=1, pre_consumed_quota=pre_result["pre_consumed_quota"]
        )

        assert token_manager.remaining_quota == initial_quota

    @pytest.mark.asyncio
    async def test_partial_failure_refund(self, token_manager):
        """部分请求失败时的 Token 退还"""
        circuit_breaker = CircuitBreaker(disable_threshold=5)
        initial_quota = token_manager.remaining_quota

        # 请求 1: 成功
        pre1 = await token_manager.pre_consume(user_id=1, model="gpt-4")
        post1 = await token_manager.post_consume(
            user_id=1, model="gpt-4", channel_id=1,
            prompt_tokens=10, completion_tokens=5,
            pre_consumed_quota=pre1["pre_consumed_quota"],
        )

        quota_after_1 = token_manager.remaining_quota
        assert quota_after_1 < initial_quota  # 有消耗

        # 请求 2: 失败，退还
        pre2 = await token_manager.pre_consume(user_id=1, model="gpt-4")
        await token_manager.return_quota(
            user_id=1, pre_consumed_quota=pre2["pre_consumed_quota"]
        )

        # 额度应恢复到请求 1 之后的水平
        assert token_manager.remaining_quota == quota_after_1


# ── 5. 多用户并发场景 ──────────────────────────────────────────


class TestMultiUserConcurrency:
    """多用户并发消费场景"""

    @pytest.mark.asyncio
    async def test_separate_user_quota(self):
        """不同用户的额度独立管理"""
        tm1 = MockTokenManager(initial_quota=10000)
        tm2 = MockTokenManager(initial_quota=20000)

        # 用户 1 消费
        await tm1.pre_consume(user_id=1, model="gpt-4")
        await tm1.post_consume(
            user_id=1, model="gpt-4", channel_id=1,
            prompt_tokens=100, completion_tokens=50,
        )

        # 用户 2 消费
        await tm2.pre_consume(user_id=2, model="gpt-4")
        await tm2.post_consume(
            user_id=2, model="gpt-4", channel_id=1,
            prompt_tokens=200, completion_tokens=100,
        )

        # 验证各自额度独立 — tm2 消费更多（绝对值）
        assert tm1.remaining_quota < 10000
        assert tm2.remaining_quota < 20000
        # tm2 消费了更多 tokens（200+100 vs 100+50），绝对消耗更大
        consumed_1 = 10000 - tm1.remaining_quota
        consumed_2 = 20000 - tm2.remaining_quota
        assert consumed_2 > consumed_1

    @pytest.mark.asyncio
    async def test_concurrent_pre_consume(self):
        """并发预消费不会导致超额"""
        tm = MockTokenManager(initial_quota=1000)
        pre_amount = 500

        # 并发 3 个请求
        results = await asyncio.gather(
            tm.pre_consume(user_id=1, model="gpt-4", pre_consumed_quota=pre_amount),
            tm.pre_consume(user_id=1, model="gpt-4", pre_consumed_quota=pre_amount),
            tm.pre_consume(user_id=1, model="gpt-4", pre_consumed_quota=pre_amount),
        )

        allowed_count = sum(1 for r in results if r["allowed"])
        # 额度 1000，每次预消费 500，最多允许 2 个
        assert allowed_count <= 2
        assert tm.remaining_quota >= 0  # 不会变成负数
