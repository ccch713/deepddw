"""
流式 SSE 处理器测试

覆盖:
- StreamUsageTracker token 追踪
- 显式 usage 提取
- 按字数估算 fallback
- relay_stream_with_billing
"""
from __future__ import annotations

import pytest
from ddw_llm_gateway.stream_handler import StreamHandler, StreamUsageTracker


class TestStreamUsageTracker:
    """StreamUsageTracker 测试"""

    def test_initial_state(self):
        """初始状态为零"""
        tracker = StreamUsageTracker()
        assert tracker.prompt_tokens == 0
        assert tracker.completion_tokens == 0
        assert tracker.total_tokens == 0
        assert tracker.has_usage is False

    def test_update_from_explicit_usage(self):
        """从显式 usage 更新"""
        tracker = StreamUsageTracker()
        tracker.update_from_chunk({
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            }
        })
        assert tracker.prompt_tokens == 10
        assert tracker.completion_tokens == 20
        assert tracker.total_tokens == 30
        assert tracker.has_usage is True

    def test_update_from_delta_content(self):
        """从 delta content 收集文本"""
        tracker = StreamUsageTracker()
        tracker.update_from_chunk({
            "choices": [{"delta": {"content": "Hello"}}]
        })
        tracker.update_from_chunk({
            "choices": [{"delta": {"content": " world"}}]
        })
        assert tracker._collected_content == ["Hello", " world"]

    def test_finalize_with_explicit_usage(self):
        """有显式 usage 时 finalize 不覆盖"""
        tracker = StreamUsageTracker()
        tracker.update_from_chunk({
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        })
        tracker.finalize(prompt_text="some prompt")
        assert tracker.prompt_tokens == 10
        assert tracker.completion_tokens == 20

    def test_finalize_estimates_from_content(self):
        """无显式 usage 时按字数估算"""
        tracker = StreamUsageTracker()
        # 20 字符的 content → 约 5 tokens
        tracker.update_from_chunk({
            "choices": [{"delta": {"content": "This is twenty chars!"}}]
        })
        tracker.finalize()
        assert tracker.completion_tokens == 5  # 20 // 4
        assert tracker.has_usage is True

    def test_finalize_estimates_prompt(self):
        """估算 prompt tokens"""
        tracker = StreamUsageTracker()
        tracker.update_from_chunk({
            "choices": [{"delta": {"content": "Hi"}}]
        })
        # 40 字符的 prompt → 约 10 tokens
        tracker.finalize(prompt_text="This is a forty character prompt text!!")
        assert tracker.prompt_tokens > 0
        assert tracker.total_tokens == tracker.prompt_tokens + tracker.completion_tokens

    def test_finalize_empty_content(self):
        """空内容时 completion_tokens 为 0"""
        tracker = StreamUsageTracker()
        tracker.finalize()
        assert tracker.completion_tokens == 0
        assert tracker.has_usage is False


class TestStreamHandlerBilling:
    """relay_stream_with_billing 测试"""

    @pytest.mark.asyncio
    async def test_billing_records_usage(self):
        """计费模式记录用量"""
        handler = StreamHandler()

        async def mock_stream():
            yield 'data: {"id":"1","choices":[{"delta":{"content":"Hello"}}]}\n'
            yield 'data: {"id":"1","choices":[{"delta":{"content":" world"}}]}\n'
            yield 'data: {"id":"1","choices":[],"usage":{"prompt_tokens":5,"completion_tokens":2,"total_tokens":7}}\n'
            yield "data: [DONE]\n"

        recorded: list[dict] = []

        def db_writer(data: dict) -> None:
            recorded.append(data)

        response = await handler.relay_stream_with_billing(
            mock_stream(),
            channel_id=1,
            model="gpt-4",
            user_id=100,
            db_writer=db_writer,
        )

        # 流式响应需要消费 body
        body = b""
        async for chunk in response.body_iterator:
            body += chunk.encode() if isinstance(chunk, str) else chunk

        assert len(recorded) == 1
        assert recorded[0]["channel_id"] == 1
        assert recorded[0]["model"] == "gpt-4"
        assert recorded[0]["prompt_tokens"] == 5
        assert recorded[0]["completion_tokens"] == 2
        assert recorded[0]["is_stream"] is True

    @pytest.mark.asyncio
    async def test_billing_estimates_when_no_usage(self):
        """无显式 usage 时估算"""
        handler = StreamHandler()

        async def mock_stream():
            yield 'data: {"id":"1","choices":[{"delta":{"content":"Hello world!"}}]}\n'
            yield "data: [DONE]\n"

        recorded: list[dict] = []

        def db_writer(data: dict) -> None:
            recorded.append(data)

        response = await handler.relay_stream_with_billing(
            mock_stream(),
            channel_id=2,
            model="deepseek-chat",
            prompt_text="What is AI?",
            db_writer=db_writer,
        )

        body = b""
        async for chunk in response.body_iterator:
            body += chunk.encode() if isinstance(chunk, str) else chunk

        assert len(recorded) == 1
        assert recorded[0]["completion_tokens"] > 0  # 估算值
        assert recorded[0]["prompt_tokens"] > 0  # 估算值

    @pytest.mark.asyncio
    async def test_billing_no_db_writer(self):
        """无 db_writer 时不报错"""
        handler = StreamHandler()

        async def mock_stream():
            yield 'data: {"id":"1","choices":[{"delta":{"content":"Hi"}}]}\n'
            yield "data: [DONE]\n"

        response = await handler.relay_stream_with_billing(
            mock_stream(),
            channel_id=1,
            model="gpt-4",
        )
        assert response.status_code == 200
