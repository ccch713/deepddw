"""
请求转发核心 — OpenAI 兼容格式

映射源:
- One API relay/controller/text.go:TextHelper()
- One API relay/adaptor.go:Adaptor 接口

核心职责:
1. 接收 OpenAI 兼容格式请求
2. 选择渠道（负载均衡）
3. 转发请求到上游 LLM
4. 转发响应（非流式 + 流式）
5. 与 ddw-token-manager 集成（预消费/后消费）
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

import httpx

from .circuit_breaker import CircuitBreaker
from .load_balancer import ChannelCandidate, LoadBalancer

logger = logging.getLogger(__name__)


@dataclass
class RelayRequest:
    """转发请求"""
    model: str
    messages: list[dict] | None = None
    prompt: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stream: bool = False
    user_id: int = 0
    extra: dict = field(default_factory=dict)


@dataclass
class RelayResponse:
    """转发响应"""
    success: bool
    status_code: int = 200
    data: dict | None = None
    error_message: str = ""
    channel_id: int = 0
    channel_name: str = ""
    response_time: int = 0  # 毫秒
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Relay:
    """
    请求转发核心

    映射: relay/controller/text.go:TextHelper()

    流程:
    1. 从负载均衡器选择渠道
    2. 格式转换（标准格式 → Provider 格式）
    3. 发送请求到上游
    4. 处理响应（非流式 / 流式）
    5. 与 token_manager 集成
    """

    def __init__(
        self,
        load_balancer: LoadBalancer | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        token_manager: Any | None = None,
    ):
        """
        初始化转发器

        Args:
            load_balancer: 负载均衡器
            circuit_breaker: 断路器
            token_manager: Token 管理器（预消费/后消费集成）
        """
        self._load_balancer = load_balancer or LoadBalancer()
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._token_manager = token_manager
        self._http_client: httpx.AsyncClient | None = None

    async def relay_chat(
        self,
        request: RelayRequest,
        candidates: list[ChannelCandidate],
        max_retries: int = 3,
    ) -> RelayResponse:
        """
        转发 Chat Completion 请求

        对应 One API: relay/controller/text.go:TextHelper()

        Args:
            request: 转发请求
            candidates: 可用渠道候选列表
            max_retries: 最大重试次数

        Returns:
            转发响应
        """
        last_error = ""

        for attempt in range(max_retries):
            # 选择渠道
            ignore_first = attempt > 0
            channel = self._load_balancer.select(
                candidates,
                model=request.model,
                ignore_first_priority=ignore_first,
            )

            if not channel:
                return RelayResponse(
                    success=False,
                    status_code=503,
                    error_message=f"无可用渠道 (尝试 {attempt + 1}/{max_retries})",
                )

            # 预消费
            if self._token_manager:
                try:
                    pre_result = await self._token_manager.pre_consume(
                        user_id=request.user_id,
                        model=request.model,
                    )
                    if not pre_result.get("allowed", True):
                        return RelayResponse(
                            success=False,
                            status_code=429,
                            error_message=pre_result.get("error", "额度不足"),
                        )
                except Exception as e:
                    logger.error("预消费失败: %s", e)

            # 发送请求
            try:
                start_time = time.time()
                response = await self._forward_request(channel, request)
                response_time = int((time.time() - start_time) * 1000)

                if response.get("success"):
                    self._circuit_breaker.record_success(channel.id)
                    return RelayResponse(
                        success=True,
                        status_code=response.get("status_code", 200),
                        data=response.get("data"),
                        channel_id=channel.id,
                        channel_name=channel.name,
                        response_time=response_time,
                        prompt_tokens=response.get("usage", {}).get("prompt_tokens", 0),
                        completion_tokens=response.get("usage", {}).get("completion_tokens", 0),
                        total_tokens=response.get("usage", {}).get("total_tokens", 0),
                    )
                else:
                    self._circuit_breaker.record_failure(channel.id)
                    last_error = response.get("error", "未知错误")
                    logger.warning(
                        "请求失败 (渠道=%s, 尝试=%d): %s",
                        channel.name, attempt + 1, last_error
                    )

            except Exception as e:
                self._circuit_breaker.record_failure(channel.id)
                last_error = str(e)
                logger.error(
                    "请求异常 (渠道=%s, 尝试=%d): %s",
                    channel.name, attempt + 1, e
                )

        return RelayResponse(
            success=False,
            status_code=502,
            error_message=f"所有重试均失败: {last_error}",
        )

    async def relay_stream(
        self,
        request: RelayRequest,
        candidates: list[ChannelCandidate],
        max_retries: int = 3,
    ) -> AsyncGenerator[str, None]:
        """
        转发流式 Chat Completion 请求

        Args:
            request: 转发请求
            candidates: 可用渠道候选列表
            max_retries: 最大重试次数

        Yields:
            SSE 数据行
        """
        last_error = ""

        for attempt in range(max_retries):
            ignore_first = attempt > 0
            channel = self._load_balancer.select(
                candidates,
                model=request.model,
                ignore_first_priority=ignore_first,
            )

            if not channel:
                yield 'data: {"error": "无可用渠道"}\n\n'
                return

            try:
                async for chunk in self._forward_stream_request(channel, request):
                    yield chunk
                self._circuit_breaker.record_success(channel.id)
                return

            except Exception as e:
                self._circuit_breaker.record_failure(channel.id)
                last_error = str(e)
                logger.error(
                    "流式请求异常 (渠道=%s, 尝试=%d): %s",
                    channel.name, attempt + 1, e
                )

        yield f'data: {{"error": "所有重试均失败: {last_error}"}}\n\n'

    async def _forward_request(
        self,
        channel: ChannelCandidate,
        request: RelayRequest,
    ) -> dict:
        """
        转发非流式请求到上游 LLM

        Args:
            channel: 目标渠道
            request: 转发请求

        Returns:
            上游响应字典
        """
        client = await self._get_http_client()

        # 构建请求体
        body: dict[str, Any] = {"model": request.model}
        if request.messages is not None:
            body["messages"] = request.messages
        if request.prompt is not None:
            body["prompt"] = request.prompt
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.top_p is not None:
            body["top_p"] = request.top_p
        body.update(request.extra)

        # 构建 URL
        url = f"{channel.name}/v1/chat/completions"  # placeholder
        headers = {"Authorization": "Bearer placeholder"}

        try:
            resp = await client.post(url, json=body, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "status_code": 200,
                    "data": data,
                    "usage": data.get("usage", {}),
                }
            else:
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "error": resp.text,
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _forward_stream_request(
        self,
        channel: ChannelCandidate,
        request: RelayRequest,
    ) -> AsyncGenerator[str, None]:
        """
        转发流式请求到上游 LLM

        Args:
            channel: 目标渠道
            request: 转发请求

        Yields:
            SSE 数据行
        """
        client = await self._get_http_client()

        body: dict[str, Any] = {"model": request.model, "stream": True}
        if request.messages is not None:
            body["messages"] = request.messages
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            body["temperature"] = request.temperature

        url = f"{channel.name}/v1/chat/completions"
        headers = {"Authorization": "Bearer placeholder"}

        async with client.stream("POST", url, json=body, headers=headers, timeout=60) as resp:
            async for line in resp.aiter_lines():
                if line.strip():
                    yield f"{line}\n"

    async def _get_http_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
