"""EmbeddedLLM echo backend stub for standalone/on-premise deployment.

In production, replace EchoBackend with a real backend (llama.cpp, API, etc.).
The echo backend returns a structured placeholder response for testing.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EchoBackend:
    """Echo backend: returns a placeholder response for each capability."""

    def __init__(self) -> None:
        self.name = "echo"


class EmbeddedLLM:
    """Lightweight LLM wrapper for plugin use.

    Default backend is echo (no external API dependency).
    """

    def __init__(self, knowledge_dir: Optional[str] = None) -> None:
        self._backend = EchoBackend()
        self._knowledge_dir = knowledge_dir
        logger.info("EmbeddedLLM initialized with echo backend")

    async def chat(self, prompt: str, system: Optional[str] = None) -> str:
        """Send a prompt to the LLM and return the response.

        Echo backend returns a structured placeholder.
        """
        # In real deployment, this would call the actual LLM
        # For now, return a helpful echo response
        if "transcri" in (system or "").lower() or "转写" in (system or ""):
            return json.dumps({
                "speaker": "unknown",
                "text": "[转写功能需要配置真实LLM后端]",
                "confidence": 0.0
            }, ensure_ascii=False)
        elif "summar" in (system or "").lower() or "摘要" in (system or ""):
            return json.dumps({
                "summary": "[摘要功能需要配置真实LLM后端]",
                "key_points": []
            }, ensure_ascii=False)
        elif "todo" in (system or "").lower() or "待办" in (system or ""):
            return json.dumps({
                "todos": []
            }, ensure_ascii=False)
        elif "entit" in (system or "").lower() or "实体" in (system or ""):
            return json.dumps({
                "entities": []
            }, ensure_ascii=False)
        else:
            return f"[Echo] 收到 {len(prompt)} 字符的提示词。请配置真实LLM后端以获得实际响应。"

    async def embed(self, text: str) -> list[float]:
        """Return a dummy embedding vector."""
        return [0.0] * 384


__all__ = ["EmbeddedLLM", "EchoBackend"]
