"""DDW MCP stdio 服务器入口（v6.0，经典协议补全）。

用法（DSH / Claude Code 等以 stdio transport 连接）::

    python -m core.mcp.stdio_server

配置示例（客户端 mcp 配置）::

    "mcpServers": {
      "ddw": {
        "command": "python",
        "args": ["-m", "core.mcp.stdio_server"],
        "cwd": "/path/to/ddw-ai-hub"
      }
    }

底层复用与 streamable-http 相同的 FastMCP 实例（同一套工具/资源注册）。
"""

from __future__ import annotations

import asyncio
import logging

fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=fmt)


async def _main() -> None:
    from core.mcp.streamable_http import get_fastmcp

    mcp = get_fastmcp()
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(_main())
