"""
流式 SSE 处理器 — 异步 SSE 转发

映射源: One API relay/controller/text.go Stream 处理

核心职责:
1. 接收上游 LLM 的 SSE 流
2. 解析 SSE 数据格式
3. 注入 Token 计量（含按字数估算 fallback）
4. 转发给下游客户端
5. 错误处理和超时控制
6. 流式结束后记录用量到数据库
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Callable

from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

# 估算常量：每 token 约 4 字符（英文），中文约 2 字符/token
_CHARS_PER_TOKEN_ESTIMATE = 4


class StreamUsageTracker:
    """流式响应的 token 用量追踪器"""

    def __init__(self) -> None:
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self._collected_content: list[str] = []
        self._has_explicit_usage: bool = False

    def update_from_chunk(self, data: dict) -> None:
        """从 SSE chunk 更新用量（优先使用显式 usage）"""
        if "usage" in data and data["usage"]:
            pass
            usage = data["usage"]
            self.prompt_tokens = usage.get("prompt_tokens", self.prompt_tokens)
            self.completion_tokens = usage.get("completion_tokens", self.completion_tokens)
            self.total_tokens = usage.get("total_tokens", self.total_tokens)
            self._has_explicit_usage = True
        # 收集 delta content 用于估算
        choices = data.get("choices", [])
        for choice in choices:
            delta = choice.get("delta", {})
            content = delta.get("content", "")
            if content:
                self._collected_content.append(content)

    def finalize(self, prompt_text: str = "") -> None:
        """流结束后：若无显式 usage，按字数估算"""
        if self._has_explicit_usage:
            return
        # 估算 completion tokens
        full_content = "".join(self._collected_content)
        if full_content:
            self.completion_tokens = max(1, len(full_content) // _CHARS_PER_TOKEN_ESTIMATE)
        # 估算 prompt tokens
        if prompt_text:
            self.prompt_tokens = max(1, len(prompt_text) // _CHARS_PER_TOKEN_ESTIMATE)
        self.total_tokens = self.prompt_tokens + self.completion_tokens

    @property
    def has_usage(self) -> bool:
        return self.total_tokens > 0


class StreamHandler:
    """
    流式 SSE 处理器

    映射: relay/controller/text.go — StreamResponse 处理
    核心: 接收上游 SSE → 解析 → 注入 Token 计量 → 转发给下游

    SSE 格式:
    data: {"id":"chatcmpl-xxx","choices":[{"delta":{"content":"Hello"}}]}
    data: [DONE]
    """

    def __init__(self, buffer_size: int = 1024, timeout: float = 60.0):
        """
        初始化流式处理器

        Args:
            buffer_size: 缓冲区大小（字节）
            timeout: 超时时间（秒）
        """
        self._buffer_size = buffer_size
        self._timeout = timeout

    async def relay_stream(
        self,
        upstream_stream: AsyncGenerator[str, None],
        on_chunk: Callable[[dict], None] | None = None,
    ) -> StreamingResponse:
        """
        将上游流式响应转发为 SSE 响应

        Args:
            upstream_stream: 上游 LLM 的 SSE 流
            on_chunk: 每个 chunk 的回调（用于 Token 计量）

        Returns:
            FastAPI StreamingResponse
        """
        async def generate():
            async for chunk in upstream_stream:
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        yield "data: [DONE]\n\n"
                        break

                    try:
                        data = json.loads(data_str)
                        # 提取 usage 信息（最后一个 chunk）
                        if "usage" in data:
                            pass
                        # 回调：用于 Token 计量
                        if on_chunk:
                            on_chunk(data)
                        yield f"data: {data_str}\n\n"
                    except json.JSONDecodeError:
                        yield f"data: {data_str}\n\n"
                else:
                    yield f"{chunk}\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def relay_stream_with_usage(
        self,
        upstream_stream: AsyncGenerator[str, None],
        token_manager: object | None = None,
        channel_id: int = 0,
        model: str = "",
        user_id: int = 0,
    ) -> StreamingResponse:
        """
        带 Token 计量的流式转发

        流式结束后，根据最后一个 chunk 的 usage 信息
        调用 token_manager.post_consume() 进行后置计费。
        """
        collected_usage: dict = {}

        def on_chunk(data: dict) -> None:
            if "usage" in data:
                collected_usage.update(data["usage"])

        response = await self.relay_stream(upstream_stream, on_chunk)

        # 后置计费（流结束后）
        if token_manager and collected_usage:
            try:
                await token_manager.post_consume(
                    channel_id=channel_id,
                    model=model,
                    user_id=user_id,
                    prompt_tokens=collected_usage.get("prompt_tokens", 0),
                    completion_tokens=collected_usage.get("completion_tokens", 0),
                )
            except Exception as e:
                logger.error("后置计费失败: %s", e)

        return response

    async def relay_stream_with_billing(
        self,
        upstream_stream: AsyncGenerator[str, None],
        *,
        channel_id: int = 0,
        model: str = "",
        user_id: int = 0,
        prompt_text: str = "",
        token_manager: object | None = None,
        db_writer: Callable[[dict[str, Any]], None] | None = None,
    ) -> StreamingResponse:
        """
        带完整计费的流式转发

        在 relay_stream_with_usage 基础上增加：
        - 无显式 usage 时按字数估算 token
        - 流式结束后通过 db_writer 记录到数据库

        Args:
            upstream_stream: 上游 LLM 的 SSE 流
            channel_id: 渠道 ID
            model: 模型名称
            user_id: 用户 ID
            prompt_text: prompt 文本（用于估算 prompt tokens）
            token_manager: Token 管理器（后置计费）
            db_writer: 数据库写入回调，接收 dict 含 channel_id/model/tokens 等
        """
        tracker = StreamUsageTracker()
        start_time = time.monotonic()

        async def billing_generator():
            async for chunk in upstream_stream:
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        yield "data: [DONE]\n\n"
                        break
                    try:
                        data = json.loads(data_str)
                        tracker.update_from_chunk(data)
                        yield f"data: {data_str}\n\n"
                    except json.JSONDecodeError:
                        yield f"data: {data_str}\n\n"
                else:
                    yield f"{chunk}\n"

            # 流结束后处理计费
            tracker.finalize(prompt_text=prompt_text)
            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            if token_manager and tracker.has_usage:
                try:
                    await token_manager.post_consume(
                        channel_id=channel_id,
                        model=model,
                        user_id=user_id,
                        prompt_tokens=tracker.prompt_tokens,
                        completion_tokens=tracker.completion_tokens,
                    )
                except Exception as e:
                    logger.error("后置计费失败: %s", e)

            if db_writer and tracker.has_usage:
                try:
                    db_writer({
                        "channel_id": channel_id,
                        "model": model,
                        "user_id": user_id,
                        "prompt_tokens": tracker.prompt_tokens,
                        "completion_tokens": tracker.completion_tokens,
                        "total_tokens": tracker.total_tokens,
                        "is_stream": True,
                        "response_time": elapsed_ms,
                        "created_time": int(time.time()),
                    })
                except Exception as e:
                    logger.error("流式计费记录写入失败: %s", e)

        return StreamingResponse(
            billing_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def relay_stream_with_timeout(
        self,
        upstream_stream: AsyncGenerator[str, None],
        timeout: float | None = None,
    ) -> StreamingResponse:
        """
        带超时控制的流式转发

        Args:
            upstream_stream: 上游 LLM 的 SSE 流
            timeout: 超时时间（秒），默认使用初始化时的值
        """
        effective_timeout = timeout or self._timeout

        async def generate():
            try:
                async with asyncio.timeout(effective_timeout):
                    async for chunk in upstream_stream:
                        if chunk.startswith("data: "):
                            data_str = chunk[6:].strip()
                            if data_str == "[DONE]":
                                yield "data: [DONE]\n\n"
                                break
                            yield f"data: {data_str}\n\n"
                        else:
                            yield f"{chunk}\n"
            except asyncio.TimeoutError:
                logger.warning("流式转发超时 (%.1fs)", effective_timeout)
                yield f"data: {json.dumps({'error': 'stream timeout'})}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @staticmethod
    def parse_sse_line(line: str) -> dict | None:
        """
        解析 SSE 数据行

        Args:
            line: SSE 数据行（如 "data: {...}"）

        Returns:
            解析后的字典，或 None（非数据行或 [DONE]）
        """
        if not line.startswith("data: "):
            return None
        data_str = line[6:].strip()
        if data_str == "[DONE]":
            return None
        try:
            return json.loads(data_str)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def build_sse_chunk(data: dict | str) -> str:
        """
        构建 SSE 数据块

        Args:
            data: 数据字典或字符串

        Returns:
            格式化的 SSE 数据行
        """
        if isinstance(data, str):
            return f"data: {data}\n\n"
        return f"data: {json.dumps(data)}\n\n"
