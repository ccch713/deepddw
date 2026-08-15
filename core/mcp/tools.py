"""deepDDW MCP 工具注册表（开源裁剪版）。

每个工具通过 :class:`Tool` 描述，由 plugin 自动注册（也可手动 register）。

deepDDW 0.1 默认内置（白名单组件，真实实现，非 stub）：
- ddw.llm.chat         LLM 对话（DeepSeek/Ollama 网关；断网降级不阻塞）
- ddw.kb.search        知识库搜索（SQLite FTS5/LIKE）

商业插件工具（ddw.training.* / ddw.smart_cs.* / ddw.email.send / ddw.hris.* 等）
随插件一起移除，绝不在开源版注册。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 避免循环导入：在 register_mcp_tool 内部延迟导入 mcp_tool_name


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)  # JSON Schema
    handler: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[Dict[str, Any]]]] = None
    is_read_only: bool = True
    plugin_name: str = "core"

    def to_mcp(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters.get("properties", {}),
                "required": self.parameters.get("required", []),
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool, override: bool = False) -> None:
        if not tool.name.startswith("ddw."):
            tool.name = f"ddw.{tool.name}"
        if tool.name in self._tools and not override:
            logger.warning("tool %s already registered, skip", tool.name)
            return
        self._tools[tool.name] = tool
        logger.info("registered tool %s (plugin=%s)", tool.name, tool.plugin_name)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list(self) -> List[Tool]:
        return list(self._tools.values())

    async def call(self, name: str, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tool = self.get(name)
        if tool is None:
            return {"error": {"code": -32002, "message": f"tool not found: {name}"}}
        if tool.handler is None:
            return {"error": {"code": -32603, "message": f"tool {name} has no handler"}}
        try:
            return await tool.handler(arguments or {}, context or {})
        except Exception as e:  # noqa: BLE001
            logger.exception("tool %s failed", name)
            return {"error": {"code": -32603, "message": f"tool execution failed: {e}"}}


# ---------------------------------------------------------------------------
# 内置工具（默认 handler 走 stub，生产可被 plugin 覆盖）
# ---------------------------------------------------------------------------


def install_default_tools(registry: ToolRegistry) -> None:
    async def llm_chat(args, ctx):
        """LLM 对话（真实网关实现；断网/无 Key 降级为友好提示，不阻塞主流程）。"""
        from core.llm_gateway.base import ChatMessage, RouteContext
        from core.llm_gateway.gateway import chat as llm_chat

        message = str(args.get("message", ""))
        system = args.get("system")
        try:
            messages = []
            if system:
                messages.append(ChatMessage(role="system", content=str(system)))
            messages.append(ChatMessage(role="user", content=message))
            resp = await llm_chat(messages, ctx=RouteContext(extra={"source": "mcp"}))
            if getattr(resp, "finish_reason", None) == "error":
                raise RuntimeError(resp.content)
            return {
                "content": [{"type": "text", "text": resp.content}],
                "model": resp.model,
                "provider": resp.provider,
                "usage": {
                    "prompt_tokens": resp.tokens_in,
                    "completion_tokens": resp.tokens_out,
                },
            }
        except Exception as exc:  # noqa: BLE001  # 断网/网关故障降级
            logger.warning("mcp llm.chat degraded: %s", exc)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "[deepDDW] LLM 网关暂不可用（无 API Key 或网络故障），"
                            "对话主流程未阻塞。请配置 DDW_DEEPSEEK_API_KEY 或本机 Ollama。"
                        ),
                    }
                ],
                "model": "unavailable",
                "provider": "degraded",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }

    async def kb_search(args, ctx):
        """知识库检索（真实 SQLite 实现）。"""
        from core.knowledge import kb_search as _kb_search

        q = str(args.get("query", ""))
        top_k = int(args.get("top_k") or 5)
        result = _kb_search(q, top_k)
        items = result.get("results", [])
        if not items:
            text = f"知识库未命中“{q}”（degraded={result.get('degraded', False)}）"
        else:
            text = "知识库检索结果：\n" + "\n".join(
                f"- {it['title']}: {it['excerpt']}" for it in items[:5]
            )
        return {
            "content": [{"type": "text", "text": text}],
            "results": items,
            "degraded": result.get("degraded", False),
        }

    registry.register(Tool(
        name="ddw.llm.chat",
        description="deepDDW LLM 对话。message: 用户消息；可选 system/model/temperature",
        parameters={
            "properties": {
                "message": {"type": "string", "description": "用户消息"},
                "system": {"type": "string", "description": "系统提示词（可选）"},
                "model": {"type": "string", "description": "模型（可选）"},
                "temperature": {"type": "number", "description": "温度（可选）"},
            },
            "required": ["message"],
        },
        handler=llm_chat,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.kb.search",
        description="deepDDW 知识库检索。query: 检索词；top_k: 返回条数（默认 5）",
        parameters={
            "properties": {
                "query": {"type": "string", "description": "检索词"},
                "top_k": {"type": "integer", "description": "返回条数"},
            },
            "required": ["query"],
        },
        handler=kb_search,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.memory.put",
        description="写入一条长期记忆。namespace/key/value；可选 tags 数组",
        parameters={
            "properties": {
                "namespace": {"type": "string", "description": "命名空间（默认 default）"},
                "key": {"type": "string", "description": "记忆键"},
                "value": {"type": "string", "description": "记忆内容"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "标签（可选）"},
            },
            "required": ["key", "value"],
        },
        handler=memory_put_handler,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.memory.search",
        description="检索记忆。query: 检索词；namespace（可选）；top_k（默认 5）",
        parameters={
            "properties": {
                "query": {"type": "string", "description": "检索词"},
                "namespace": {"type": "string", "description": "命名空间（默认 default）"},
                "top_k": {"type": "integer", "description": "返回条数"},
            },
            "required": ["query"],
        },
        handler=memory_search_handler,
        plugin_name="core",
    ))


async def memory_put_handler(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """ddw.memory.put 真实 handler（SQLite 记忆存储）。"""
    from core.knowledge import memory_put

    try:
        result = memory_put(
            namespace=str(args.get("namespace") or "default"),
            key=str(args.get("key", "")),
            value=str(args.get("value", "")),
            tags=list(args.get("tags") or []),
        )
        return {
            "content": [{"type": "text", "text": f"记忆已保存（id={result['id']}）"}],
            "ok": True,
            "id": result["id"],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp memory.put degraded: %s", exc)
        return {
            "content": [{"type": "text", "text": f"记忆保存失败（已降级，不影响对话）：{exc}"}],
            "ok": False,
            "degraded": True,
        }


async def memory_search_handler(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """ddw.memory.search 真实 handler（SQLite 记忆检索）。"""
    from core.knowledge import memory_search

    try:
        result = memory_search(
            namespace=str(args.get("namespace") or "default"),
            query=str(args.get("query", "")),
            top_k=int(args.get("top_k") or 5),
        )
        items = result.get("results", [])
        if not items:
            text = "记忆未命中（degraded={})".format(result.get("degraded", False))
        else:
            text = "记忆检索结果：\n" + "\n".join(
                f"- [{it['key']}] {it['value']}" for it in items[:5]
            )
        return {"content": [{"type": "text", "text": text}], "results": items}
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp memory.search degraded: %s", exc)
        return {
            "content": [{"type": "text", "text": f"记忆检索失败（已降级）：{exc}"}],
            "results": [],
            "degraded": True,
        }


__all__ = ["Tool", "ToolRegistry", "install_default_tools"]


# --------------------------------------------------------------------------- #
#  MCP 结果标准化（参照 Proma convertMcpResult）
# --------------------------------------------------------------------------- #


def convert_mcp_result(result: dict[str, Any]) -> dict[str, Any]:
    """将外部 MCP Server 返回的原始结果转换为 DDW 标准格式。

    DDW 标准工具结果格式 (与 MCP content[] 对齐)::

        {
            "content": [{"type": "text", "text": "..."}],
            "isError": False,
            "details": { ... }  # 原始返回值
        }

    处理逻辑（参照 Proma convertMcpResult）:
    1. 如果有 ``content`` 数组 → 直接使用（text/image 支持）
    2. 如果有 ``toolResult`` → 转为 text content
    3. 如果有 ``structuredContent`` → 追加为 JSON text
    4. 都没有 → 将整个结果 JSON 序列化为 text
    5. 如果 ``isError`` 为 True → 在 content 头部插入错误标记
    """
    content: list[dict[str, Any]] = []

    if "content" in result and isinstance(result["content"], list):
        for block in result["content"]:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    content.append({"type": "text", "text": block["text"]})
                elif block.get("type") == "image":
                    content.append({
                        "type": "image",
                        "data": block.get("data", ""),
                        "mimeType": block.get("mimeType", "image/png"),
                    })
                else:
                    content.append({"type": "text", "text": json.dumps(block, default=str, ensure_ascii=False)})
    elif "toolResult" in result:
        raw = result["toolResult"]
        content.append({
            "type": "text",
            "text": raw if isinstance(raw, str) else json.dumps(raw, default=str, ensure_ascii=False),
        })

    if "structuredContent" in result and result["structuredContent"] is not None:
        sc = result["structuredContent"]
        content.append({
            "type": "text",
            "text": f"structuredContent:\n{json.dumps(sc, default=str, ensure_ascii=False)}",
        })

    if not content:
        content.append({
            "type": "text",
            "text": json.dumps(result, default=str, ensure_ascii=False) if not isinstance(result, str) else result,
        })

    if result.get("isError"):
        content.insert(0, {"type": "text", "text": "MCP tool returned isError=true."})

    return {
        "content": content,
        "isError": result.get("isError", False),
        "details": result,
    }


def register_mcp_tool(
    registry: ToolRegistry,
    server_name: str,
    tool_name: str,
    description: str,
    parameters: dict[str, Any],
    call_fn: Any,
) -> Tool:
    """将外部 MCP Server 的 tool 注册为 DDW Tool。

    Args:
        registry: DDW ToolRegistry 实例
        server_name: MCP Server 名称
        tool_name: MCP 工具原始名称
        description: 工具描述
        parameters: JSON Schema 参数定义
        call_fn: 异步调用函数 ``(arguments: dict) -> dict``

    Returns:
        注册后的 Tool 实例
    """
    from core.mcp.client import mcp_tool_name as _mcp_tool_name

    full_name = _mcp_tool_name(server_name, tool_name)

    async def _handler(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        raw_result = await call_fn(args)
        return convert_mcp_result(raw_result)

    tool = Tool(
        name=full_name,
        description=f"[MCP:{server_name}] {description}",
        parameters=parameters,
        handler=_handler,
        is_read_only=False,  # MCP 工具默认为非只读
        plugin_name=f"mcp:{server_name}",
    )
    registry.register(tool, override=True)
    return tool
