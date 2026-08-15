"""DDW 设计人员资质管理插件 API 路由。

14 个 API：
  POST   /certs
  GET    /certs
  GET    /certs/{id}
  PUT    /certs/{id}
  DELETE /certs/{id}
  POST   /certs/import
  GET    /certs/export
  GET    /expiring
  GET    /stats
  GET    /persons/{id}/certs
  POST   /renewals
  PUT    /renewals/{id}
  GET    /renewals
  GET    /alerts
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_personnel_qual.schemas import (
    CertCreateReq,
    CertImportReq,
    CertUpdateReq,
    RenewalCreateReq,
    RenewalUpdateReq,
)
from plugins.ddw_personnel_qual.services.cert_service import parse_csv

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------


def _cert_to_dict(c) -> Dict[str, Any]:
    return {
        "id": c.id,
        "tenant_id": c.tenant_id,
        "person_name": c.person_name,
        "person_id": c.person_id,
        "cert_type": c.cert_type,
        "cert_no": c.cert_no,
        "cert_level": c.cert_level,
        "issue_org": c.issue_org,
        "issue_date": c.issue_date,
        "expiry_date": c.expiry_date,
        "renewal_date": c.renewal_date,
        "status": c.status,
        "notes": c.notes,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def build_router(plugin) -> APIRouter:
    router = APIRouter(prefix=f"/api/v1/plugins/{plugin.name}", tags=[plugin.name])
    cert = plugin.cert_service
    expiry = plugin.expiry_service
    renewal = plugin.renewal_service

    # ----------- 页面挂载 ----------- #
    from pathlib import Path as _P

    from fastapi.responses import FileResponse

    _HTML = _P(__file__).resolve().parent / "templates" / "personnel_qual.html"

    async def _ui():
        return FileResponse(str(_HTML), media_type="text/html; charset=utf-8")

    router.add_api_route("/ui", _ui, methods=["GET"], include_in_schema=False)

    # ----------- 证书 CRUD ----------- #

    async def _create(req: CertCreateReq):
        payload = req.model_dump(exclude_none=True)
        async with session_scope() as s, bypass_tenant_filter():
            row = await cert.create(s, payload)
            await s.commit()
        return _cert_to_dict(row)

    async def _list(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        cert_type: Optional[str] = None,
        status: Optional[str] = None,
        person_name: Optional[str] = None,
    ):
        async with session_scope() as s, bypass_tenant_filter():
            total, rows = await cert.list(s, page, page_size, cert_type, status, person_name)
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [_cert_to_dict(r) for r in rows],
            }

    async def _get(cert_id: int):
        async with session_scope() as s, bypass_tenant_filter():
            row = await cert.get(s, cert_id)
            if row is None:
                raise HTTPException(status_code=404, detail="cert not found")
            return _cert_to_dict(row)

    async def _update(cert_id: int, req: CertUpdateReq):
        patch = req.model_dump(exclude_none=True)
        async with session_scope() as s, bypass_tenant_filter():
            row = await cert.update(s, cert_id, patch)
            if row is None:
                raise HTTPException(status_code=404, detail="cert not found")
            await s.commit()
        return _cert_to_dict(row)

    async def _delete(cert_id: int):
        async with session_scope() as s, bypass_tenant_filter():
            ok = await cert.delete(s, cert_id)
            if not ok:
                raise HTTPException(status_code=404, detail="cert not found")
            await s.commit()
        return {"deleted": cert_id}

    # ----------- 导入导出 ----------- #

    async def _import(req: CertImportReq):
        if req.format != "csv":
            raise HTTPException(status_code=400, detail="仅支持 CSV（Excel 解析依赖未启用）")
        _, rows = parse_csv(req.content, skip_header=req.skip_header)
        if not rows:
            return {"success": 0, "failed": 0, "errors": []}
        # 默认租户
        for r in rows:
            r.setdefault("tenant_id", req.tenant_id)
            r.setdefault("status", "active")
        async with session_scope() as s, bypass_tenant_filter():
            result = await cert.import_rows(s, rows)
            await s.commit()
        return result

    async def _export():
        async with session_scope() as s, bypass_tenant_filter():
            content = await cert.export_csv(s)
        return {
            "filename": f"personnel_certs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "content": content,
            "count": content.count("\n") - 1,
        }

    # ----------- 到期预警 / 统计 ----------- #

    async def _expiring():
        async with session_scope() as s, bypass_tenant_filter():
            data = await expiry.scan(s, persist=True)
            await s.commit()
        return data

    async def _stats():
        async with session_scope() as s, bypass_tenant_filter():
            return await cert.stats(s)

    async def _person_certs(person_id: str):
        async with session_scope() as s, bypass_tenant_filter():
            rows = await cert.list_by_person(s, person_id)
            return {"person_id": person_id, "items": [_cert_to_dict(r) for r in rows]}

    # ----------- 年检 ----------- #

    async def _create_renewal(req: RenewalCreateReq):
        payload = req.model_dump(exclude_none=True)
        async with session_scope() as s, bypass_tenant_filter():
            row = await renewal.create(s, payload)
            await s.commit()
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "cert_id": row.cert_id,
            "renewal_date": row.renewal_date,
            "result": row.result,
            "operator": row.operator,
            "notes": row.notes,
            "status": row.status,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    async def _update_renewal(renewal_id: int, req: RenewalUpdateReq):
        patch = req.model_dump(exclude_none=True)
        async with session_scope() as s, bypass_tenant_filter():
            row = await renewal.update(s, renewal_id, patch)
            if row is None:
                raise HTTPException(status_code=404, detail="renewal not found")
            await s.commit()
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "cert_id": row.cert_id,
            "renewal_date": row.renewal_date,
            "result": row.result,
            "operator": row.operator,
            "notes": row.notes,
            "status": row.status,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    async def _list_renewals(
        cert_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = Query(100, ge=1, le=500),
    ):
        async with session_scope() as s, bypass_tenant_filter():
            return await renewal.list(s, cert_id, status, limit)

    # ----------- 提醒 ----------- #

    async def _alerts(unread_only: bool = False, limit: int = Query(100, ge=1, le=500)):
        async with session_scope() as s, bypass_tenant_filter():
            return await expiry.list_alerts(s, unread_only=unread_only, limit=limit)

    # ----------- 路由注册 ----------- #

    router.add_api_route("/certs", _create, methods=["POST"])
    router.add_api_route("/certs", _list, methods=["GET"])
    router.add_api_route("/certs/import", _import, methods=["POST"])
    router.add_api_route("/certs/export", _export, methods=["GET"])
    router.add_api_route("/certs/{cert_id}", _get, methods=["GET"])
    router.add_api_route("/certs/{cert_id}", _update, methods=["PUT"])
    router.add_api_route("/certs/{cert_id}", _delete, methods=["DELETE"])

    router.add_api_route("/expiring", _expiring, methods=["GET"])
    router.add_api_route("/stats", _stats, methods=["GET"])
    router.add_api_route("/persons/{person_id}/certs", _person_certs, methods=["GET"])

    router.add_api_route("/renewals", _create_renewal, methods=["POST"])
    router.add_api_route("/renewals", _list_renewals, methods=["GET"])
    router.add_api_route("/renewals/{renewal_id}", _update_renewal, methods=["PUT"])

    router.add_api_route("/alerts", _alerts, methods=["GET"])

    
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw_personnel_qual", "version": "1.0.0", "status": "ok"}

    return router


__all__ = ["build_router"]
