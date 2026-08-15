"""LLM Gateway - Unified entry point for LLM provider calls.

This is a lightweight stub suitable for plugin development. The real
implementation lives in the DDW AI Hub core; plugins only need to
import :func:`get_gateway` and use the returned object.

The stub preserves the contract so plugins can be tested in isolation
without a real provider configured.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from typing import Any, Optional


class LLMGateway:
    """Minimal LLM Gateway interface.

    Real implementation handles provider routing, retries, token
    accounting, and policy enforcement. The stub simulates just enough
    behaviour for plugin development and tests.
    """

    def __init__(self) -> None:
        self._calls: list[dict[str, Any]] = []
        self._default_model: str = "stub-embed-v1"

    async def embed(self, text: str, model: Optional[str] = None) -> list[float]:
        """Return a deterministic 8-dim embedding for ``text``.

        The vector is hashed from the text so similar inputs produce
        similar vectors (small numerical drift from tokenisation).
        """
        self._calls.append({"op": "embed", "model": model or self._default_model, "len": len(text)})
        return await asyncio.to_thread(_hash_embed, text)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return a stub chat completion response."""
        self._calls.append({"op": "chat", "model": model, "msgs": len(messages)})
        return {
            "model": model or self._default_model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "[stub] " + (messages[-1].get("content", "") if messages else ""),
                    },
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    @property
    def call_count(self) -> int:
        return len(self._calls)


def _hash_embed(text: str, dim: int = 8) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Stretch digest to ``dim`` floats in [-1, 1]
    floats: list[float] = []
    for i in range(dim):
        byte = digest[i % len(digest)]
        floats.append(math.sin(byte * (i + 1)) * 0.5)
    # L2 normalise
    norm = math.sqrt(sum(x * x for x in floats)) or 1.0
    return [x / norm for x in floats]


_GATEWAY: Optional[LLMGateway] = None


def get_gateway() -> LLMGateway:
    """Return a process-wide LLM Gateway singleton."""
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = LLMGateway()
    return _GATEWAY


def reset_gateway() -> None:
    """Reset the singleton (test helper)."""
    global _GATEWAY
    _GATEWAY = None
