"""API routes for ESG Knowledge Base plugin."""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response

try:
    from .importer import import_markdown, import_text
    from .models import (
        BatchImportRequest,
        BatchImportResponse,
        ChunkResponse,
        CustomerCreate,
        CustomerResponse,
        CustomerUpdate,
        DocumentCreate,
        DocumentResponse,
        DocumentUpdate,
        HybridSearchRequest,
        KeywordSearchRequest,
        RAGContextItem,
        RAGContextResponse,
        RAGRetrieveRequest,
        SearchResult,
        SemanticSearchRequest,
        StatsResponse,
    )
    from .rag import build_rag_context, retrieve_context
    from .search import (
        compute_tsvector,
        hybrid_search,
        keyword_search,
        semantic_search,
    )
except ImportError:
    from importer import import_markdown, import_text  # type: ignore[no-redef]
    from models import (  # type: ignore[no-redef]
        BatchImportRequest,
        BatchImportResponse,
        ChunkResponse,
        CustomerCreate,
        CustomerResponse,
        CustomerUpdate,
        DocumentCreate,
        DocumentResponse,
        DocumentUpdate,
        HybridSearchRequest,
        KeywordSearchRequest,
        RAGContextItem,
        RAGContextResponse,
        RAGRetrieveRequest,
        SearchResult,
        SemanticSearchRequest,
        StatsResponse,
    )
    from rag import build_rag_context, retrieve_context  # type: ignore[no-redef]
    from search import (  # type: ignore[no-redef]
        compute_tsvector,
        hybrid_search,
        keyword_search,
        semantic_search,
    )

router = APIRouter(prefix="/api/v1/plugins/ddw-esg-knowledge", tags=["ddw-esg-knowledge"])

# ---------------------------------------------------------------------------
# In-memory DB for development / testing (swappable with real session)
# ---------------------------------------------------------------------------

_db: dict[str, list[dict[str, Any]]] = {
    "customers": [],
    "documents": [],
    "chunks": [],
}


def _get_db() -> dict[str, list[dict[str, Any]]]:
    """Return the in-memory store. Override for real DB."""
    return _db


def _reset_db() -> None:
    """Reset in-memory store (for tests)."""
    _db["customers"] = []
    _db["documents"] = []
    _db["chunks"] = []


# ---------------------------------------------------------------------------
# Health & Stats
# ---------------------------------------------------------------------------


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "plugin": "ddw-esg-knowledge"}


