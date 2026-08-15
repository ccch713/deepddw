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
from typing import Any, AsyncIterator, List

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


class StreamRequest(ChatRequest):
    pass


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
    ctx = RouteContext(user_id=user_id, tenant_id=tenant_id, rule=payload.rule)
    response = await llm_chat(messages, rule=payload.rule, ctx=ctx)
    conv_id = payload.conversation_id or uuid.uuid4().hex
    now = datetime.utcnow()
    try:
        async with session_scope() as session:
            # 表 id 非自增（四库合并遗留），显式取 max+1
            max_id = (
                await session.execute(
                    select(_chat_table.c.id).order_by(_chat_table.c.id.desc()).limit(1)
                )
            ).scalar() or 0
            for role, content in (
                ("user", payload.message), ("assistant", response.content)
            ):
                await session.execute(_chat_table.insert().values(
                    id=max_id + 1, user_id=user_id, tenant_id=tenant_id,
                    conversation_id=conv_id,
                    role=role, content=content,
                    provider=response.provider, model=response.model,
                    tokens_in=response.tokens_in, tokens_out=response.tokens_out,
                    cost=response.cost,
                    created_at=now, updated_at=now,
                ))
                max_id += 1
            await session.commit()
    except Exception as exc:  # noqa: BLE001  # 历史落库失败不阻塞回复
        logger.warning("chat history persist degraded: %s", exc)
    return ok({
        "content": response.content, "model": response.model,
        "provider": response.provider,
        "tokens_in": response.tokens_in, "tokens_out": response.tokens_out,
        "cost": response.cost,
               "conversation_id": conv_id})


@router.post("/stream")
async def post_stream(
    payload: StreamRequest, claims: dict = Depends(require_access_token),
) -> StreamingResponse:
    messages: List[LLMChatMessage] = []
    if payload.system:
        messages.append(LLMChatMessage(role="system", content=payload.system))
    messages.append(LLMChatMessage(role="user", content=payload.message))
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
