"""MiniMax LLM 客户端 — 对接 wenqu 苏格拉底对话。

M0-6 改造（2026-08-14）：优先走 DDW 底座 LLM Gateway
（token 计量由 gateway 自动发布 EventBus，复用底座不造轮子）；
gateway 异常/超时自动回退直连 MiniMax API（参考 ddw_online_cs 模式）。
"""
from __future__ import annotations

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)


class MiniMaxLLMClient:
    """调用底座 LLM Gateway（回退直连 MiniMax API）生成对话回复。"""

    def __init__(self):
        self.api_key = os.getenv("DDW_MINIMAX_API_KEY", "")
        self.base_url = os.getenv(
            "DDW_MINIMAX_BASE_URL",
            "https://api.minimaxi.com/v1",
        )
        if not self.api_key:
            try:
                with open(os.path.expanduser("~/.ddw_env")) as f:
                    for line in f:
                        if "MINIMAX_API_KEY" in line:
                            self.api_key = line.split("=", 1)[1].strip()
                            break
            except FileNotFoundError:
                pass
        logger.info("MiniMax client init: key=%s..., base=%s",
                     self.api_key[:10] if self.api_key else "NONE",
                     self.base_url)

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Remove <think>...</think> blocks from response."""
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return cleaned.strip()

    async def generate(
        self,
        model: str = "MiniMax-M3",
        system: str = "",
        user: str = "",
        temperature: float = 0.7,
        max_tokens: int = 8000,
    ) -> str:
        """调用底座 LLM Gateway（回退直连）生成回复，返回纯文本。

        token 计量：gateway 自动发布用量事件到 EventBus（底座能力）。
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        # 优先走底座 gateway（token 计量复用）
        try:
            from core.llm_gateway.base import ChatMessage
            from core.llm_gateway.gateway import chat as gateway_chat

            gm = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
            resp = await gateway_chat(
                gm,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            cleaned = self._strip_thinking(resp.content)
            logger.info(
                "Gateway reply: model=%s provider=%s in=%d out=%d preview=%s",
                resp.model, resp.provider, resp.tokens_in, resp.tokens_out,
                cleaned[:80],
            )
            return cleaned
        except Exception as e:  # noqa: BLE001
            logger.warning("Gateway chat failed (%s), fallback to direct MiniMax", e)

        # 回退：直连 MiniMax chat/completions
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            cleaned = self._strip_thinking(raw)
            logger.info("MiniMax direct reply: raw_len=%d preview=%s",
                        len(raw), cleaned[:80])
            return cleaned

    async def generate_stream(
        self,
        model: str = "MiniMax-M3",
        system: str = "",
        user: str = "",
        temperature: float = 0.7,
        max_tokens: int = 8000,
    ):
        """流式生成（SSE 用）：异步产出内容块。

        优先 gateway.stream_chat（token 计量复用）；异常回退直连流式。
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        try:
            from core.llm_gateway.base import ChatMessage
            from core.llm_gateway.gateway import stream_chat as gateway_stream

            gm = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
            async for chunk in gateway_stream(
                gm, max_tokens=max_tokens, temperature=temperature,
            ):
                if chunk:
                    yield chunk
            return
        except Exception as e:  # noqa: BLE001
            logger.warning("Gateway stream failed (%s), fallback to direct MiniMax", e)

        # 回退：直连 MiniMax 流式（SSE 格式解析）
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    import json

                    try:
                        delta = json.loads(data)["choices"][0]["delta"]["content"]
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
                    if delta:
                        yield delta


_default_client = None

def get_llm_client():
    global _default_client
    if _default_client is None:
        _default_client = MiniMaxLLMClient()
    return _default_client
