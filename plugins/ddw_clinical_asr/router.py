"""DDW Clinical ASR - FastAPI router.

端点：
    POST /extract         抽取结构化实体
    POST /classify        纯分类
    GET  /prompts         列出所有可用 prompt
    GET  /health          健康检查
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import PLUGIN_NAME, VERSION, config
from .extractor import classify_treatment, extract_medical_entities, list_prompts
from .schema import (
    ClassifyRequest,
    ClassifyResponse,
    ClassifyResult,
    ExtractionResult,
    ExtractRequest,
    ExtractResponse,
    HealthResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plugins/ddw_clinical_asr", tags=["ddw_clinical_asr"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(default_model=config.DEFAULT_MODEL)


@router.get("/prompts")
async def get_prompts() -> dict[str, Any]:
    return {
        "plugin": PLUGIN_NAME,
        "version": VERSION,
        "prompts": list_prompts(),
    }


@router.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest) -> ExtractResponse:
    if len(req.transcript_text) > config.MAX_TRANSCRIPT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"transcript_text 过长（>{config.MAX_TRANSCRIPT_CHARS} 字符）",
        )
    if not req.transcript_text.strip():
        raise HTTPException(status_code=422, detail="transcript_text 不能为空")
    try:
        result, latency = await extract_medical_entities(
            req.transcript_text,
            job_id=req.job_id,
            treatment_hint=req.treatment_hint,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("extract failed")
        raise HTTPException(status_code=500, detail=f"extract failed: {e}") from e
    return ExtractResponse(
        result=ExtractionResult(**result),
        latency_ms=latency,
    )


@router.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest) -> ClassifyResponse:
    if not req.transcript_text.strip():
        raise HTTPException(status_code=422, detail="transcript_text 不能为空")
    try:
        out = await classify_treatment(req.transcript_text, job_id=req.job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("classify failed")
        raise HTTPException(status_code=500, detail=f"classify failed: {e}") from e
    return ClassifyResponse(result=ClassifyResult(**out))


class PromptsReloadRequest(BaseModel):
    pass


@router.post("/prompts/reload")
async def reload_prompts() -> dict[str, Any]:
    """重新加载 prompts/ 目录（运营操作）."""
    return {"status": "ok", "prompts": list_prompts()}
