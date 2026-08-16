"""LLM Gateway — the single entry point for the rest of the platform.

This module wraps :class:`LLMRouter` with a higher-level facade that
also takes care of:

* Loading rule configuration
* Publishing usage events on the EventBus (PRD §18.2)
* Exposing ``health()`` and ``providers()`` introspection helpers

API code (chat, messages, IM adapters) should always go through
this module — never instantiate providers directly.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional

from core.llm_gateway.base import BaseLLMProvider, ChatMessage, ChatResponse
from core.llm_gateway.router import LLMRouter, RouteContext
from core.llm_gateway.usage import UsageTracker

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_router() -> LLMRouter:
    """Process-wide cached :class:`LLMRouter`."""

    return LLMRouter()


def get_usage_tracker() -> UsageTracker:
    """Return the router's usage tracker (or a fresh one if no router yet)."""

    try:
        return get_router().usage
    except Exception:  # noqa: BLE001
        return UsageTracker()


# --------------------------------------------------------------------------- #
# High-level helpers
# --------------------------------------------------------------------------- #


async def chat(
    messages: List[ChatMessage],
    *,
    rule: Optional[str] = None,
    ctx: Optional[RouteContext] = None,
    **kwargs: Any,
) -> ChatResponse:
    return await get_router().chat(messages, rule=rule, ctx=ctx, **kwargs)


async def stream_chat(
    messages: List[ChatMessage],
    *,
    rule: Optional[str] = None,
    ctx: Optional[RouteContext] = None,
    **kwargs: Any,
):
    async for chunk in get_router().stream_chat(messages, rule=rule, ctx=ctx, **kwargs):
        yield chunk


async def health() -> Dict[str, Any]:
    """Return per-provider health snapshot."""

    router = get_router()
    result: Dict[str, Any] = {"providers": {}}
    for name, provider in router._providers.items():  # noqa: SLF001
        try:
            result["providers"][name] = await provider.health()
        except Exception as exc:  # noqa: BLE001
            result["providers"][name] = {"provider": name, "ok": False, "error": str(exc)}
    return result


def register_provider(provider: BaseLLMProvider) -> None:
    get_router().register_provider(provider)


async def aclose_all() -> None:
    """P1-14：关闭 LLM 网关全部底层 client（lifespan finally 调用）。"""
    try:
        await get_router().aclose()
        get_router.cache_clear()
    except Exception as exc:  # noqa: BLE001
        logger.debug("llm aclose_all failed: %s", exc)


__all__ = [
    "BaseLLMProvider",
    "ChatMessage",
    "ChatResponse",
    "RouteContext",
    "UsageTracker",
    "chat",
    "stream_chat",
    "health",
    "register_provider",
]
