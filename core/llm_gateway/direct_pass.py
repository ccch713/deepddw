"""P1: Direct pass mode — OpenAI native request passthrough (PRD v5.7 §32.2).

One API optimization: If the client sends OpenAI-format requests and the
target channel is also OpenAI-compatible, skip:
1. Request parsing and validation (~2ms)
2. Request format conversion (~5ms)
3. Response format conversion (~5ms)

Total latency reduction: 10-15ms (non-streaming) / 30-50% (streaming first token)
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Optional

import httpx

logger = logging.getLogger(__name__)

# Content types that indicate OpenAI-compatible format
_OPENAI_CONTENT_TYPES = (
    "application/json",
    "application/x-www-form-urlencoded",
)


class DirectPassAdaptor:
    """Direct passthrough for OpenAI-format requests.

    When the incoming request is already in OpenAI format and the target
    channel accepts OpenAI format, this adaptor forwards the raw bytes
    directly without any JSON parsing or conversion.
    """

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        self._client = http_client

    def is_openai_format(self, request_body: bytes, content_type: str = "") -> bool:
        """Detect if the request body is OpenAI-compatible format.

        Checks for the presence of "model" and "messages" keys in the JSON.
        """
        if not request_body:
            return False

        # Quick check: must be JSON content type
        if content_type and not any(ct in content_type for ct in _OPENAI_CONTENT_TYPES):
            return False

        try:
            data = json.loads(request_body)
            return isinstance(data, dict) and "model" in data and "messages" in data
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False

    async def direct_relay(
        self,
        upstream_url: str,
        api_key: str,
        request_body: bytes,
        headers: Optional[dict] = None,
    ) -> httpx.Response:
        """Forward the request directly without format conversion.

        Args:
            upstream_url: The target API endpoint URL.
            api_key: Bearer token for the upstream API.
            request_body: Raw request body bytes.
            headers: Optional additional headers to include.

        Returns:
            The raw httpx.Response from the upstream API.
        """
        relay_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": (headers or {}).get("Accept", "application/json"),
        }

        return await self._client.post(
            upstream_url,
            content=request_body,
            headers=relay_headers,
            timeout=60.0,
        )

    async def direct_stream_relay(
        self,
        upstream_url: str,
        api_key: str,
        request_body: bytes,
        headers: Optional[dict] = None,
    ) -> AsyncGenerator[bytes, None]:
        """Forward a streaming request directly.

        Yields raw bytes from the upstream SSE stream without parsing.
        """
        relay_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        async with self._client.stream(
            "POST",
            upstream_url,
            content=request_body,
            headers=relay_headers,
            timeout=httpx.Timeout(60.0, connect=10.0),
        ) as response:
            async for chunk in response.aiter_bytes():
                yield chunk
