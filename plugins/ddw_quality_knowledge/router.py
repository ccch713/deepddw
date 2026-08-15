"""FastAPI router for Quality Knowledge plugin."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/plugins/ddw-quality-knowledge", tags=["quality-knowledge"])
_service = None


def set_service(service):
    global _service
    _service = service


class DocumentCreateRequest(BaseModel):
    title: str
    content: str
    doc_type: str  # standard/sop/case/regulation/guide
    category: str = "general"
    tags: Optional[List[str]] = None
    source: str = ""


class DocumentUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    doc_type: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None


class SearchRequest(BaseModel):
    query: str
    doc_type: Optional[str] = None
    category: Optional[str] = None
    limit: int = 10


class SemanticSearchRequest(BaseModel):
    query: str
    limit: int = 10


# === CRUD Endpoints ===

@router.post("/documents")
async def create_document(
    request: Request, response: Response, req: DocumentCreateRequest
):
    # P3 数据同步授权校验 + P4 捎带响应头：旧码超 7 天倒计时 → 拒绝同步
    from core.utils.license_broker import state_response_headers
    from core.utils.license_state import check_sync_allowed

    sync_allowed, sync_reason = check_sync_allowed(
        request.headers.get("X-DDW-License-Key")
    )
    _state_headers = state_response_headers()
    if not sync_allowed:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=403,
            content={"detail": sync_reason},
            headers=_state_headers,
        )
    response.headers.update(_state_headers)
    if not _service:
        raise HTTPException(503, "Service not initialized")
    doc = _service.add_document(
        title=req.title, content=req.content, doc_type=req.doc_type,
        category=req.category, tags=req.tags, source=req.source
    )
    return {"id": doc.id, "title": doc.title, "doc_type": doc.doc_type}


@router.get("/documents")
async def list_documents(doc_type: Optional[str] = None, category: Optional[str] = None,
                         limit: int = 50, offset: int = 0):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    docs = _service.list_documents(doc_type=doc_type, category=category, limit=limit, offset=offset)
    return [{"id": d.id, "title": d.title, "doc_type": d.doc_type,
             "category": d.category, "tags": d.tags, "updated_at": d.updated_at.isoformat()} for d in docs]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    doc = _service.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"id": doc.id, "title": doc.title, "content": doc.content,
            "doc_type": doc.doc_type, "category": doc.category,
            "tags": doc.tags, "source": doc.source}


@router.put("/documents/{doc_id}")
async def update_document(doc_id: int, req: DocumentUpdateRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    updates = {k: v for k, v in req.dict().items() if v is not None}
    doc = _service.update_document(doc_id, **updates)
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"id": doc.id, "title": doc.title}


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    if not _service.delete_document(doc_id):
        raise HTTPException(404, "Document not found")
    return {"deleted": True}


# === Search Endpoints ===

@router.post("/search")
async def search(req: SearchRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    results = _service.search(query=req.query, doc_type=req.doc_type,
                              category=req.category, limit=req.limit)
    return [{"id": d.id, "title": d.title, "doc_type": d.doc_type,
             "category": d.category, "snippet": d.content[:200]} for d in results]


@router.post("/search/semantic")
async def semantic_search(req: SemanticSearchRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    return _service.semantic_search(query=req.query, limit=req.limit)


# === Seed Endpoint ===

@router.post("/seed")
async def seed_standards():
    if not _service:
        raise HTTPException(503, "Service not initialized")
    count = _service.seed_food_safety_standards()
    return {"seeded": count}


# === Analytics ===

@router.get("/stats")
async def get_stats(days: int = 30):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    return _service.get_search_stats(days=days)


@router.get("/health")
async def health():
    return {"status": "ok", "plugin": "ddw-quality-knowledge", "version": "1.0.0"}
