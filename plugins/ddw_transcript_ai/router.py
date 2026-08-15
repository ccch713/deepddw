from __future__ import annotations

"""DDW 转写与结构化插件 API 路由。

API 端点（5 个）：
  健康检查：GET  /health
  转写     ：POST /transcript/transcribe
  摘要     ：POST /transcript/summarize
  待办提取 ：POST /transcript/extract-todos
  实体抽取 ：POST /transcript/extract-entities
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from .schemas import (
    ExtractEntitiesReq,
    ExtractEntitiesResp,
    ExtractTodosReq,
    ExtractTodosResp,
    SummarizeReq,
    SummarizeResp,
    TranscribeReq,
    TranscribeResp,
)
from .services import TranscriptService

logger = logging.getLogger(__name__)

# 文本最大长度：与 manifest.yaml config_schema.max_input_length 保持一致
MAX_INPUT_LENGTH = 32_000


def build_router(service: TranscriptService) -> APIRouter:
    """构造转写与结构化路由。

    参数：
        service: 业务服务实例（持有 EmbeddedLLM）
    """
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-transcript-ai",
        tags=["ddw-transcript-ai"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "plugin": "ddw-transcript-ai",
            "version": "1.0.0",
            "status": "ok",
            "backend": service._backend_name(),
        }

    # -----------------------------------------------------------------------
    # 1) 转写
    # -----------------------------------------------------------------------
    @router.post("/transcript/transcribe", response_model=TranscribeResp)
    async def transcribe(data: TranscribeReq) -> TranscribeResp:
        """录音转写（模拟 ASR）。"""
        try:
            result = await service.transcribe(
                file_url=data.file_url,
                language=data.language,
            )
        except Exception:  # pragma: no cover
            logger.exception("transcribe failed")
            raise HTTPException(status_code=500, detail="transcribe failed")
        return TranscribeResp(**result)

    # -----------------------------------------------------------------------
    # 2) 摘要
    # -----------------------------------------------------------------------
    @router.post("/transcript/summarize", response_model=SummarizeResp)
    async def summarize(data: SummarizeReq) -> SummarizeResp:
        """文本摘要。"""
        _validate_text_length(data.text, "text")
        try:
            result = await service.summarize(
                text=data.text,
                max_length=data.max_length,
            )
        except Exception:  # pragma: no cover
            logger.exception("summarize failed")
            raise HTTPException(status_code=500, detail="summarize failed")
        return SummarizeResp(**result)

    # -----------------------------------------------------------------------
    # 3) 待办提取
    # -----------------------------------------------------------------------
    @router.post("/transcript/extract-todos", response_model=ExtractTodosResp)
    async def extract_todos(data: ExtractTodosReq) -> ExtractTodosResp:
        """提取待办事项。"""
        _validate_text_length(data.text, "text")
        try:
            result = await service.extract_todos(text=data.text)
        except Exception:  # pragma: no cover
            logger.exception("extract_todos failed")
            raise HTTPException(status_code=500, detail="extract_todos failed")
        return ExtractTodosResp(**result)

    # -----------------------------------------------------------------------
    # 4) 实体抽取
    # -----------------------------------------------------------------------
    @router.post("/transcript/extract-entities", response_model=ExtractEntitiesResp)
    async def extract_entities(data: ExtractEntitiesReq) -> ExtractEntitiesResp:
        """抽取关键实体（公司/人名/金额/日期）。"""
        _validate_text_length(data.text, "text")
        try:
            result = await service.extract_entities(text=data.text)
        except Exception:  # pragma: no cover
            logger.exception("extract_entities failed")
            raise HTTPException(status_code=500, detail="extract_entities failed")
        return ExtractEntitiesResp(**result)

    return router


def _validate_text_length(text: str, field: str) -> None:
    """统一校验文本长度，超出 400。"""
    if len(text) > MAX_INPUT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"{field} 长度 {len(text)} 超过最大限制 {MAX_INPUT_LENGTH}",
        )


__all__ = ["MAX_INPUT_LENGTH", "build_router"]
