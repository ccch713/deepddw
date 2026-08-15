"""BaseLLMProvider — the common interface every provider implements.

The contract is intentionally minimal so a new provider can be
added in ~150 lines. Subclasses MUST implement :meth:`chat` and
:meth:`embed` (or raise :class:`NotImplementedError` if they don't
support the latter).

All providers expose:

* ``name`` — short identifier (``minimax``, ``deepseek``, ``ollama``)
* ``default_model`` — the model used when the caller doesn't specify one
* ``chat(messages, **kwargs)`` — single-turn or multi-turn chat
* ``stream_chat(messages, **kwargs)`` — async generator of token chunks
* ``health()`` — return provider health snapshot
"""

from __future__ import annotations

import abc
import logging
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think(text: str) -> str:
    """Remove ``<think>...</think>`` reasoning blocks from LLM output.

    MiniMax-M3 / DeepSeek 推理模型会在 content 中附带思考过程，
    展示给终端用户前必须剥离（2026-08-04 手机浏览器实测泄漏）。
    """
    if not text:
        return text
    return _THINK_RE.sub("", text).strip()


@dataclass
class ChatMessage:
    """A single chat message; role is one of {system,user,assistant}."""

    role: str
    content: str
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, str]:
        d = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class ChatResponse:
    """Normalised response returned by :meth:`BaseLLMProvider.chat`."""

    content: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    latency_ms: int = 0
    raw: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None


@dataclass
class Usage:
    """Token usage summary; useful for billing / observability."""

    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0


@dataclass
class RouteContext:
    """Routing context (user / tenant / explicit rule)."""

    user_id: Optional[int] = None
    tenant_id: Optional[int] = None
    rule: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class BaseLLMProvider(abc.ABC):
    """Abstract base class for all LLM providers."""

    name: str = "base"
    default_model: str = ""

    def __init__(self, *, api_key: Optional[str] = None, api_base: Optional[str] = None, model: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> None:
        self.api_key = api_key
        self.api_base = api_base
        if model:
            self.default_model = model
        self.config: Dict[str, Any] = dict(config or {})

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    @abc.abstractmethod
    async def chat(self, messages: List[ChatMessage], *, model: Optional[str] = None, **kwargs: Any) -> ChatResponse:
        """Run a chat completion; must return a :class:`ChatResponse`."""

    async def stream_chat(
        self, messages: List[ChatMessage], *, model: Optional[str] = None, **kwargs: Any
    ) -> AsyncIterator[str]:
        """Default: fall back to non-streaming and yield the whole text.

        Providers that support true token streaming override this.
        """

        response = await self.chat(messages, model=model, **kwargs)
        yield response.content

    async def embed(self, text: str, *, model: Optional[str] = None, **kwargs: Any) -> List[float]:
        """Return an embedding vector. Default: not implemented."""

        raise NotImplementedError(f"{self.name} does not support embeddings")

    async def health(self) -> Dict[str, Any]:
        """Return a small health snapshot. Default: assume healthy."""

        return {"provider": self.name, "ok": True, "model": self.default_model}

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def resolve_model(self, requested: Optional[str]) -> str:
        return requested or self.default_model

    def _to_messages(self, messages: List[ChatMessage]) -> List[Dict[str, str]]:
        return [m.to_dict() for m in messages]


__all__ = ["BaseLLMProvider", "ChatMessage", "ChatResponse", "Usage"]
