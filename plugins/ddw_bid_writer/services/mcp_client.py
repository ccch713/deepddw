"""MCP 客户端封装：调用 core/mcp 的 ddw.llm.chat / ddw.kb.search。

设计：插件不直接 import core/mcp 内部类，而是通过 MCP server 的
JSON-RPC 接口或直接 tool registry 调用。这样避免循环依赖。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM 调用
# ---------------------------------------------------------------------------


class MCPClient:
    """DDW MCP 工具调用客户端。

    用法：
        client = MCPClient()
        text = await client.llm_chat("帮我写标书", system="...")
        results = await client.kb_search("桩基础", top_k=3)
    """

    def __init__(self) -> None:
        self._server = None
        self._initialized = False

    def _ensure(self) -> None:
        if self._initialized:
            return
        try:
            from core.mcp.server import get_mcp_server

            self._server = get_mcp_server()
            self._initialized = True
        except Exception as e:  # noqa: BLE001
            logger.warning("MCP server not available, fallback to stub: %s", e)
            self._server = None
            self._initialized = True  # 不要再尝试

    async def llm_chat(
        self,
        message: str,
        system: str = "",
        model: str = "minimax-M3",
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """调用 LLM。返回纯文本。"""
        self._ensure()
        if self._server is None:
            return self._stub_llm(message, system)
        try:
            result = await self._server.tools.call(
                "ddw.llm.chat",
                {
                    "message": message,
                    "system": system,
                    "model": model,
                    "temperature": temperature,
                },
                context={"max_tokens": max_tokens},
            )
            if "error" in result:
                logger.warning("MCP llm_chat error: %s", result["error"])
                return self._stub_llm(message, system)
            content = result.get("content", [])
            if isinstance(content, list) and content:
                return content[0].get("text", "")
            return str(content)
        except Exception as e:  # noqa: BLE001
            logger.warning("MCP llm_chat exception: %s", e)
            return self._stub_llm(message, system)

    async def kb_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """RAG 检索。"""
        self._ensure()
        if self._server is None:
            return []
        try:
            result = await self._server.tools.call(
                "ddw.kb.search",
                {"query": query, "top_k": top_k},
            )
            if "error" in result:
                return []
            results = result.get("results", [])
            if isinstance(results, list):
                return results
            return []
        except Exception as e:  # noqa: BLE001
            logger.warning("MCP kb_search exception: %s", e)
            return []

    @staticmethod
    def _stub_llm(message: str, system: str) -> str:
        """无 MCP 时的兜底：返回结构化模板（用于开发/测试）。"""
        sys_head = (system or "")[:80].replace("\n", " ")
        return (
            f"[stub-llm]\n"
            f"# 基于输入生成的占位内容\n\n"
            f"> system: {sys_head!r}\n\n"
            f"> user: {message[:120]!r}\n\n"
            f"## 1. 项目理解\n（待 LLM 生成）\n\n"
            f"## 2. 技术方案\n（待 LLM 生成）\n\n"
            f"## 3. 关键难点\n（待 LLM 生成）\n\n"
            f"## 4. 资源组织\n（待 LLM 生成）\n\n"
            f"## 5. 进度计划\n（待 LLM 生成）\n\n"
            f"## 6. 质量控制\n（待 LLM 生成）\n"
        )


# 进程级单例
_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    global _client
    if _client is None:
        _client = MCPClient()
    return _client


def set_mcp_client(client: MCPClient) -> None:
    """测试时注入。"""
    global _client
    _client = client


__all__ = ["MCPClient", "get_mcp_client", "set_mcp_client"]
