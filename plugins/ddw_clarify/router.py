"""FastAPI router for Clarify plugin."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .models import (
    DetectRequest,
    DetectResponse,
    ClarifyRule,
    RespondRequest,
    RespondResponse,
)

router = APIRouter(prefix="/api/v1/plugins/ddw-clarify", tags=["clarify"])

_service = None


def set_service(service):
    global _service
    _service = service


@router.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest):
    """检测用户问题是否模糊、是否需要澄清。"""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    result = _service.detect(
        question=req.question,
        context=req.context,
        session_id=req.session_id,
    )
    return DetectResponse(
        needs_clarification=result["needs_clarification"],
        session_id=result["session_id"],
        matched_rule=result["matched_rule"],
        question=result["question"],
        clarification_round=result["clarification_round"],
    )


@router.post("/respond", response_model=RespondResponse)
async def respond(req: RespondRequest):
    """用户回答反问后提交答案。"""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    result = _service.respond(session_id=req.session_id, answer=req.answer)
    if result["status"] == "error":
        raise HTTPException(404, f"Session {req.session_id} not found")
    return RespondResponse(**result)


@router.get("/rules", response_model=list[ClarifyRule])
async def list_rules():
    """列出所有澄清规则。"""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    return _service.list_rules()


@router.get("/health")
async def health():
    return {"status": "ok", "plugin": "ddw-clarify", "version": "1.0.0"}
