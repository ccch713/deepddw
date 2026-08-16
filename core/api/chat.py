"""deepDDW Chat API（开源裁剪版）。

提供（全部走网关 Token 门禁）：
- ``POST /api/v1/chat/``          — 非流式对话（LLM 网关；断网/无 Key 降级不阻塞）
- ``POST /api/v1/chat/stream``    — SSE 流式对话
- ``GET  /api/v1/chat/history``   — 会话历史

单用户模型：无账号体系，会话归属 user_id=0 / tenant_id=0。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import (
    BigInteger, Column, DateTime, Float, Integer,
    MetaData, String, Table, Text, select,
)

from core.api_response import ok
from core.database.session import session_scope
from core.llm_gateway.base import ChatMessage as LLMChatMessage
from core.llm_gateway.gateway import chat as llm_chat
from core.llm_gateway.gateway import stream_chat as llm_stream
from core.llm_gateway.router import RouteContext
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

# chat_messages 表（单用户：user_id/tenant_id 恒为 0）
_chat_table = Table(
    "chat_messages",
    MetaData(),
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("user_id", BigInteger),
    Column("tenant_id", BigInteger),
    Column("conversation_id", String(64)),
    Column("role", String(16)),
    Column("content", Text),
    Column("provider", String(64)),
    Column("model", String(128)),
    Column("tokens_in", Integer),
    Column("tokens_out", Integer),
    Column("cost", Float),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32_000)
    conversation_id: str | None = None
    rule: str | None = None
    system: str | None = None
    rag: bool = True  # 自动 RAG：先检索知识库拼入上下文（无命中/故障自动降级）


class StreamRequest(ChatRequest):
    pass


_RAG_MAX_HITS = 3  # 拼入上下文的 KB 命中上限（防上下文爆炸）
_RAG_MAX_CHARS = 600  # 每条命中截断长度


def _build_rag_context(message: str) -> Dict[str, Any]:
    """自动 RAG：检索知识库并把命中拼成 system 上下文。

    失败/无命中返回空上下文（对话主流程不阻塞）。
    """
    try:
        from core.knowledge import kb_search

        result = kb_search(message, top_k=_RAG_MAX_HITS)
        hits = result.get("results", [])
        if not hits:
            return {"context": "", "hits": [], "degraded": bool(result.get("degraded"))}
        lines = ["以下为知识库检索结果，可据此回答（若无直接关系请忽略）："]
        for i, it in enumerate(hits, 1):
            excerpt = (it.get("excerpt") or "")[:_RAG_MAX_CHARS]
            lines.append(f"[{i}] {it.get('title', '')}: {excerpt}")
        return {"context": "\n".join(lines), "hits": hits, "degraded": False}
    except Exception as exc:  # noqa: BLE001  # RAG 故障降级为普通对话
        logger.warning("chat rag degraded: %s", exc)
        return {"context": "", "hits": [], "degraded": True}


def _apply_rag(
    messages: List[LLMChatMessage],
    payload: ChatRequest,
) -> Dict[str, Any]:
    """把 RAG 上下文注入 messages（payload.rag 开启时）；返回命中信息。"""
    if not payload.rag:
        return {"context": "", "hits": [], "degraded": False}
    rag = _build_rag_context(payload.message)
    if rag["context"]:
        base_system = payload.system or ""
        combined = (
            f"{base_system}\n\n{rag['context']}"
            if base_system else rag["context"]
        )
        # 替换/插入 system 消息（保持 system 在最前）
        if messages and messages[0].role == "system":
            messages[0] = LLMChatMessage(role="system", content=combined)
        else:
            messages.insert(0, LLMChatMessage(role="system", content=combined))
    return rag


@router.post("/")
async def post_chat(
    payload: ChatRequest, claims: dict = Depends(require_access_token),
) -> Any:
    user_id = 0
    tenant_id = 0
    messages: List[LLMChatMessage] = []
    if payload.system:
        messages.append(LLMChatMessage(role="system", content=payload.system))
    messages.append(LLMChatMessage(role="user", content=payload.message))
    rag = _apply_rag(messages, payload)  # 自动 RAG（可开关；失败降级）
    ctx = RouteContext(user_id=user_id, tenant_id=tenant_id, rule=payload.rule)
    response = await llm_chat(messages, rule=payload.rule, ctx=ctx)
    conv_id = payload.conversation_id or uuid.uuid4().hex
    now = datetime.utcnow()
    try:
        # P0-6：id 留空由 DB 自增（chat_messages 建表已声明 AUTOINCREMENT），
        # 去掉手算 max(id)+1——消除并发主键冲突；两条消息同一事务成对写入。
        async with session_scope() as session:
            for role, content in (
                ("user", payload.message), ("assistant", response.content)
            ):
                await session.execute(_chat_table.insert().values(
                    user_id=user_id, tenant_id=tenant_id,
                    conversation_id=conv_id,
                    role=role, content=content,
                    provider=response.provider, model=response.model,
                    tokens_in=response.tokens_in, tokens_out=response.tokens_out,
                    cost=response.cost,
                    created_at=now, updated_at=now,
                ))
            await session.commit()
    except Exception as exc:  # noqa: BLE001  # 历史落库失败不阻塞回复
        logger.warning("chat history persist degraded: %s", exc)
    return ok({
        "content": response.content, "model": response.model,
        "provider": response.provider,
        "tokens_in": response.tokens_in, "tokens_out": response.tokens_out,
        "cost": response.cost,
        "conversation_id": conv_id,
        "rag": {
            "enabled": payload.rag,
            "hits": len(rag.get("hits", [])),
            "degraded": bool(rag.get("degraded")),
        },
    })


@router.post("/stream")
async def post_stream(
    payload: StreamRequest, claims: dict = Depends(require_access_token),
) -> StreamingResponse:
    messages: List[LLMChatMessage] = []
    if payload.system:
        messages.append(LLMChatMessage(role="system", content=payload.system))
    messages.append(LLMChatMessage(role="user", content=payload.message))
    _apply_rag(messages, payload)  # 自动 RAG（流式同样生效；失败降级）
    ctx = RouteContext(user_id=0, tenant_id=0, rule=payload.rule)

    async def gen() -> AsyncIterator[bytes]:
        try:
            async for chunk in llm_stream(messages, rule=payload.rule, ctx=ctx):
                yield f"data: {chunk}\n\n".encode("utf-8")
        except Exception as exc:  # noqa: BLE001  # 流式故障降级为完整回复
            logger.warning("chat stream degraded: %s", exc)
            yield f"data: {exc}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/history")
async def history(
    conversation_id: str, claims: dict = Depends(require_access_token),
) -> Any:
    user_id = 0
    try:
        async with session_scope() as session:
            stmt = (
                select(_chat_table)
                .where(
                    _chat_table.c.user_id == user_id,
                    _chat_table.c.conversation_id == conversation_id,
                )
                .order_by(_chat_table.c.id)
            )
            rows = (await session.execute(stmt)).all()
        return ok([
            {
                "role": r.role,
                "content": r.content,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ])
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat history degraded: %s", exc)
        return ok([])
