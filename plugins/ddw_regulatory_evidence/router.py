"""FastAPI router for Regulatory Evidence plugin."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/plugins/ddw-regulatory-evidence", tags=["regulatory-evidence"])
_service = None


def set_service(service):
    global _service
    _service = service


class DocumentCreateRequest(BaseModel):
    title: str
    content: str
    jurisdiction: str
    authority: str
    doc_type: str
    category: str = "general"
    reference_number: str = ""
    effective_date: str = ""
    tags: Optional[List[str]] = None
    source_url: str = ""


class SearchRequest(BaseModel):
    query: str
    jurisdiction: Optional[str] = None
    limit: int = 10


class EvidenceChainCreateRequest(BaseModel):
    requirement: str
    regulation_id: Optional[int] = None
    product_name: str = ""
    compliance_status: str = "pending"
    evidence_description: str = ""
    evidence_documents: Optional[List[str]] = None
    gaps: str = ""
    action_plan: str = ""
    responsible: str = ""
    due_date: str = ""


class EvidenceChainUpdateRequest(BaseModel):
    compliance_status: Optional[str] = None
    evidence_description: Optional[str] = None
    gaps: Optional[str] = None
    action_plan: Optional[str] = None
    responsible: Optional[str] = None


@router.post("/documents")
async def create_document(req: DocumentCreateRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    doc = _service.add_document(**req.dict())
    return {"id": doc.id, "title": doc.title}


@router.get("/documents")
async def list_documents(jurisdiction: Optional[str] = None,
                         authority: Optional[str] = None,
                         doc_type: Optional[str] = None,
                         category: Optional[str] = None,
                         limit: int = 50):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    docs = _service.list_documents(jurisdiction=jurisdiction, authority=authority,
                                   doc_type=doc_type, category=category, limit=limit)
    return [{"id": d.id, "title": d.title, "jurisdiction": d.jurisdiction,
             "authority": d.authority, "doc_type": d.doc_type,
             "reference_number": d.reference_number} for d in docs]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    doc = _service.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"id": doc.id, "title": doc.title, "content": doc.content,
            "jurisdiction": doc.jurisdiction, "authority": doc.authority,
            "doc_type": doc.doc_type, "category": doc.category,
            "reference_number": doc.reference_number}


@router.post("/search")
async def search(req: SearchRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    docs = _service.search_documents(req.query, jurisdiction=req.jurisdiction, limit=req.limit)
    return [{"id": d.id, "title": d.title, "jurisdiction": d.jurisdiction,
             "authority": d.authority, "snippet": d.content[:200]} for d in docs]


@router.post("/evidence-chains")
async def create_evidence_chain(req: EvidenceChainCreateRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    chain = _service.create_evidence_chain(**req.dict())
    return {"id": chain.id, "requirement": chain.requirement[:80],
            "compliance_status": chain.compliance_status}


@router.get("/evidence-chains")
async def list_evidence_chains(product_name: Optional[str] = None,
                                compliance_status: Optional[str] = None,
                                limit: int = 50):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    chains = _service.list_evidence_chains(product_name=product_name,
                                            compliance_status=compliance_status,
                                            limit=limit)
    return [{"id": c.id, "requirement": c.requirement[:80],
             "product_name": c.product_name, "compliance_status": c.compliance_status,
             "gaps": c.gaps[:100] if c.gaps else ""} for c in chains]


@router.get("/evidence-chains/{chain_id}")
async def get_evidence_chain(chain_id: int):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    chain = _service.get_evidence_chain(chain_id)
    if not chain:
        raise HTTPException(404, "Evidence chain not found")
    return {"id": chain.id, "requirement": chain.requirement,
            "product_name": chain.product_name,
            "compliance_status": chain.compliance_status,
            "evidence_description": chain.evidence_description,
            "gaps": chain.gaps, "action_plan": chain.action_plan,
            "responsible": chain.responsible}


@router.patch("/evidence-chains/{chain_id}")
async def update_evidence_chain(chain_id: int, req: EvidenceChainUpdateRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    updates = {k: v for k, v in req.dict().items() if v is not None}
    chain = _service.update_evidence_chain(chain_id, **updates)
    if not chain:
        raise HTTPException(404, "Evidence chain not found")
    return {"id": chain.id, "compliance_status": chain.compliance_status}


@router.post("/seed")
async def seed_regulations():
    if not _service:
        raise HTTPException(503, "Service not initialized")
    count = _service.seed_food_regulations()
    return {"seeded": count}


@router.post("/seed/cabio")
async def seed_cabio():
    if not _service:
        raise HTTPException(503, "Service not initialized")
    count = _service.seed_cabio_evidence_template()
    return {"seeded": count}


@router.get("/health")
async def health():
    return {"status": "ok", "plugin": "ddw-regulatory-evidence", "version": "1.0.0"}
