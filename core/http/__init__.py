"""P2: HTTP connection pool management (PRD v5.7 §32.3).

One API optimization: client.Init() configures MaxIdle/MaxOpen/MaxLifetime.

Python httpx equivalent:
- max_connections = MaxOpen (max simultaneous connections)
- max_keepalive_connections = MaxIdle (idle connection pool size)
- keepalive_expiry = MaxLifetime (idle connection max lifetime in seconds)
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class HTTPClientPool:
    """Singleton HTTP connection pool for all LLM provider connections.

    Shared across all providers to maximize connection reuse and avoid
    port exhaustion under high concurrency.
    """

    _instance: Optional[httpx.AsyncClient] = None
    _config: Optional[dict] = None

    @classmethod
    def get_client(
        cls,
        max_connections: int = 100,
        max_keepalive: int = 20,
        keepalive_expiry: int = 30,
        timeout: float = 60.0,
    ) -> httpx.AsyncClient:
        """Get or create the shared HTTP client singleton.

        Args:
            max_connections: Maximum total connections (MaxOpen).
            max_keepalive: Maximum idle connections in pool (MaxIdle).
            keepalive_expiry: Seconds before idle connections close (MaxLifetime).
            timeout: Default request timeout in seconds.

        Returns:
            A shared httpx.AsyncClient instance.
        """
        new_config = {
            "max_connections": max_connections,
            "max_keepalive": max_keepalive,
            "keepalive_expiry": keepalive_expiry,
            "timeout": timeout,
        }

        if cls._instance is not None and not cls._instance.is_closed:
            # Check if config changed — if so, recreate
            if cls._config == new_config:
                return cls._instance
            # Config changed, close old client
            logger.info("HTTP pool config changed, recreating client")
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Can't close in running loop; mark for lazy recreation
                    cls._instance = None
                else:
                    loop.run_until_complete(cls._instance.aclose())
                    cls._instance = None
            except Exception:
                cls._instance = None

        cls._config = new_config
        cls._instance = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive,
                keepalive_expiry=keepalive_expiry,
            ),
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=True,
        )
        logger.info(
            "HTTP pool created: max_conn=%d, keepalive=%d, expiry=%ds",
            max_connections,
            max_keepalive,
            keepalive_expiry,
        )
        return cls._instance

    @classmethod
    async def close(cls) -> None:
        """Close the shared HTTP client and release all connections."""
        if cls._instance is not None and not cls._instance.is_closed:
            await cls._instance.aclose()
            logger.info("HTTP pool closed")
        cls._instance = None
        cls._config = None

    @classmethod
    def get_stats(cls) -> dict:
        """Return connection pool statistics."""
        if cls._instance is None or cls._instance.is_closed:
            return {"status": "closed"}
        return {
            "status": "open",
            "config": cls._config or {},
        }
