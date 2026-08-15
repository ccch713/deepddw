"""LLM call wrapper for methodology distill engine.

Provides async LLM calls with retry and JSON parsing.
Uses DDW LLM gateway (Token Plaza).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default model and token limits per TASK_SPEC E.4
DEFAULT_MODEL = "minimax-m3"
DEFAULT_MAX_TOKENS = 8000
DEFAULT_TEMPERATURE = 0.3


async def call_llm(
    prompt: str,
    system: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    model: str = DEFAULT_MODEL,
) -> Optional[str]:
    """Call LLM via DDW gateway. Returns response text or None on failure."""
    try:
        from core.llm_gateway.base import ChatMessage
        from core.llm_gateway.gateway import chat as gateway_chat

        msgs = []
        if system:
            msgs.append(ChatMessage(role="system", content=system[:4000]))
        msgs.append(ChatMessage(role="user", content=prompt[:8000]))

        resp = await gateway_chat(
            msgs,
            max_tokens=max_tokens,
            temperature=temperature,
            model=model,
        )
        if resp and resp.content and resp.finish_reason != "error":
            return resp.content.strip()
        return None
    except Exception as exc:
        logger.warning("distill_llm: LLM call failed: %s", exc)
        return None


async def call_llm_json(
    prompt: str,
    system: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    model: str = DEFAULT_MODEL,
) -> Optional[dict[str, Any]]:
    """Call LLM and parse JSON response. Returns dict or None on failure."""
    raw = await call_llm(prompt, system, max_tokens, temperature, model)
    if not raw:
        return None

    # Try to extract JSON from markdown code blocks
    text = raw.strip()
    if text.startswith("```"):
        # Remove markdown code fence
        lines = text.split("\n")
        # Find opening and closing fences
        start = 0
        end = len(lines)
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                start = i + 1
                break
        for i in range(len(lines) - 1, start, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end]).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("distill_llm: Failed to parse JSON from LLM response: %s", text[:200])
        return None


async def call_llm_json_array(
    prompt: str,
    system: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    model: str = DEFAULT_MODEL,
) -> Optional[list[Any]]:
    """Call LLM and parse JSON array response. Returns list or None on failure."""
    raw = await call_llm(prompt, system, max_tokens, temperature, model)
    if not raw:
        return None

    # Try to extract JSON from markdown code blocks
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 0
        end = len(lines)
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                start = i + 1
                break
        for i in range(len(lines) - 1, start, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end]).strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        return None
    except json.JSONDecodeError:
        logger.warning("distill_llm: Failed to parse JSON array from LLM response: %s", text[:200])
        return None
