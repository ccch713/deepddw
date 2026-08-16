"""LLM router — rule-based provider selection with fallback chain (PRD §8.2).

Routing rules are configured in ``config/deployment.yaml`` under
``llm.routing_rules``. Each rule is a dict with:

* ``name`` — rule identifier
* ``provider`` — provider name (``minimax`` / ``deepseek`` / ``ollama``)
* ``model`` — model name within that provider
* ``cost_per_call`` — flat cost (CNY) for billing/observability

The router picks the first rule whose predicate matches; if no rule
matches, the default provider is used. If the selected provider
fails (network / auth), the fallback chain is walked.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from core.config import LLMRouteRule, get_deployment
from core.llm_gateway.base import (
    BaseLLMProvider,
    ChatMessage,
    ChatResponse,
    RouteContext,
)
from core.llm_gateway.deepseek import DeepSeekProvider
from core.llm_gateway.ollama import OllamaProvider
from core.llm_gateway.usage import UsageTracker

logger = logging.getLogger(__name__)


# Predicate signature: (messages, kwargs) -> bool
Predicate = Callable[[List[ChatMessage], Dict[str, Any]], bool]


# --------------------------------------------------------------------------- #
# Built-in predicates
# --------------------------------------------------------------------------- #


def _total_chars(messages: List[ChatMessage], _kwargs: Dict[str, Any]) -> bool:
    return sum(len(m.content) for m in messages) > 5000


def _has_chinese(messages: List[ChatMessage], _kwargs: Dict[str, Any]) -> bool:
    text = "".join(m.content for m in messages)
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _simple_chat(messages: List[ChatMessage], _kwargs: Dict[str, Any]) -> bool:
    return len(messages) <= 2 and sum(len(m.content) for m in messages) < 200


# Map rule name -> predicate (None = match-all).
_PREDICATES: Dict[str, Optional[Predicate]] = {
    "long_context": _total_chars,
    "complex_analysis": lambda msgs, kw: kw.get("complex") is True,
    "local_simple": _simple_chat,
    "simple_chat": lambda msgs, kw: True,
}


class LLMRouter:
    """Holds provider instances and applies routing rules + fallback chain."""

    def __init__(self, usage: Optional[UsageTracker] = None) -> None:
        self._providers: Dict[str, BaseLLMProvider] = {}
        self.usage = usage or UsageTracker()
        self._init_providers()

    # ------------------------------------------------------------------ #
    # Provider management
    # ------------------------------------------------------------------ #

    def _init_providers(self) -> None:
        # deepDDW 白名单通道：DeepSeek（云端）+ Ollama（本地）；商业渠道已移除
        self._providers["deepseek"] = DeepSeekProvider()
        self._providers["ollama"] = OllamaProvider()
        # Allow plugins to register custom providers via the gateway
        # (see core.llm_gateway.gateway.register_provider).

    def register_provider(self, provider: BaseLLMProvider) -> None:
        # P2-28：覆盖同名 provider 时关闭旧实例的 httpx client（防 fd 泄漏）
        old = self._providers.get(provider.name)
        if old is not None and old is not provider:
            try:
                import asyncio

                loop = asyncio.get_running_loop()
                loop.create_task(old.aclose())
            except RuntimeError:
                # 无运行中事件循环：无法 await，连接由进程退出时回收
                pass
        self._providers[provider.name] = provider

    async def aclose(self) -> None:
        """P1-14：关闭全部 provider 的 httpx client（lifespan finally 调用）。"""
        for provider in list(self._providers.values()):
            try:
                await provider.aclose()
            except Exception as exc:  # noqa: BLE001
                logger.debug("provider %s aclose failed: %s", provider.name, exc)
        self._providers.clear()

    def get(self, name: str) -> BaseLLMProvider:
        if name not in self._providers:
            raise KeyError(f"Unknown provider: {name}")
        return self._providers[name]

    # ------------------------------------------------------------------ #
    # Rule selection
    # ------------------------------------------------------------------ #

    def pick_rule(self, messages: List[ChatMessage], kwargs: Dict[str, Any]) -> LLMRouteRule:
        dep = get_deployment()
        for rule in dep.llm.routing_rules:
            predicate = _PREDICATES.get(rule.name)
            if predicate is None:
                # Unknown rule name: default to match (so it can still be used).
                return rule
            try:
                if predicate(messages, kwargs):
                    return rule
            except Exception as exc:  # noqa: BLE001
                logger.debug("rule %s predicate failed: %s", rule.name, exc)
                continue
        # Fall back: synthesise a rule from the default provider.
        return LLMRouteRule(
            name="default",
            provider=dep.llm.default_provider,
            model=self.get(dep.llm.default_provider).default_model,
            cost_per_call=0.0,
        )

    # ------------------------------------------------------------------ #
    # Main entry
    # ------------------------------------------------------------------ #

    async def chat(
        self,
        messages: List[ChatMessage],
        *,
        rule: Optional[str] = None,
        ctx: Optional[RouteContext] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Run a chat completion, honouring the routing rule and fallback chain."""

        if rule:
            dep = get_deployment()
            matched = next((r for r in dep.llm.routing_rules if r.name == rule), None)
            chosen = matched or self.pick_rule(messages, kwargs)
        else:
            chosen = self.pick_rule(messages, kwargs)

        ctx = ctx or RouteContext()
        ctx.rule = chosen.name

        chain = [chosen.provider] + \
            [p for p in get_deployment().llm.fallback_chain if p != chosen.provider]
        last_error: Optional[Exception] = None
        for provider_name in chain:
            try:
                provider = self.get(provider_name)
                response = await provider.chat(messages, model=chosen.model, **kwargs)
                self.usage.record(provider=provider_name, model=chosen.model,
                                  response=response, ctx=ctx, ok=response.finish_reason != "error")
                if response.finish_reason == "error":
                    # Provider 内部吞掉了异常并返回 error response（如 [minimax-error]）：
                    # 同样视为失败，继续走 fallback 链。
                    logger.warning("provider %s returned error response, trying next: %s",
                                   provider_name, response.content[:80])
                    last_error = RuntimeError(response.content[:200])
                    continue
                return response
            except Exception as exc:  # noqa: BLE001
                logger.warning("provider %s failed: %s", provider_name, exc)
                last_error = exc
                continue

        # All providers failed — return a safe default response.
        logger.error("LLM router: all providers failed: %s", last_error)
        return ChatResponse(
            content="[llm-router] all providers unavailable",
            model=chosen.model,
            provider=chosen.provider,
            finish_reason="error",
        )

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        *,
        rule: Optional[str] = None,
        ctx: Optional[RouteContext] = None,
        **kwargs: Any,
    ):
        """Yield tokens from the selected provider. Falls back to non-streaming chunks."""

        chosen = self.pick_rule(messages, kwargs)
        provider = self.get(chosen.provider)
        try:
            async for chunk in provider.stream_chat(messages, model=chosen.model, **kwargs):
                yield chunk
        except Exception as exc:  # noqa: BLE001
            logger.warning("stream failed, falling back: %s", exc)
            response = await self.chat(messages, rule=rule, ctx=ctx, **kwargs)
            yield response.content
