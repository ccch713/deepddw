"""DeepSeek V4 Pro provider (PRD §8.1 fallback chain position #2)."""

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

DEFAULT_API_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-v4-pro"


class DeepSeekProvider(BaseLLMProvider):
    name = "deepseek"
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
            api_key=api_key or os.getenv("DDW_DEEPSEEK_API_KEY", "") or self._deployment_key(),
            api_base=api_base or self._deployment_api_base(),
            model=model or self._deployment_model(),
            config=config,
        )
        self._client: Optional[httpx.AsyncClient] = None

    @staticmethod
    def _deployment_yaml() -> Dict[str, Any]:
        """Read llm.providers.deepseek from config/deployment.yaml (fallback key source)."""
        import yaml as _yaml

        for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
            cfg = base / "config" / "deployment.yaml"
            if cfg.exists():
                try:
                    d = _yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                    return d.get("llm", {}).get("providers", {}).get("deepseek", {}) or {}
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

    async def chat(self, messages: List[ChatMessage], *, model: Optional[str] = None, **kwargs: Any) -> ChatResponse:
        start = time.time()
        m = self.resolve_model(model)
        if not self.api_key:
            return ChatResponse(
                content=f"[DeepSeek V4 Pro mock] complex analysis of: {messages[-1].content[:150] if messages else ''}",
                model=m,
                provider=self.name,
                tokens_in=sum(len(x.content) for x in messages) // 4,
                tokens_out=20,
                cost=0.01,
                latency_ms=int((time.time() - start) * 1000),
                finish_reason="stop",
            )

        client = await self._client_lazy()
        payload = {"model": m, "messages": self._to_messages(messages), **kwargs}
        try:
            r = await client.post("/chat/completions", json=payload)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            return ChatResponse(
                content=f"[deepseek-error] {exc}",
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
        if not self.api_key:
            content = f"[DeepSeek V4 Pro mock] analysis of: {messages[-1].content[:200] if messages else ''}"
            for i in range(0, len(content), 10):
                yield content[i : i + 10]
            return

        client = await self._client_lazy()
        stream_kwargs = {k: v for k, v in kwargs.items() if k not in ("timeout",)}
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
            logger.warning("DeepSeek stream_chat failed: %s", exc)
            yield f"[deepseek-error] {exc}"

    async def health(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"provider": self.name, "ok": True, "mode": "mock", "model": self.default_model}
        return {"provider": self.name, "ok": True, "mode": "live", "model": self.default_model}

    @staticmethod
    def _estimate_cost(tokens: int) -> float:
        return round(tokens / 1000.0 * 0.01, 6)
