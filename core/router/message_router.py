"""Message router (PRD §10.1, internal dispatch).

Decides whether an incoming IM message should be answered by:

* an installed plugin (skill / command match)
* the LLM gateway (default)

The router also publishes a ``message.received`` event on the
EventBus so plugins can subscribe and act.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from core.events.event_bus import Event, get_event_bus
from core.llm_gateway.base import ChatMessage as LLMChatMessage
from core.llm_gateway.gateway import chat as llm_chat
from core.llm_gateway.router import RouteContext
from core.plugin_manager.manager import get_plugin_manager

logger = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    user_id: str
    chat_id: str
    text: str
    metadata: Dict[str, Any] | None = None


# Plugin matchers can be registered; each returns a reply or None.
Handler = Callable[[IncomingMessage], Awaitable[Optional[str]]]


_handlers: List[Handler] = []


def register_handler(handler: Handler) -> None:
    _handlers.append(handler)


# --------------------------------------------------------------------------- #
# Built-in command: /help
# --------------------------------------------------------------------------- #


async def _help_command(msg: IncomingMessage) -> Optional[str]:
    if msg.text.strip() == "/help":
        return "Commands: /help, /plugins, /ping"
    return None


async def _plugins_command(msg: IncomingMessage) -> Optional[str]:
    if msg.text.strip() == "/plugins":
        pm = get_plugin_manager()
        names = [m.name for m in pm.list()]
        return "Loaded plugins: " + ", ".join(names)
    return None


async def _ping_command(msg: IncomingMessage) -> Optional[str]:
    if msg.text.strip() == "/ping":
        return "pong"
    return None


register_handler(_help_command)
register_handler(_plugins_command)
register_handler(_ping_command)


# --------------------------------------------------------------------------- #
# Public dispatch
# --------------------------------------------------------------------------- #


async def route(msg: IncomingMessage) -> str:
    """Dispatch ``msg`` to a handler, or fall back to the LLM."""

    bus = get_event_bus()
    await bus.publish(Event(topic="message.received", payload={"chat_id": msg.chat_id, "user_id": msg.user_id, "text": msg.text[:200]}))

    for handler in _handlers:
        try:
            reply = await handler(msg)
            if reply is not None:
                return reply
        except Exception as exc:  # noqa: BLE001
            logger.warning("handler %s failed: %s", handler.__name__, exc)

    # Default: forward to LLM.
    messages = [LLMChatMessage(role="user", content=msg.text)]
    ctx = RouteContext(extra={"chat_id": msg.chat_id, "user_id": msg.user_id})
    response = await llm_chat(messages, ctx=ctx)
    return response.content
