"""DDW MCP 模块 — JSON-RPC 2.0 MCP Server + Client。

Server 端（已有）:
    DDWMCPServer — 处理 initialize/ping/tools/list/call/resources/list/read

Client 端（新增，参照 Proma PiMcpClientManager）:
    MCPClientManager — 连接外部 MCP Server，管理连接生命周期
    mcp_tool_name()  — 生成 DDW 风格的 MCP 工具名
"""

from core.mcp.client import (
    MCPClientManager,
    MCPServerConfig,
    get_mcp_client,
    mcp_tool_name,
)
from core.mcp.server import DDWMCPServer, get_mcp_server
from core.mcp.tools import Tool, ToolRegistry

__all__ = [
    # Server
    "DDWMCPServer",
    "get_mcp_server",
    # Client
    "MCPClientManager",
    "MCPServerConfig",
    "get_mcp_client",
    "mcp_tool_name",
    # Registry
    "Tool",
    "ToolRegistry",
]
