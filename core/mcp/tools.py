"""DDW MCP 工具注册表（DDW AI Hub v5.4 — 模块 D1）。

每个工具通过 :class:`Tool` 描述，由 plugin 自动注册（也可手动 register）。

默认内置：
- ddw.llm.chat         LLM 对话
- ddw.kb.search        知识库搜索
- ddw.training.start_session  启动培训会话
- ddw.training.get_progress   查询学习进度
- ddw.smart_cs.handle_message 智能客服
- ddw.email.send       邮件发送
- ddw.hris.sync_employees     同步员工
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
        return {
            "content": [{"type": "text", "text": f"[stub LLM reply] 你说的是：{args.get('message', '')}"}],
            "model": "minimax-M3",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

    async def kb_search(args, ctx):
        q = args.get("query", "")
        return {
            "content": [{"type": "text", "text": f"[stub KB] 检索 {q} 返回 0 条结果"}],
            "results": [],
        }

    async def training_start(args, ctx):
        return {
            "content": [{"type": "text", "text": f"[stub] 已为用户 {args.get('user_id')} 启动培训会话"}],
            "session_id": "stub-session",
        }

    async def training_progress(args, ctx):
        return {
            "content": [{"type": "text", "text": "[stub] 进度：50%"}],
            "progress": 0.5,
        }

    async def smart_cs(args, ctx):
        return {
            "content": [{"type": "text", "text": f"[stub CS] 已收到：{args.get('message', '')}"}],
        }

    async def email_send(args, ctx):
        return {
            "content": [{"type": "text", "text": f"[stub email] 已发往 {args.get('to')} 主题 {args.get('subject', '')}"}],
        }

    async def hris_sync(args, ctx):
        return {
            "content": [{"type": "text", "text": f"[stub hris] 已同步 {args.get('adapter', 'kingdee')} 员工"}],
            "synced": 0,
        }

    registry.register(Tool(
        name="ddw.llm.chat",
        description="DDW LLM 对话。message: 用户消息；可选 system/model/temperature",
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
        description="DDW 知识库检索。query: 检索词；top_k: 返回条数（默认 5）",
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
        name="ddw.training.start_session",
        description="启动培训会话。user_id/course_id/subject",
        parameters={
            "properties": {
                "user_id": {"type": "string"},
                "course_id": {"type": "string"},
                "subject": {"type": "string"},
            },
            "required": ["user_id", "course_id"],
        },
        handler=training_start,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.training.get_progress",
        description="查询学习进度。session_id 或 user_id+course_id",
        parameters={
            "properties": {
                "session_id": {"type": "string"},
                "user_id": {"type": "string"},
                "course_id": {"type": "string"},
            },
        },
        handler=training_progress,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.smart_cs.handle_message",
        description="智能客服回复。message: 用户消息；session_id（可选）",
        parameters={
            "properties": {
                "message": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["message"],
        },
        handler=smart_cs,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.email.send",
        description="发送邮件。to/subject/body",
        parameters={
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
        handler=email_send,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.hris.sync_employees",
        description="同步员工。adapter: kingdee/wecom/beisen/feishu/dingtalk",
        parameters={
            "properties": {
                "adapter": {"type": "string", "enum": ["kingdee", "wecom", "beisen", "feishu", "dingtalk"]},
                "since": {"type": "string"},
            },
            "required": ["adapter"],
        },
        handler=hris_sync,
        plugin_name="core",
    ))


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
