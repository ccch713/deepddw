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
    handler: Optional[Callable[[Dict[str, Any], Dict[str, Any]],
        Awaitable[Dict[str, Any]]]] = None
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

    async def call(
        self, name: str, arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
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
                "tags": {"type": "array", "items": {"type": "string"},
                       "description": "标签（可选）"},
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
    # 分层记忆（v2.1 记忆子系统，借鉴 dsh-auto-memory 设计）
    registry.register(Tool(
        name="ddw.memory.context",
        description=(
            "构建长期记忆注入块（用户偏好+项目笔记+最近日志+反思），"
            "chat 自动注入同源；供外部预览/调试。budget（可选，默认 2400 字符）"
        ),
        parameters={
            "properties": {
                "budget": {"type": "integer", "description": "预算字符数"},
            },
        },
        handler=memory_context_handler,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.memory.consolidate",
        description=(
            "记忆沉淀：把当前对话要点写入今日日志（自动沉淀，append-only）。"
            "content: 沉淀内容；llm=true 时用 LLM 提炼要点（失败规则降级，默认 true）"
        ),
        parameters={
            "properties": {
                "content": {"type": "string", "description": "沉淀内容/对话文本"},
                "llm": {"type": "boolean", "description": "是否 LLM 提炼（默认 true）"},
            },
            "required": ["content"],
        },
        handler=memory_consolidate_handler,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.memory.reflect",
        description=(
            "每日反思：昨天有日志且今天未反思时调用。"
            "generate=true 时 LLM 基于最近日志自动生成并保存（默认建议）；"
            "否则 content 直接存当日。style（可选，默认 auto）"
        ),
        parameters={
            "properties": {
                "generate": {"type": "boolean", "description": "LLM 自动生成（默认 false）"},
                "content": {"type": "string",
                            "description": "反思正文（generate=false 时必填）"},
                "style": {"type": "string", "description": "风格（默认 auto）"},
            },
        },
        handler=memory_reflect_handler,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.memory.maintain",
        description=(
            "记忆维护：当日写预算超限时归档最旧笔记到 archive，释放预算；"
            "返回归档数量与预算状态"
        ),
        parameters={},
        handler=memory_maintain_handler,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.memory.note",
        description=(
            "写一条项目笔记（分层记忆笔记层，先查后插 upsert）。"
            "key/value；source（可选，默认 deepddw）"
        ),
        parameters={
            "properties": {
                "key": {"type": "string", "description": "笔记键"},
                "value": {"type": "string", "description": "笔记内容"},
                "source": {"type": "string", "description": "来源（可选）"},
            },
            "required": ["key", "value"],
        },
        handler=memory_note_handler,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.memory.user",
        description=(
            "写一条用户级长期事实/偏好（分层记忆用户层）。key/value"
        ),
        parameters={
            "properties": {
                "key": {"type": "string", "description": "事实/偏好键"},
                "value": {"type": "string", "description": "内容"},
            },
            "required": ["key", "value"],
        },
        handler=memory_user_handler,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.memory.search-v2",
        description=(
            "分层记忆检索：OR 多关键词扫四层（用户/笔记/日志/反思），"
            "返回带 layer/source 标注的结果；query 为自然语言时 LLM 自动"
            "扩写关键词（失败降级原词）。query；top_k（可选，默认 5）"
        ),
        parameters={
            "properties": {
                "query": {"type": "string", "description": "检索词/自然语言查询"},
                "top_k": {"type": "integer", "description": "返回条数"},
            },
            "required": ["query"],
        },
        handler=memory_search_v2_handler,
        plugin_name="core",
    ))
    # 会话→文档闭环（v2.1：以官方 MCP 工具出现在 dsh，模型直接调用）
    registry.register(Tool(
        name="ddw.docs.save",
        description=(
            "把当前对话产出的文档保存到 deepDDW 知识库并关联会话。"
            "session_id/title/content；kind（可选，默认 chat）"
        ),
        parameters={
            "properties": {
                "session_id": {"type": "string", "description": "dsh 会话 id"},
                "title": {"type": "string", "description": "文档标题"},
                "content": {"type": "string", "description": "文档正文（markdown）"},
                "kind": {"type": "string", "description": "类型（默认 chat）"},
            },
            "required": ["session_id", "title", "content"],
        },
        handler=docs_save_handler,
        plugin_name="core",
    ))
    registry.register(Tool(
        name="ddw.session.docs",
        description="列出某会话产出/关联的文档。session_id；limit（可选，默认 50）",
        parameters={
            "properties": {
                "session_id": {"type": "string", "description": "dsh 会话 id"},
                "limit": {"type": "integer", "description": "返回条数"},
            },
            "required": ["session_id"],
        },
        handler=session_docs_handler,
        plugin_name="core",
    ))


async def memory_put_handler(
    args: Dict[str, Any], ctx: Dict[str, Any],
) -> Dict[str, Any]:
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


async def memory_search_handler(
    args: Dict[str, Any], ctx: Dict[str, Any],
) -> Dict[str, Any]:
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


async def memory_context_handler(
    args: Dict[str, Any], ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """ddw.memory.context handler（记忆注入块预览）。"""
    from core.knowledge import memory_context_build

    try:
        result = memory_context_build(budget=int(args.get("budget") or 2400))
        context = result.get("context", "")
        if not context:
            return {
                "content": [{"type": "text", "text": "当前无可用记忆（degraded={})"
                                        .format(result.get("degraded", False))}],
                "chars": 0,
            }
        return {
            "content": [{"type": "text", "text": context}],
            "chars": result.get("chars", 0),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp memory.context degraded: %s", exc)
        return {
            "content": [{"type": "text", "text": f"记忆上下文构建失败（已降级）：{exc}"}],
            "degraded": True,
        }


async def memory_consolidate_handler(
    args: Dict[str, Any], ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """ddw.memory.consolidate handler（自动沉淀：LLM 提炼 → 今日日志）。

    content 为对话文本时走 LLM 提炼（失败规则降级）；text 字段直接写日志。
    """
    from core.knowledge import memory_consolidate_llm, memory_log_append

    try:
        content = str(args.get("content", "")).strip()
        if not content:
            return {"content": [{"type": "text", "text": "沉淀内容为空"}], "ok": False}
        if args.get("llm"):
            result = await memory_consolidate_llm(content)
            mode = result.get("mode", "rule")
            if result.get("skipped") == "too_short":
                return {
                    "content": [{"type": "text", "text": "内容过短，跳过沉淀（寒暄轮）"}],
                    "ok": True, "skipped": "too_short",
                }
            wrote = result.get("wrote", 0)
            return {
                "content": [{"type": "text", "text": f"已沉淀（{mode} 提炼 {wrote} 条）"}],
                "ok": bool(result.get("ok", True)),
                "mode": mode,
                "wrote": wrote,
            }
        result = memory_log_append(content, auto=True)
        return {
            "content": [{"type": "text", "text": "已沉淀到今日日志（auto）"}],
            "ok": bool(result.get("ok", True)),
            "log_id": result.get("log_id"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp memory.consolidate degraded: %s", exc)
        return {
            "content": [{"type": "text", "text": f"沉淀失败（已降级）：{exc}"}],
            "ok": False,
            "degraded": True,
        }


async def memory_reflect_handler(
    args: Dict[str, Any], ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """ddw.memory.reflect handler（每日反思：generate=true 用 LLM 自动生成）。"""
    try:
        if args.get("generate"):
            from core.knowledge import memory_reflect_generate

            result = await memory_reflect_generate(
                style=str(args.get("style") or "auto")
            )
            if not result.get("due"):
                return {
                    "content": [{"type": "text", "text": (
                        "今日反思不满足触发条件（昨天无日志或已反思）")}],
                    "ok": True, "generated": False,
                }
            if result.get("generated"):
                return {
                    "content": [{"type": "text", "text": (
                        "LLM 反思已生成并保存（{}）".format(result.get("ref_date", "")))}],
                    "ok": True, "generated": True,
                }
            return {
                "content": [{"type": "text", "text": (
                    "反思待生成：LLM 不可用或日志为空（due={})"
                    .format(result.get("degraded", False)))}],
                "ok": True, "generated": False, "due": True,
            }
        from core.knowledge import memory_reflect_save

        content = str(args.get("content", "")).strip()
        if not content:
            return {"content": [{"type": "text", "text": "反思正文为空"}], "ok": False}
        result = memory_reflect_save(content, style=str(args.get("style") or "auto"))
        return {
            "content": [{"type": "text", "text": "反思已保存（{}）"
                        .format(result.get("ref_date", ""))}],
            "ok": bool(result.get("ok", True)),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp memory.reflect degraded: %s", exc)
        return {
            "content": [{"type": "text", "text": f"反思保存失败（已降级）：{exc}"}],
            "ok": False,
            "degraded": True,
        }


async def memory_maintain_handler(
    args: Dict[str, Any], ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """ddw.memory.maintain handler（超预算归档最旧笔记）。"""
    from core.knowledge import memory_maintain

    try:
        result = memory_maintain()
        archived = result.get("archived", [])
        return {
            "content": [{"type": "text", "text": (
                "维护完成：归档 {} 条，预算 {} 字（余 {}）".format(
                    len(archived), result.get("total", 0),
                    result.get("remaining", 0)))}],
            "ok": bool(result.get("ok", True)),
            "archived": len(archived),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp memory.maintain degraded: %s", exc)
        return {
            "content": [{"type": "text", "text": f"维护失败（已降级）：{exc}"}],
            "ok": False,
            "degraded": True,
        }


async def memory_note_handler(
    args: Dict[str, Any], ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """ddw.memory.note handler（项目笔记 upsert）。"""
    from core.knowledge import memory_note_put

    try:
        result = memory_note_put(
            key=str(args.get("key", "")),
            value=str(args.get("value", "")),
            source=str(args.get("source") or "deepddw"),
        )
        return {
            "content": [{"type": "text", "text": (
                "笔记已保存（{}）".format(result.get("note", "ok")))}],
            "ok": bool(result.get("ok", True)),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp memory.note degraded: %s", exc)
        return {
            "content": [{"type": "text", "text": f"笔记保存失败（已降级）：{exc}"}],
            "ok": False,
            "degraded": True,
        }


async def memory_user_handler(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """ddw.memory.user handler（用户级长期事实 upsert）。"""
    from core.knowledge import memory_user_put

    try:
        result = memory_user_put(
            key=str(args.get("key", "")),
            value=str(args.get("value", "")),
        )
        return {
            "content": [{"type": "text", "text": "用户记忆已保存"}],
            "ok": bool(result.get("ok", True)),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp memory.user degraded: %s", exc)
        return {
            "content": [{"type": "text", "text": f"用户记忆保存失败（已降级）：{exc}"}],
            "ok": False,
            "degraded": True,
        }


async def memory_search_v2_handler(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """ddw.memory.search-v2 handler（分层检索 + LLM 扩写增强，失败降级原词）。"""
    from core.knowledge import memory_search_v2_async

    try:
        result = await memory_search_v2_async(
            query=str(args.get("query", "")),
            top_k=int(args.get("top_k") or 5),
            expand=True,
        )
        items = result.get("results", [])
        if not items:
            text = "分层记忆未命中（degraded={})".format(result.get("degraded", False))
        else:
            text = "分层记忆检索结果：\n" + "\n".join(
                f"- [{it.get('layer', '?')}] {it.get('content', it.get('value', ''))}"
                for it in items[:5]
            )
        return {
            "content": [{"type": "text", "text": text}],
            "results": items,
            "layers": result.get("layers", []),
            "expanded": result.get("expanded", []),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp memory.search-v2 degraded: %s", exc)
        return {
            "content": [{"type": "text", "text": f"分层记忆检索失败（已降级）：{exc}"}],
            "results": [],
            "degraded": True,
        }


async def docs_save_handler(
    args: Dict[str, Any], ctx: Dict[str, Any]
) -> Dict[str, Any]:
    """ddw.docs.save 真实 handler（会话→文档入库+关联）。"""
    from core.knowledge import session_doc_add

    try:
        result = session_doc_add(
            session_id=str(args.get("session_id", "")),
            title=str(args.get("title", "")),
            content=str(args.get("content", "")),
            kind=str(args.get("kind") or "chat"),
        )
        if not result.get("ok"):
            return {
                "content": [{"type": "text", "text": "文档保存失败（已降级）"}],
                "ok": False,
                "degraded": True,
            }
        return {
            "content": [
                {"type": "text", "text": f"文档已保存（id={result['id']}，已关联会话）"}
            ],
            "ok": True,
            "id": result["id"],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp docs.save degraded: %s", exc)
        return {
            "content": [{"type": "text", "text": f"文档保存失败（已降级）：{exc}"}],
            "ok": False,
            "degraded": True,
        }


async def session_docs_handler(
    args: Dict[str, Any], ctx: Dict[str, Any]
) -> Dict[str, Any]:
    """ddw.session.docs 真实 handler（按会话列文档）。"""
    from core.knowledge import session_docs_list

    try:
        result = session_docs_list(
            session_id=str(args.get("session_id", "")),
            limit=int(args.get("limit") or 50),
        )
        items = result.get("results", [])
        if not items:
            text = "该会话暂无产出文档（degraded={})".format(
                result.get("degraded", False)
            )
        else:
            text = "会话文档列表：\n" + "\n".join(
                f"- [{it['id']}] {it['title']}" for it in items
            )
        return {"content": [{"type": "text", "text": text}], "results": items}
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp session.docs degraded: %s", exc)
        return {
            "content": [{"type": "text", "text": f"会话文档查询失败（已降级）：{exc}"}],
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
                    content.append({"type": "text", "text": json.dumps(
                        block, default=str, ensure_ascii=False)})
    elif "toolResult" in result:
        raw = result["toolResult"]
        content.append({
            "type": "text",
            "text": raw if isinstance(raw, str)
                    else json.dumps(raw, default=str, ensure_ascii=False),  # noqa: E501
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
            "text": json.dumps(result, default=str, ensure_ascii=False)
                    if not isinstance(result, str) else result,  # noqa: E501
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
