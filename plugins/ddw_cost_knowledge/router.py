"""DDW 造价知识库 API 路由（10 个 API）。

  POST   /documents/upload
  GET    /documents
  GET    /documents/{id}
  POST   /documents/{id}/extract
  DELETE /documents/{id}
  GET    /search
  POST   /estimates
  GET    /estimates/{id}
  GET    /stats
  POST   /batch-import
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_cost_knowledge.schemas import (
    BatchImportReq,
    DocumentUploadReq,
    EstimateCreateReq,
)

logger = logging.getLogger(__name__)


def _doc_to_dict(d) -> Dict[str, Any]:
    return {
        "id": d.id,
        "tenant_id": d.tenant_id,
        "file_name": d.file_name,
        "file_path": d.file_path,
        "doc_type": d.doc_type,
        "project_name": d.project_name,
        "project_type": d.project_type,
        "total_cost": d.total_cost,
        "area": d.area,
        "unit_price": d.unit_price,
        "extracted_data": d.extracted_data,
        "status": d.status,
        "notes": d.notes,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }


def _est_to_dict(e) -> Dict[str, Any]:
    return {
        "id": e.id,
        "tenant_id": e.tenant_id,
        "project_name": e.project_name,
        "project_type": e.project_type,
        "area": e.area,
        "floor_count": e.floor_count,
        "structure_type": e.structure_type,
        "estimate_result": e.estimate_result,
        "reference_docs": e.reference_docs,
        "confidence": e.confidence,
        "notes": e.notes,
        "created_at": e.created_at,
    }


def build_router(plugin) -> APIRouter:
    router = APIRouter(prefix=f"/api/v1/plugins/{plugin.name}", tags=[plugin.name])
    imp = plugin.import_service
    ext = plugin.extract_service
    est = plugin.estimate_service
    srch = plugin.search_service

    # ----------- 页面挂载 ----------- #
    from pathlib import Path as _P

    from fastapi.responses import FileResponse

    _HTML = _P(__file__).resolve().parent / "templates" / "cost_knowledge.html"

    async def _ui():
        return FileResponse(str(_HTML), media_type="text/html; charset=utf-8")

    router.add_api_route("/ui", _ui, methods=["GET"], include_in_schema=False)

    # ----------- 文件 ----------- #

    async def _upload(request: Request, response: Response, req: DocumentUploadReq):
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
        async with session_scope() as s, bypass_tenant_filter():
            doc = await imp.upload(s, req.model_dump(exclude_none=True))
            await s.commit()
        return _doc_to_dict(doc)

    async def _list_docs(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        doc_type: Optional[str] = None,
        project_type: Optional[str] = None,
        status: Optional[str] = None,
    ):
        async with session_scope() as s, bypass_tenant_filter():
            total, rows = await imp.list(s, page, page_size, doc_type, project_type, status)
            return {"total": total, "items": [_doc_to_dict(r) for r in rows]}

    async def _get_doc(doc_id: int):
        async with session_scope() as s, bypass_tenant_filter():
            d = await imp.get(s, doc_id)
            if d is None:
                raise HTTPException(status_code=404, detail="document not found")
            return _doc_to_dict(d)

    async def _delete_doc(doc_id: int):
        async with session_scope() as s, bypass_tenant_filter():
            ok = await imp.delete(s, doc_id)
            if not ok:
                raise HTTPException(status_code=404, detail="document not found")
            await s.commit()
        return {"deleted": doc_id}

    async def _extract(doc_id: int, use_llm: bool = False):
        async with session_scope() as s, bypass_tenant_filter():
            d = await imp.get(s, doc_id)
            if d is None:
                raise HTTPException(status_code=404, detail="document not found")
            try:
                data = await ext.extract(s, d, use_llm=use_llm)
                await s.commit()
                return {
                    "document_id": doc_id,
                    "status": d.status,
                    "extracted_data": data,
                    "message": "提炼完成",
                }
            except Exception as e:  # noqa: BLE001
                await s.commit()
                raise HTTPException(status_code=500, detail=f"提炼失败：{e}")

    # ----------- 检索 ----------- #

    async def _search(
        q: str = Query(..., min_length=1, max_length=200),
        project_type: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = Query(20, ge=1, le=100),
    ):
        async with session_scope() as s, bypass_tenant_filter():
            hits = await srch.search(s, q, project_type, doc_type, limit)
        return {"query": q, "total": len(hits), "hits": hits}

    # ----------- 估算 ----------- #

    async def _create_estimate(req: EstimateCreateReq):
        async with session_scope() as s, bypass_tenant_filter():
            row = await est.create(s, req.model_dump(exclude_none=True))
            await s.commit()
        return _est_to_dict(row)

    async def _get_estimate(est_id: int):
        async with session_scope() as s, bypass_tenant_filter():
            e = await est.get(s, est_id)
            if e is None:
                raise HTTPException(status_code=404, detail="estimate not found")
            return _est_to_dict(e)

    # ----------- 统计 ----------- #

    async def _stats():
        from sqlalchemy import select

        from plugins.ddw_cost_knowledge.models import CostDocument, CostEstimate

        async with session_scope() as s, bypass_tenant_filter():
            docs = (await s.execute(select(CostDocument))).scalars().all()
            ests = (await s.execute(select(CostEstimate))).scalars().all()

        by_type: Dict[str, int] = {}
        by_ptype: Dict[str, int] = {}
        ups: List[float] = []
        tc: List[float] = []
        for d in docs:
            by_type[d.doc_type] = by_type.get(d.doc_type, 0) + 1
            if d.project_type:
                by_ptype[d.project_type] = by_ptype.get(d.project_type, 0) + 1
            if d.unit_price:
                ups.append(d.unit_price)
            if d.total_cost:
                tc.append(d.total_cost)
        return {
            "documents_total": len(docs),
            "documents_by_type": by_type,
            "documents_by_project_type": by_ptype,
            "estimates_total": len(ests),
            "avg_unit_price": round(sum(ups) / len(ups), 2) if ups else 0.0,
            "avg_total_cost": round(sum(tc) / len(tc), 2) if tc else 0.0,
        }

    # ----------- 批量导入 ----------- #

    async def _batch_import(req: BatchImportReq):
        items = [i.model_dump() for i in req.items]
        async with session_scope() as s, bypass_tenant_filter():
            result = await imp.batch_import(
                s, items, tenant_id=req.tenant_id, auto_extract=req.auto_extract
            )
            await s.commit()
        return result

    # ----------- 路由 ----------- #

    router.add_api_route("/documents/upload", _upload, methods=["POST"])
    router.add_api_route("/documents", _list_docs, methods=["GET"])
    router.add_api_route("/documents/{doc_id}", _get_doc, methods=["GET"])
    router.add_api_route("/documents/{doc_id}", _delete_doc, methods=["DELETE"])
    router.add_api_route("/documents/{doc_id}/extract", _extract, methods=["POST"])

    router.add_api_route("/search", _search, methods=["GET"])

    router.add_api_route("/estimates", _create_estimate, methods=["POST"])
    router.add_api_route("/estimates/{est_id}", _get_estimate, methods=["GET"])

    router.add_api_route("/stats", _stats, methods=["GET"])
    router.add_api_route("/batch-import", _batch_import, methods=["POST"])

    
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw_cost_knowledge", "version": "0.1.0", "status": "ok"}

    return router


__all__ = ["build_router"]