@router.get("/stats", response_model=StatsResponse)
def get_stats() -> StatsResponse:
    db = _get_db()
    docs = db["documents"]
    chunks = db["chunks"]
    customers = db["customers"]

    by_framework: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for d in docs:
        fw = d.get("framework") or "unspecified"
        st = d.get("status") or "unknown"
        by_framework[fw] = by_framework.get(fw, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1

    return StatsResponse(
        total_documents=len(docs),
        total_chunks=len(chunks),
        total_customers=len(customers),
        documents_by_framework=by_framework,
        documents_by_status=by_status,
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@router.post("/documents", response_model=DocumentResponse, status_code=201)
def create_document(req: DocumentCreate) -> DocumentResponse:
    db = _get_db()
    doc_id = str(uuid.uuid4())
    doc: dict[str, Any] = {
        "id": doc_id,
        "title": req.title,
        "framework": req.framework,
        "doc_type": req.doc_type,
        "visibility": req.visibility,
        "customer_id": req.customer_id,
        "tags": req.tags or [],
        "metadata": req.metadata_ or {},
        "summary": None,
        "chunk_count": 0,
        "status": "processing",
        "created_at": None,
        "updated_at": None,
    }

    # Import content if provided
    if req.content:
        imported = import_text(req.content, title=req.title)
        chunks_data = imported["chunks"]
        for i, c in enumerate(chunks_data):
            chunk_id = str(uuid.uuid4())
            chunk_doc: dict[str, Any] = {
                "id": chunk_id,
                "doc_id": doc_id,
                "customer_id": req.customer_id,
                "text": c["text"],
                "section": None,
                "page": None,
                "chunk_index": i,
                "token_count": c.get("token_count", 0),
                "embedding": None,
                "tsvector": c.get("tsvector", ""),
                "metadata": {},
                "created_at": None,
            }
            db["chunks"].append(chunk_doc)
        doc["chunk_count"] = len(chunks_data)
        doc["status"] = "ready"
        doc["summary"] = imported["text"][:200] if imported["text"] else None

    db["documents"].append(doc)
    return DocumentResponse.model_validate(doc)


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    framework: Optional[str] = None,
    doc_type: Optional[str] = None,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[DocumentResponse]:
    db = _get_db()
    results = db["documents"]
    if framework:
        results = [d for d in results if d.get("framework") == framework]
    if doc_type:
        results = [d for d in results if d.get("doc_type") == doc_type]
    if customer_id:
        results = [d for d in results if d.get("customer_id") == customer_id]
    if status:
        results = [d for d in results if d.get("status") == status]
    start = (page - 1) * page_size
    return [DocumentResponse.model_validate(d) for d in results[start : start + page_size]]


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
def get_document(doc_id: str) -> DocumentResponse:
    db = _get_db()
    for d in db["documents"]:
        if d["id"] == doc_id:
            return DocumentResponse.model_validate(d)
    raise HTTPException(status_code=404, detail="Document not found")


@router.put("/documents/{doc_id}", response_model=DocumentResponse)
def update_document(doc_id: str, req: DocumentUpdate) -> DocumentResponse:
    db = _get_db()
    for d in db["documents"]:
        if d["id"] == doc_id:
            update_data = req.model_dump(exclude_unset=True)
            # Map Pydantic alias
            if "metadata_" in update_data:
                update_data["metadata"] = update_data.pop("metadata_")
            d.update(update_data)
            return DocumentResponse.model_validate(d)
    raise HTTPException(status_code=404, detail="Document not found")


@router.delete("/documents/{doc_id}", status_code=204, response_model=None, response_class=Response)
def delete_document(doc_id: str) -> None:
    db = _get_db()
    for i, d in enumerate(db["documents"]):
        if d["id"] == doc_id:
            db["documents"].pop(i)
            # Delete associated chunks
            db["chunks"] = [c for c in db["chunks"] if c.get("doc_id") != doc_id]
            return
    raise HTTPException(status_code=404, detail="Document not found")


@router.post("/documents/{doc_id}/reindex", response_model=DocumentResponse)
def reindex_document(doc_id: str) -> DocumentResponse:
    """Reindex a document's chunks (recompute tsvector)."""
    db = _get_db()
    for d in db["documents"]:
        if d["id"] == doc_id:
            for c in db["chunks"]:
                if c.get("doc_id") == doc_id:
                    c["tsvector"] = compute_tsvector(c["text"])
            d["status"] = "ready"
            return DocumentResponse.model_validate(d)
    raise HTTPException(status_code=404, detail="Document not found")


@router.get("/documents/{doc_id}/chunks", response_model=list[ChunkResponse])
def list_document_chunks(doc_id: str) -> list[ChunkResponse]:
    db = _get_db()
    # Verify doc exists
    if not any(d["id"] == doc_id for d in db["documents"]):
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = [c for c in db["chunks"] if c.get("doc_id") == doc_id]
    return [ChunkResponse.model_validate(c) for c in chunks]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _get_search_chunks(
    db: dict[str, list[dict[str, Any]]],
    customer_id: Optional[str] = None,
    framework: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Get chunks enriched with doc title for search."""
    doc_map: dict[str, dict[str, Any]] = {d["id"]: d for d in db["documents"]}
    chunks = db["chunks"]
    result: list[dict[str, Any]] = []
    for c in chunks:
        doc = doc_map.get(c.get("doc_id", ""), {})
        # Apply filters
        if customer_id and c.get("customer_id") != customer_id:
            continue
        if framework and doc.get("framework") != framework:
            continue
        enriched = {**c, "doc_title": doc.get("title", "Unknown")}
        result.append(enriched)
    return result


@router.post("/search/keyword", response_model=list[SearchResult])
def search_keyword(req: KeywordSearchRequest) -> list[SearchResult]:
    db = _get_db()
    chunks = _get_search_chunks(db, customer_id=req.customer_id, framework=req.framework)
    results = keyword_search(req.query, chunks, top_k=req.top_k)
    return [
        SearchResult(
            chunk_id=r["id"],
            doc_id=r["doc_id"],
            doc_title=r.get("doc_title", "Unknown"),
            text=r["text"],
            score=r["score"],
            match_type="keyword",
            customer_id=r.get("customer_id"),
        )
        for r in results
    ]


@router.post("/search/semantic", response_model=list[SearchResult])
def search_semantic(req: SemanticSearchRequest) -> list[SearchResult]:
    db = _get_db()
    chunks = _get_search_chunks(db, customer_id=req.customer_id, framework=req.framework)
    embedding = req.query_embedding or [0.0] * 10
    results = semantic_search(embedding, chunks, top_k=req.top_k)
    return [
        SearchResult(
            chunk_id=r["id"],
            doc_id=r["doc_id"],
            doc_title=r.get("doc_title", "Unknown"),
            text=r["text"],
            score=r["score"],
            match_type="semantic",
            customer_id=r.get("customer_id"),
        )
        for r in results
    ]


@router.post("/search/hybrid", response_model=list[SearchResult])
def search_hybrid(req: HybridSearchRequest) -> list[SearchResult]:
    db = _get_db()
    chunks = _get_search_chunks(db, customer_id=req.customer_id, framework=req.framework)
    results = hybrid_search(
        req.query,
        req.query_embedding,
        chunks,
        keyword_weight=req.keyword_weight,
        semantic_weight=req.semantic_weight,
        top_k=req.top_k,
    )
    return [
        SearchResult(
            chunk_id=r["id"],
            doc_id=r["doc_id"],
            doc_title=r.get("doc_title", "Unknown"),
            text=r["text"],
            score=r["score"],
            match_type="hybrid",
            customer_id=r.get("customer_id"),
        )
        for r in results
    ]


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


@router.post("/customers", response_model=CustomerResponse, status_code=201)
def create_customer(req: CustomerCreate) -> CustomerResponse:
    db = _get_db()
    customer: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": req.name,
        "short_name": req.short_name,
        "stock_code": req.stock_code,
        "industry": req.industry,
        "sub_industry": req.sub_industry,
        "scale": req.scale,
        "contact": req.contact or {},
        "tags": req.tags or [],
        "created_at": None,
        "updated_at": None,
    }
    db["customers"].append(customer)
    return CustomerResponse.model_validate(customer)


@router.get("/customers", response_model=list[CustomerResponse])
def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[CustomerResponse]:
    db = _get_db()
    start = (page - 1) * page_size
    return [CustomerResponse.model_validate(c) for c in db["customers"][start : start + page_size]]


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: str) -> CustomerResponse:
    db = _get_db()
    for c in db["customers"]:
        if c["id"] == customer_id:
            return CustomerResponse.model_validate(c)
    raise HTTPException(status_code=404, detail="Customer not found")


@router.put("/customers/{customer_id}", response_model=CustomerResponse)
def update_customer(customer_id: str, req: CustomerUpdate) -> CustomerResponse:
    db = _get_db()
    for c in db["customers"]:
        if c["id"] == customer_id:
            update_data = req.model_dump(exclude_unset=True)
            c.update(update_data)
            return CustomerResponse.model_validate(c)
    raise HTTPException(status_code=404, detail="Customer not found")


@router.delete("/customers/{customer_id}", status_code=204, response_model=None, response_class=Response)
def delete_customer(customer_id: str) -> None:
    db = _get_db()
    for i, c in enumerate(db["customers"]):
        if c["id"] == customer_id:
            db["customers"].pop(i)
            # Soft-unlink documents
            for d in db["documents"]:
                if d.get("customer_id") == customer_id:
                    d["customer_id"] = None
            return
    raise HTTPException(status_code=404, detail="Customer not found")


@router.get("/customers/{customer_id}/documents", response_model=list[DocumentResponse])
def list_customer_documents(
    customer_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[DocumentResponse]:
    db = _get_db()
    # Verify customer exists
    if not any(c["id"] == customer_id for c in db["customers"]):
        raise HTTPException(status_code=404, detail="Customer not found")
    docs = [d for d in db["documents"] if d.get("customer_id") == customer_id]
    start = (page - 1) * page_size
    return [DocumentResponse.model_validate(d) for d in docs[start : start + page_size]]


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------


@router.post("/rag/retrieve", response_model=RAGContextResponse)
def rag_retrieve(req: RAGRetrieveRequest) -> RAGContextResponse:
    db = _get_db()
    chunks = _get_search_chunks(db, customer_id=req.customer_id)
    result = retrieve_context(
        req.question, chunks, top_k=req.top_k, max_tokens=req.max_tokens, customer_id=req.customer_id
    )
    return RAGContextResponse(
        context=[RAGContextItem(**item) for item in result["context"]],
        total_tokens=result["total_tokens"],
    )


@router.post("/rag/context")
def rag_context(req: RAGRetrieveRequest) -> dict[str, Any]:
    """Build full RAG context with formatted string."""
    db = _get_db()
    chunks = _get_search_chunks(db, customer_id=req.customer_id)
    result = build_rag_context(
        req.question, chunks, top_k=req.top_k, max_tokens=req.max_tokens, customer_id=req.customer_id
    )
    return {
        "context": [RAGContextItem(**item) for item in result["context"]],
        "context_str": result.get("context_str", ""),
        "total_tokens": result["total_tokens"],
    }


# ---------------------------------------------------------------------------
# Batch Import
# ---------------------------------------------------------------------------


@router.post("/import/batch", response_model=BatchImportResponse, status_code=201)
def batch_import(
    request: Request, response: Response, req: BatchImportRequest
) -> BatchImportResponse:
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
    db = _get_db()
    imported = 0
    failed = 0
    doc_ids: list[str] = []

    for file_path in req.file_paths:
        try:
            if file_path.endswith(".md"):
                imported_data = import_markdown(file_path)
            else:
                # Try reading as text
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
                imported_data = import_text(text, title=os.path.basename(file_path))

            doc_id = str(uuid.uuid4())
            doc: dict[str, Any] = {
                "id": doc_id,
                "title": imported_data["title"],
                "framework": req.framework,
                "doc_type": req.doc_type,
                "visibility": "public",
                "customer_id": req.customer_id,
                "tags": [],
                "metadata": {},
                "summary": imported_data["text"][:200] if imported_data["text"] else None,
                "chunk_count": imported_data["chunk_count"],
                "status": "ready",
                "file_path": file_path,
                "content_hash": hashlib.md5(imported_data["text"].encode()).hexdigest(),
                "created_at": None,
                "updated_at": None,
            }
            db["documents"].append(doc)

            for i, c in enumerate(imported_data["chunks"]):
                chunk_doc: dict[str, Any] = {
                    "id": str(uuid.uuid4()),
                    "doc_id": doc_id,
                    "customer_id": req.customer_id,
                    "text": c["text"],
                    "section": None,
                    "page": None,
                    "chunk_index": i,
                    "token_count": c.get("token_count", 0),
                    "embedding": None,
                    "tsvector": c.get("tsvector", ""),
                    "metadata": {},
                    "created_at": None,
                }
                db["chunks"].append(chunk_doc)

            imported += 1
            doc_ids.append(doc_id)
        except Exception:
            failed += 1

    return BatchImportResponse(imported=imported, failed=failed, document_ids=doc_ids)
