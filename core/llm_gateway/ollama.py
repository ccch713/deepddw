"""Ollama local provider (PRD §8.1 fallback chain position #3).

The Ollama API differs from OpenAI in two ways:

* It runs locally — ``api_base`` defaults to ``http://localhost:11434``.
* Embeddings live on a different path (``/api/embeddings``).

The provider also operates in **echo mode** when the local Ollama
daemon is not reachable, which is what happens in CI / dev. This
keeps the LLM Gateway testable without Docker.
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from core.llm_gateway.base import BaseLLMProvider, ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b"


class OllamaProvider(BaseLLMProvider):
    name = "ollama"
    default_model = DEFAULT_MODEL

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(api_key=None, api_base=api_base or DEFAULT_API_BASE, model=model, config=config)
        self._client: Optional[httpx.AsyncClient] = None

    async def _client_lazy(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.api_base,
                timeout=httpx.Timeout(120.0, connect=5.0),
            )
        return self._client

    async def chat(self, messages: List[ChatMessage], *, model: Optional[str] = None, **kwargs: Any) -> ChatResponse:
        start = time.time()
        m = self.resolve_model(model)
        client = await self._client_lazy()
        payload = {"model": m, "messages": self._to_messages(messages), "stream": False, **kwargs}
        try:
            r = await client.post("/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            # Local Ollama may not be running — degrade gracefully.
            logger.debug("Ollama unreachable, echo mode: %s", exc)
            last = messages[-1].content if messages else ""
            return ChatResponse(
                content=f"[Ollama echo] {last[:200]}",
                model=m,
                provider=self.name,
                tokens_in=len(last) // 4,
                tokens_out=20,
                cost=0.0,
                latency_ms=int((time.time() - start) * 1000),
                finish_reason="stop",
            )

        message = data.get("message") or {}
        return ChatResponse(
            content=message.get("content", ""),
            model=m,
            provider=self.name,
            tokens_in=int(data.get("prompt_eval_count", 0)),
            tokens_out=int(data.get("eval_count", 0)),
            cost=0.0,
            latency_ms=int((time.time() - start) * 1000),
            raw=data,
            finish_reason="stop",
        )

    async def stream_chat(self, messages: List[ChatMessage], *, model: Optional[str] = None, **kwargs: Any) -> AsyncIterator[str]:
        client = await self._client_lazy()
        m = self.resolve_model(model)
        payload = {"model": m, "messages": self._to_messages(messages), "stream": True, **kwargs}
        try:
            async with client.stream("POST", "/api/chat", json=payload) as r:
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    import json

                    try:
                        data = json.loads(line)
                    except Exception:  # noqa: BLE001
                        continue
                    chunk = (data.get("message") or {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
        except Exception as exc:  # noqa: BLE001
            logger.debug("Ollama stream failed, echo: %s", exc)
            full = await self.chat(messages, model=model, **kwargs)
            yield full.content

    async def embed(self, text: str, *, model: Optional[str] = None, **kwargs: Any) -> List[float]:
        client = await self._client_lazy()
        m = self.resolve_model(model) or "nomic-embed-text"
        r = await client.post("/api/embeddings", json={"model": m, "prompt": text})
        r.raise_for_status()
        data = r.json()
        return list(data.get("embedding", []))

    async def aclose(self) -> None:
        """P1-14：关闭内部 httpx client（防 fd 泄漏）。"""
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def health(self) -> Dict[str, Any]:
        # P1-11：Ollama 仅允许本机回环地址（防 api_base 指向任意主机 → SSRF 跳板）
        if not self._is_loopback_base():
            return {
                "provider": self.name, "ok": False,
                "error": "ollama base_url must be loopback (127.0.0.1/localhost/[::1])",
                "model": self.default_model, "mode": "blocked",
            }
        try:
            client = await self._client_lazy()
            r = await client.get("/api/tags", timeout=httpx.Timeout(3.0))
            return {"provider": self.name, "ok": r.status_code == 200, "model": self.default_model}
        except Exception as exc:  # noqa: BLE001
            return {"provider": self.name, "ok": False, "error": str(exc), "model": self.default_model, "mode": "echo"}

    def _is_loopback_base(self) -> bool:
        """base_url 主机名是否为回环（127.0.0.1 / localhost / [::1]）。"""
        import urllib.parse

        host = (urllib.parse.urlparse(self.api_base or "").hostname or "").lower()
        return host in ("127.0.0.1", "localhost", "::1")
