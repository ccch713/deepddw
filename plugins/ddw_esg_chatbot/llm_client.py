"""LLM client for DDW Gateway integration."""

from typing import Optional


class LLMClient:
    """Client for DDW Gateway LLM API.

    In production, this calls the DDW Gateway's chat-completion endpoint.
    For testing / stub mode, it returns deterministic mock responses.
    """

    def __init__(self, gateway_url: str = "http://localhost:8000"):
        self.gateway_url = gateway_url
        self.default_model = "deepseek-chat"

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict:
        """Send a chat completion request to the DDW Gateway.

        Returns a dict with keys: content, model, usage.
        """
        # In production, POST to {gateway_url}/v1/chat/completions
        # For now, return a mock response.
        content = self._build_mock_reply(messages)
        return {
            "content": content,
            "model": model or self.default_model,
            "usage": {"prompt_tokens": 100, "completion_tokens": len(content)},
        }

    async def health_check(self) -> bool:
        """Check if the LLM gateway is reachable."""
        # In production, GET {gateway_url}/health
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_mock_reply(messages: list[dict]) -> str:
        """Build a deterministic mock reply from the message list."""
        if not messages:
            return "No input provided."
        last = messages[-1].get("content", "")
        return (
            f"基于 ESG 知识库，关于「{last}」的回答：\n\n"
            "根据相关标准和最佳实践，建议您..."
        )
