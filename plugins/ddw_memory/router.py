"""ddw_memory API 路由 — 四层持久化记忆引擎。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response

from .llm_summarizer import generate_position_answer
from .models import (
    AutoCaptureConfigUpdateReq,
    LayerConfigReq,
    MemoryCreateReq,
    MemoryLayer,
    MemoryMigrationReq,
    MemorySearchReq,
    MemoryUpdateReq,
    PositionKnowledgeQueryReq,
    PositionSOPTemplateCreateReq,
    PositionSOPTemplateUpdateReq,
    SessionSummaryCaptureReq,
)
from .service import MemoryService

logger = logging.getLogger(__name__)

_service = MemoryService()


def get_service() -> MemoryService:
    return _service


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/plugins/ddw-memory", tags=["ddw-memory"])

    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-memory", "version": "2.0.0", "status": "ok", "engine": "sqlalchemy"}

    # ── 记忆 CRUD ──────────────────────────────────────────

    @router.post("/memories", status_code=201)
    async def create_memory(
        request: Request, response: Response, data: MemoryCreateReq,
        tenant_id: int = Query(1)
    ) -> dict:
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
        svc = get_service()
        try:
            entry = await svc.create_memory(
                tenant_id=tenant_id,
                layer=data.layer,
                content=data.content,
                creator_id=data.creator_id,
                department_id=data.department_id,
                position_id=data.position_id,
                tags=data.tags,
                source_type=data.source_type,
                expires_at=data.expires_at,
            )
            return entry.model_dump(mode="json")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/memories")
    async def list_memories(
        tenant_id: int = Query(1),
        layer: MemoryLayer | None = Query(None),
        department_id: int | None = Query(None),
        position_id: int | None = Query(None),
        creator_id: int | None = Query(None),
        include_deleted: bool = Query(False),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ) -> dict:
        svc = get_service()
        return await svc.list_memories(
            tenant_id=tenant_id, layer=layer, department_id=department_id,
            position_id=position_id, creator_id=creator_id,
            include_deleted=include_deleted, page=page, page_size=page_size,
        )

    @router.get("/memories/{memory_id}")
    async def get_memory(memory_id: int, tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        entry = await svc.get_memory(tenant_id=tenant_id, memory_id=memory_id)
        if not entry:
            raise HTTPException(status_code=404, detail=f"memory {memory_id} not found")
        return entry.model_dump(mode="json")

    @router.put("/memories/{memory_id}")
    async def update_memory(memory_id: int, data: MemoryUpdateReq, tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        entry = await svc.update_memory(
            tenant_id=tenant_id, memory_id=memory_id,
            content=data.content, summary=data.summary,
            tags=data.tags, expires_at=data.expires_at,
        )
        if not entry:
            raise HTTPException(status_code=404, detail=f"memory {memory_id} not found")
        return entry.model_dump(mode="json")

    @router.delete("/memories/{memory_id}")
    async def delete_memory(memory_id: int, tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        ok = await svc.delete_memory(tenant_id=tenant_id, memory_id=memory_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"memory {memory_id} not found")
        return {"deleted": True, "id": memory_id}

    # ── 记忆检索 ────────────────────────────────────────────

    @router.post("/search")
    async def search_memories(data: MemorySearchReq, tenant_id: int = Query(1), user_id: int = Query(1)) -> dict:
        svc = get_service()
        result = await svc.search_memories(
            tenant_id=tenant_id, query=data.query, user_id=user_id,
            layers=data.layers if data.layers else None,
            department_id=data.department_id, position_id=data.position_id,
            top_k=data.top_k, search_mode=data.search_mode,
        )
        return result.model_dump(mode="json")

    # ── 自动捕获 ────────────────────────────────────────────

    @router.post("/capture/session-summary")
    async def capture_session_summary(data: SessionSummaryCaptureReq, tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        config = await svc.get_capture_config(tenant_id)
        if not config.get("enabled", True):
            return {"captured": False, "reason": "disabled"}

        from .auto_capture import maybe_capture_session

        async def _llm_chat(system: str, user: str) -> str:
            from core.llm_gateway.base import ChatMessage
            from core.llm_gateway.gateway import chat as gateway_chat
            resp = await gateway_chat([ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)])
            return resp.content

        result = await maybe_capture_session(
            tenant_id=tenant_id, user_id=data.user_id, session_id=data.session_id,
            messages=data.messages, config=config,
            llm_chat_fn=_llm_chat, create_pending_fn=svc.create_pending_capture,
        )
        return {"captured": bool(result), **(result or {"reason": "below_threshold"})}

    @router.get("/capture/pending")
    async def list_pending_captures(tenant_id: int = Query(1), user_id: int | None = Query(None)) -> dict:
        svc = get_service()
        items = await svc.list_pending_captures(tenant_id=tenant_id, user_id=user_id)
        return {"items": items, "total": len(items)}

    @router.post("/capture/{capture_id}/approve")
    async def approve_capture(capture_id: int, tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        entry = await svc.approve_capture(tenant_id=tenant_id, capture_id=capture_id)
        if not entry:
            raise HTTPException(status_code=404, detail="capture not found or already reviewed")
        return {"approved": True, "memory": entry.model_dump(mode="json")}

    @router.post("/capture/{capture_id}/reject")
    async def reject_capture(capture_id: int, tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        ok = await svc.reject_capture(tenant_id=tenant_id, capture_id=capture_id)
        if not ok:
            raise HTTPException(status_code=404, detail="capture not found or already reviewed")
        return {"rejected": True}

    @router.get("/capture/config")
    async def get_capture_config(tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        return await svc.get_capture_config(tenant_id=tenant_id)

    @router.put("/capture/config")
    async def update_capture_config(data: AutoCaptureConfigUpdateReq, tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        return await svc.update_capture_config(
            tenant_id=tenant_id, enabled=data.enabled,
            capture_after_turns=data.capture_after_turns,
            auto_archive_to_department=data.auto_archive_to_department,
            exclude_patterns=data.exclude_patterns,
        )

    # ── 岗位 SOP ────────────────────────────────────────────

    @router.post("/templates/sop", status_code=201)
    async def create_sop_template(data: PositionSOPTemplateCreateReq, tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        tmpl = await svc.create_sop_template(
            tenant_id=tenant_id, position_name=data.position_name,
            sop_steps=data.sop_steps, position_id=data.position_id,
            knowledge_doc_ids=data.knowledge_doc_ids,
            applicable_departments=data.applicable_departments,
        )
        return tmpl.model_dump(mode="json")

    @router.get("/templates/sop")
    async def list_sop_templates(tenant_id: int = Query(1), position_id: int | None = Query(None)) -> dict:
        svc = get_service()
        items = await svc.list_sop_templates(tenant_id=tenant_id, position_id=position_id)
        return {"items": [t.model_dump(mode="json") for t in items], "total": len(items)}

    @router.get("/templates/sop/{template_id}")
    async def get_sop_template(template_id: int, tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        tmpl = await svc.get_sop_template(tenant_id=tenant_id, template_id=template_id)
        if not tmpl:
            raise HTTPException(status_code=404, detail="SOP template not found")
        return tmpl.model_dump(mode="json")

    @router.put("/templates/sop/{template_id}")
    async def update_sop_template(template_id: int, data: PositionSOPTemplateUpdateReq, tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        tmpl = await svc.update_sop_template(
            tenant_id=tenant_id, template_id=template_id,
            sop_steps=data.sop_steps, knowledge_doc_ids=data.knowledge_doc_ids,
            applicable_departments=data.applicable_departments,
        )
        if not tmpl:
            raise HTTPException(status_code=404, detail="SOP template not found")
        return tmpl.model_dump(mode="json")

    @router.post("/templates/sop/query")
    async def query_position_knowledge(data: PositionKnowledgeQueryReq, tenant_id: int = Query(1), user_id: int = Query(1)) -> dict:
        svc = get_service()
        result = await svc.query_position_knowledge(
            tenant_id=tenant_id, user_id=user_id,
            position_id=data.position_id, question=data.question,
        )

        async def _llm_chat(system: str, user: str) -> str:
            from core.llm_gateway.base import ChatMessage
            from core.llm_gateway.gateway import chat as gateway_chat
            resp = await gateway_chat([ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)])
            return resp.content

        sop_steps = result["sop_steps"]
        pos_mems = [m.content[:200] for m in result["position_memories"]]
        redlines = [m.content[:200] for m in result["enterprise_redlines"]]

        templates = await svc.list_sop_templates(tenant_id, position_id=data.position_id)
        pos_name = templates[0].position_name if templates else f"岗位#{data.position_id}"

        ai_answer = await generate_position_answer(
            position_name=pos_name, sop_steps=sop_steps,
            position_memories=pos_mems, enterprise_redlines=redlines,
            question=data.question, llm_chat_fn=_llm_chat,
        )

        sources = []
        if sop_steps:
            sources.append("SOP")
        if pos_mems:
            sources.append("岗位知识")
        if redlines:
            sources.append("企业红线")
        if not sources:
            sources.append("AI建议")

        return {
            "sop_steps": sop_steps,
            "position_memories": [m.model_dump(mode="json") for m in result["position_memories"]],
            "enterprise_redlines": [m.model_dump(mode="json") for m in result["enterprise_redlines"]],
            "ai_answer": ai_answer, "sources": sources,
        }

    # ── 记忆迁移 ────────────────────────────────────────────

    @router.post("/migrate")
    async def migrate_memories(data: MemoryMigrationReq, tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        return await svc.migrate_memories(
            tenant_id=tenant_id, source_user_id=data.source_user_id,
            target_user_id=data.target_user_id, scope=data.scope,
        )

    # ── 离职清除 ────────────────────────────────────────────

    @router.post("/cleanup/soft-delete")
    async def cleanup_soft_delete(user_id: int = Query(...), tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        count = await svc.soft_delete_user_memories(tenant_id=tenant_id, user_id=user_id)
        return {"soft_deleted": count}

    @router.post("/cleanup/physical-delete")
    async def cleanup_physical_delete(tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        count = await svc.physical_delete_expired(tenant_id=tenant_id)
        return {"physical_deleted": count}

    # ── 层级配置 ────────────────────────────────────────────

    @router.get("/config/layers")
    async def get_layer_config() -> dict:
        return {"enabled_layers": [lyr.value for lyr in MemoryLayer]}

    @router.put("/config/layers")
    async def set_layer_config(data: LayerConfigReq) -> dict:
        return {"enabled_layers": [lyr.value for lyr in data.layers]}

    # ── 统计 ────────────────────────────────────────────────

    @router.get("/stats")
    async def get_stats(tenant_id: int = Query(1)) -> dict:
        svc = get_service()
        return await svc.get_stats(tenant_id=tenant_id)

    return router


__all__ = ["build_router", "get_service"]
