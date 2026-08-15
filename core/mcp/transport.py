"""MCP 传输层（DDW AI Hub v5.4 — 模块 D1）。

- StdioTransport：本地 CLI，stdin/stdout
- SSETransport：服务器推送
- HTTPTransport：JSON-RPC over HTTP（最常用，由 FastAPI 端点承载）
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, AsyncIterator, Dict, Optional

logger = logging.getLogger(__name__)


class Transport:
    """所有传输的抽象基类。"""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send(self, message: Dict[str, Any]) -> None:
        raise NotImplementedError

    async def recv(self) -> Optional[Dict[str, Any]]:
        raise NotImplementedError


class StdioTransport(Transport):
    """本地 CLI 传输。"""

    def __init__(self) -> None:
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def start(self) -> None:
        loop = asyncio.get_event_loop()
        self._reader = asyncio.StreamReader(loop=loop)
        reader_protocol = asyncio.StreamReaderProtocol(self._reader)
        await loop.connect_read_pipe(lambda: reader_protocol, sys.stdin)
        w_transport, w_protocol = await loop.connect_write_pipe(asyncio.StreamReaderProtocol, sys.stdout)
        self._writer = asyncio.StreamWriter(w_transport, w_protocol, self._reader, loop)

    async def send(self, message: Dict[str, Any]) -> None:
        if self._writer is None:
            return
        line = json.dumps(message, ensure_ascii=False) + "\n"
        self._writer.write(line.encode("utf-8"))
        await self._writer.drain()

    async def recv(self) -> Optional[Dict[str, Any]]:
        if self._reader is None:
            return None
        line = await self._reader.readline()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None


class SSETransport(Transport):
    """SSE 传输（被动发送，主动接收走 POST）。"""

    def __init__(self, queue: Optional[asyncio.Queue] = None) -> None:
        self._q = queue or asyncio.Queue()

    async def send(self, message: Dict[str, Any]) -> None:
        await self._q.put(message)

    async def recv(self) -> Optional[Dict[str, Any]]:
        if self._q.empty():
            await asyncio.sleep(0.1)
        try:
            return self._q.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def stream(self) -> AsyncIterator[str]:
        while True:
            msg = await self._q.get()
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"


class HTTPTransport(Transport):
    """JSON-RPC over HTTP — 实际请求体由 FastAPI 端点接收。"""

    async def send(self, message: Dict[str, Any]) -> None:
        # HTTP 是请求-响应模式，send 由 HTTPResponse 直接写出
        logger.debug("HTTP transport send: %s", message)

    async def recv(self) -> Optional[Dict[str, Any]]:
        return None


__all__ = ["HTTPTransport", "SSETransport", "StdioTransport", "Transport"]
