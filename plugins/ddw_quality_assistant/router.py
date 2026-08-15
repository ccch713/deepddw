"""FastAPI router for Quality Assistant plugin."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/plugins/ddw-quality-assistant", tags=["quality-assistant"])

_service = None


def set_service(service):
    global _service
    _service = service


# === Request Models ===

class EightDRequest(BaseModel):
    problem: str
    product: str = ""
    batch: str = ""
    severity: str = "major"
    language: str = "zh-CN"


class CAPARequest(BaseModel):
    nonconformity: str
    source: str = "internal_audit"
    severity: str = "major"
    language: str = "zh-CN"


class DeviationRequest(BaseModel):
    description: str
    product: str = ""
    batch: str = ""
    process_step: str = ""
    language: str = "zh-CN"


class ComplaintReplyRequest(BaseModel):
    complaint: str
    customer: str = ""
    product: str = ""
    tone: str = "professional"
    language: str = "zh-CN"


class FiveWhyRequest(BaseModel):
    problem: str
    context: str = ""
    language: str = "zh-CN"


class StatusUpdateRequest(BaseModel):
    status: str  # draft/reviewed/approved/archived


# === Endpoints ===

@router.post("/8d")
async def generate_8d(req: EightDRequest):
    """Generate an 8D problem-solving report."""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    doc = _service.generate_8d_report(
        problem=req.problem, product=req.product,
        batch=req.batch, severity=req.severity, language=req.language
    )
    return {"id": doc.id, "title": doc.title, "content": doc.content,
            "doc_type": doc.doc_type, "status": doc.status}


@router.post("/capa")
async def generate_capa(req: CAPARequest):
    """Generate a CAPA draft."""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    doc = _service.generate_capa_draft(
        nonconformity=req.nonconformity, source=req.source,
        severity=req.severity, language=req.language
    )
    return {"id": doc.id, "title": doc.title, "content": doc.content,
            "doc_type": doc.doc_type, "status": doc.status}


@router.post("/deviation")
async def generate_deviation(req: DeviationRequest):
    """Generate a deviation investigation report."""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    doc = _service.generate_deviation_report(
        deviation_desc=req.description, product=req.product,
        batch=req.batch, process_step=req.process_step, language=req.language
    )
    return {"id": doc.id, "title": doc.title, "content": doc.content,
            "doc_type": doc.doc_type, "status": doc.status}


@router.post("/complaint-reply")
async def generate_complaint_reply(req: ComplaintReplyRequest):
    """Generate a customer complaint reply."""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    doc = _service.generate_complaint_reply(
        complaint=req.complaint, customer=req.customer,
        product=req.product, tone=req.tone, language=req.language
    )
    return {"id": doc.id, "title": doc.title, "content": doc.content,
            "doc_type": doc.doc_type, "status": doc.status}


@router.post("/5why")
async def perform_5why(req: FiveWhyRequest):
    """Perform 5-Why root cause analysis."""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    analysis = _service.perform_5why_analysis(
        problem=req.problem, context=req.context, language=req.language
    )
    return {"id": analysis.id, "problem": analysis.problem_description,
            "why_chain": analysis.why_chain, "root_cause": analysis.root_cause,
            "corrective_action": analysis.corrective_action}


@router.get("/documents")
async def list_documents(doc_type: Optional[str] = None,
                         status: Optional[str] = None, limit: int = 50):
    """List quality documents."""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    docs = _service.list_documents(doc_type=doc_type, status=status, limit=limit)
    return [{"id": d.id, "doc_type": d.doc_type, "title": d.title,
             "status": d.status, "created_at": d.created_at.isoformat()} for d in docs]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int):
    """Get a specific quality document."""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    doc = _service.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"id": doc.id, "doc_type": doc.doc_type, "title": doc.title,
            "content": doc.content, "status": doc.status,
            "input_data": doc.input_data, "created_at": doc.created_at.isoformat()}


@router.patch("/documents/{doc_id}/status")
async def update_status(doc_id: int, req: StatusUpdateRequest):
    """Update document status."""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    doc = _service.update_document_status(doc_id, req.status)
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"id": doc.id, "status": doc.status}


@router.get("/5why")
async def list_5why(limit: int = 20):
    """List 5-Why analyses."""
    if not _service:
        raise HTTPException(503, "Service not initialized")
    analyses = _service.list_5why_analyses(limit=limit)
    return [{"id": a.id, "problem": a.problem_description,
             "root_cause": a.root_cause, "created_at": a.created_at.isoformat()} for a in analyses]


@router.get("/health")
async def health():
    return {"status": "ok", "plugin": "ddw-quality-assistant", "version": "1.0.0"}
