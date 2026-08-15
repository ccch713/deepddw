"""docs_search LLM 工具（决策 3：LLM 检索文档栏目统一入口）。

- 以 OpenAI function calling 格式定义（供 ddw-llm-gateway / MCP ToolRegistry 注册）
- 所有 LLM（内置本地 + 租户自配）调 docs_search 一律经平台 LLM 网关链路：
  鉴权 → 租户过滤 → 审计事件（docs.portal.searched）→ 计量（网关 usage 层）
- 插件层不直连外部 LLM、不存租户 key（红线）
- 只返回 published + 当前租户可见文档；draft/archived 对工具不可见
"""
from __future__ import annotations

import logging
from typing import Any

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .services import DocsPortalService

logger = logging.getLogger(__name__)

TOOL_NAME = "ddw.docs_portal.search"

_MAX_RESULT_CHARS = 50000


def docs_search_tool_definition() -> dict[str, Any]:
    """docs_search 工具定义（OpenAI function calling 格式，测试 11 断言此格式）。"""
    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": (
                "检索 DDW 产品文档栏目（白皮书/产品手册/解决方案/规章制度等正式文档），"
                "返回相关段落与来源链接。仅返回当前用户可见的已发布文档，可作权威引用依据。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索问题或关键词",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回相关段落条数（1-20，默认 5）",
                    },
                },
                "required": ["query"],
            },
        },
    }


async def _docs_search_handler(
    args: dict[str, Any], ctx: dict[str, Any]
) -> dict[str, Any]:
    """工具执行：租户过滤检索 + 审计事件。ctx 由调用方注入 tenant_id/user_id。"""
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": {"message": "缺少 query 参数"}}
    try:
        top_k = min(max(int(args.get("top_k") or 5), 1), 20)
    except (TypeError, ValueError):
        top_k = 5

    tenant_id = int((ctx or {}).get("tenant_id") or 0)
    user_id = int((ctx or {}).get("user_id") or 0)
    user = {"tenant_id": tenant_id, "user_id": user_id, "role": "member"}

    async with session_scope() as db, bypass_tenant_filter():
        svc = DocsPortalService(db)
        result = await svc.search_docs(query, top_k, user)

    sources = result.get("sources", [])
    lines = []
    if not sources:
        lines.append("未在文档栏目中找到相关内容。")
    else:
        lines.append(f"文档栏目命中 {len(sources)} 条相关内容：")
        for i, s in enumerate(sources, 1):
            lines.append(
                f"[{i}] {s.get('doc_title', '')}（{s.get('version', '')}）\n"
                f"来源: {s.get('docs_url', '')}\n{s.get('content', '')[:800]}"
            )
    text = "\n\n".join(lines)[:_MAX_RESULT_CHARS]

    return {
        "content": [{"type": "text", "text": text}],
        "results": [
            {
                "doc_title": s.get("doc_title", ""),
                "slug": s.get("slug", ""),
                "version": s.get("version", ""),
                "content": s.get("content", ""),
                "score": s.get("score", 0.0),
                "docs_url": s.get("docs_url", ""),
            }
            for s in sources
        ],
    }


def register_docs_tool(registry) -> None:
    """注册到 MCP ToolRegistry（覆盖同名 stub）。"""
    try:
        from core.mcp.tools import Tool

        registry.register(
            Tool(
                name=TOOL_NAME,
                description="检索 DDW 产品文档栏目（白皮书/手册/方案等正式文档），返回相关段落与来源链接（仅已发布、当前用户可见文档）",
                parameters={
                    "properties": {
                        "query": {"type": "string", "description": "检索问题或关键词"},
                        "top_k": {"type": "integer", "description": "返回条数（1-20）"},
                    },
                    "required": ["query"],
                },
                handler=_docs_search_handler,
                is_read_only=True,
                plugin_name="ddw-docs-portal",
            ),
            override=True,
        )
        logger.info("docs_portal: registered LLM tool %s", TOOL_NAME)
    except Exception as exc:  # noqa: BLE001
        logger.warning("docs_portal: LLM tool register failed: %s", exc)


__all__ = ["TOOL_NAME", "docs_search_tool_definition", "register_docs_tool"]
