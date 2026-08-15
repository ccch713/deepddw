"""MiniMax provider (PRD §8.3).

The MiniMax M3 API is OpenAI-compatible, so the only thing we
need is a configured HTTP client. In a deployment with no
``DDW_MINIMAX_API_KEY``, the provider operates in mock mode
(echoes the last user message back). This keeps the rest of the
codebase testable in CI without a real network round-trip.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from core.llm_gateway.base import (
    BaseLLMProvider,
    ChatMessage,
    ChatResponse,
    strip_think,
)

logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M3"

# MiniMax-M3/M2.x 是思考模型：<think>...</think> 会先消耗 max_tokens budget。
# 实战教训（2026-08-10）：max_tokens<8000 时正文常被截断（finish_reason=length，
# 内容为空）；max_tokens=4000 时 think 吃光全部额度。因此对思考模型强制下限。
THINKING_MAX_TOKENS_FLOOR = 8000
THINKING_MODEL_PREFIXES = ("MiniMax-M3", "MiniMax-M2")


class MiniMaxProvider(BaseLLMProvider):
    name = "minimax"
    default_model = DEFAULT_MODEL

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            api_key=api_key or os.getenv("DDW_MINIMAX_API_KEY", "") or self._deployment_key(),
            api_base=api_base or self._deployment_api_base(),
            model=model or self._deployment_model(),
            config=config,
        )
        self._client: Optional[httpx.AsyncClient] = None

    @staticmethod
    def _deployment_yaml() -> Dict[str, Any]:
        """Read llm.providers.minimax from config/deployment.yaml (fallback key source)."""
        import yaml as _yaml

        for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
            cfg = base / "config" / "deployment.yaml"
            if cfg.exists():
                try:
                    d = _yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                    return d.get("llm", {}).get("providers", {}).get("minimax", {}) or {}
                except Exception:  # noqa: BLE001
                    return {}
        return {}

    @classmethod
    def _deployment_key(cls) -> str:
        return str(cls._deployment_yaml().get("api_key") or "")

    @classmethod
    def _deployment_api_base(cls) -> str:
        return str(cls._deployment_yaml().get("api_base") or DEFAULT_API_BASE)

    @classmethod
    def _deployment_model(cls) -> str:
        return str(cls._deployment_yaml().get("default_model") or DEFAULT_MODEL)

    async def _client_lazy(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.api_base,
                timeout=httpx.Timeout(60.0, connect=10.0),
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
            )
        return self._client

    @staticmethod
    def _guard_thinking_max_tokens(model: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """M3/M2.x 思考模型防呆：max_tokens 未传或低于下限时自动提升。

        思考模型会先输出 <think>...</think>，若 max_tokens 过小，正文
        会被截断（finish_reason=length）甚至完全为空。调用方显式传小值
        时同样提升（短回复场景只会多花一点套餐内额度，不会损坏语义）。
        """
        if not model.startswith(THINKING_MODEL_PREFIXES) or "highspeed" in model:
            return kwargs
        current = kwargs.get("max_tokens") or 0
        if current < THINKING_MAX_TOKENS_FLOOR:
            kwargs = {**kwargs, "max_tokens": THINKING_MAX_TOKENS_FLOOR}
            logger.info(
                "minimax thinking model %s: max_tokens raised %s -> %d",
                model, current or "unset", THINKING_MAX_TOKENS_FLOOR,
            )
        return kwargs

    async def chat(self, messages: List[ChatMessage], *, model: Optional[str] = None, **kwargs: Any) -> ChatResponse:
        start = time.time()
        m = self.resolve_model(model)
        # No API key → mock mode.
        if not self.api_key:
            content = self._mock_reply(messages)
            return ChatResponse(
                content=content,
                model=m,
                provider=self.name,
                tokens_in=sum(len(x.content) for x in messages) // 4,
                tokens_out=len(content) // 4,
                cost=0.004,
                latency_ms=int((time.time() - start) * 1000),
                finish_reason="stop",
            )

        client = await self._client_lazy()
        kwargs = self._guard_thinking_max_tokens(m, kwargs)
        payload = {"model": m, "messages": self._to_messages(messages), **kwargs}
        try:
            r = await client.post("/chat/completions", json=payload)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("MiniMax chat failed: %s", exc)
            # Fall back to a friendly error response so callers can still emit
            # something useful to the user.
            return ChatResponse(
                content=f"[minimax-error] {exc}",
                model=m,
                provider=self.name,
                cost=0.0,
                latency_ms=int((time.time() - start) * 1000),
                finish_reason="error",
            )

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return ChatResponse(
            content=strip_think(message.get("content", "")),
            model=m,
            provider=self.name,
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            cost=self._estimate_cost(usage.get("total_tokens", 0)),
            latency_ms=int((time.time() - start) * 1000),
            raw=data,
            finish_reason=choice.get("finish_reason"),
        )

    async def stream_chat(self, messages: List[ChatMessage], *, model: Optional[str] = None, **kwargs: Any) -> AsyncIterator[str]:
        """True SSE streaming — first token in ~200ms, no waiting for full generation."""
        import json as _json

        m = self.resolve_model(model)
        # No API key → mock mode
        if not self.api_key:
            content = self._mock_reply(messages)
            for i in range(0, len(content), 10):
                yield content[i : i + 10]
            return

        client = await self._client_lazy()
        stream_kwargs = {k: v for k, v in kwargs.items() if k not in ("timeout",)}
        stream_kwargs = self._guard_thinking_max_tokens(m, stream_kwargs)
        payload = {"model": m, "messages": self._to_messages(messages), "stream": True, **stream_kwargs}
        try:
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                in_think = False
                async for raw_line in resp.aiter_lines():
                    if not raw_line.startswith("data: "):
                        continue
                    data_str = raw_line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = _json.loads(data_str)
                        delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                        token = delta.get("content") or ""
                        if not token:
                            continue
                        # Strip <think>...</think> in real-time
                        if in_think:
                            if "</think>" in token:
                                in_think = False
                                token = token.split("</think>", 1)[1]
                            else:
                                continue
                        if "<think>" in token:
                            parts = token.split("<think>", 1)
                            in_think = True
                            token = parts[0]
                            if len(parts) > 1 and "</think>" in parts[1]:
                                in_think = False
                                token += parts[1].split("</think>", 1)[1]
                            else:
                                continue
                        if token:
                            yield token
                    except (_json.JSONDecodeError, KeyError, IndexError):
                        continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("MiniMax stream_chat failed: %s", exc)
            yield f"[minimax-error] {exc}"

    async def health(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"provider": self.name, "ok": True, "mode": "mock", "model": self.default_model}
        try:
            client = await self._client_lazy()
            r = await client.get("/models")
            return {"provider": self.name, "ok": r.status_code == 200, "mode": "live", "model": self.default_model}
        except Exception as exc:  # noqa: BLE001
            return {"provider": self.name, "ok": False, "error": str(exc), "model": self.default_model}

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _mock_reply(messages: List[ChatMessage]) -> str:
        last = next((m for m in reversed(messages) if m.role == "user"), None)
        if last is None:
            return "(no input)"
        return f"[MiniMax M3 mock] I received: {last.content[:200]}"

    @staticmethod
    def _estimate_cost(tokens: int) -> float:
        # Placeholder: ¥0.004 per 1k tokens; revisit per MiniMax pricing.
        return round(tokens / 1000.0 * 0.004, 6)
