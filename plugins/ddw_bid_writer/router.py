"""DDW 投标标书插件 API 路由（16 个 API）。

  项目：POST/GET/PUT/DELETE /projects
  生成：POST /projects/{id}/generate
  文档：GET /projects/{id}/documents / GET/PUT /documents/{id}
  修饰：POST /documents/{id}/refine
  审查：POST /documents/{id}/review
  批准：POST /documents/{id}/approve
  模板：GET/POST/PUT/DELETE /templates
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_bid_writer.schemas import (
    ApproveReq,
    AssessImportanceReq,
    DocumentUpdateReq,
    GenerateReq,
    KnowledgeBootstrapReq,
    ProjectCreateReq,
    ProjectUpdateReq,
    RefineReq,
    ReviewReq,
    SectionRegenerateReq,
    TemplateCreateReq,
    TemplateUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------


def _project_to_dict(p) -> Dict[str, Any]:
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "project_name": p.project_name,
        "client_name": p.client_name,
        "bid_deadline": p.bid_deadline,
        "project_type": p.project_type,
        "estimated_amount": p.estimated_amount,
        "status": p.status,
        "notes": p.notes,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _doc_to_dict(d) -> Dict[str, Any]:
    return {
        "id": d.id,
        "bid_project_id": d.bid_project_id,
        "doc_type": d.doc_type,
        "style": d.style,
        "title": d.title,
        "content": d.content,
        "version": d.version,
        "status": d.status,
        "review_notes": d.review_notes,
        "review_score": d.review_score,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }


def _template_to_dict(t) -> Dict[str, Any]:
    return {
        "id": t.id,
        "tenant_id": t.tenant_id,
        "name": t.name,
        "doc_type": t.doc_type,
        "content": t.content,
        "is_default": bool(t.is_default),
        "description": t.description,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def build_router(plugin) -> APIRouter:
    router = APIRouter(prefix=f"/api/v1/plugins/{plugin.name}", tags=[plugin.name])
    tmpl = plugin.template_service
    gen = plugin.generate_service
    sty = plugin.style_service
    rev = plugin.review_service

    # ----------- 页面挂载 ----------- #
    from pathlib import Path as _P

    from fastapi.responses import FileResponse

    _HTML = _P(__file__).resolve().parent / "templates" / "bid_writer.html"

    async def _ui():
        return FileResponse(str(_HTML), media_type="text/html; charset=utf-8")

    router.add_api_route("/ui", _ui, methods=["GET"], include_in_schema=False)

    # ----------- 项目 ----------- #

    async def _create_project(req: ProjectCreateReq):
        async with session_scope() as s, bypass_tenant_filter():
            from plugins.ddw_bid_writer.models import BidProject
            p = BidProject(**req.model_dump(exclude_none=True))
            s.add(p)
            await s.commit()
            await s.refresh(p)
        return _project_to_dict(p)

    async def _list_projects(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        status: Optional[str] = None,
        project_type: Optional[str] = None,
    ):
        from sqlalchemy import and_, func, select

        from plugins.ddw_bid_writer.models import BidProject

        where = []
        if status:
            where.append(BidProject.status == status)
        if project_type:
            where.append(BidProject.project_type == project_type)
        count_q = select(func.count(BidProject.id))
        list_q = select(BidProject).order_by(BidProject.id.desc())
        if where:
            count_q = count_q.where(and_(*where))
            list_q = list_q.where(and_(*where))
        async with session_scope() as s, bypass_tenant_filter():
            total = (await s.execute(count_q)).scalar_one()
            rows = (
                await s.execute(list_q.offset((page - 1) * page_size).limit(page_size))
            ).scalars().all()
        return {"total": total, "items": [_project_to_dict(r) for r in rows]}

    async def _get_project(project_id: int):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidProject

        async with session_scope() as s, bypass_tenant_filter():
            p = (
                await s.execute(select(BidProject).where(BidProject.id == project_id))
            ).scalar_one_or_none()
            if p is None:
                raise HTTPException(status_code=404, detail="project not found")
            return _project_to_dict(p)

    async def _update_project(project_id: int, req: ProjectUpdateReq):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidProject

        patch = req.model_dump(exclude_none=True)
        async with session_scope() as s, bypass_tenant_filter():
            p = (
                await s.execute(select(BidProject).where(BidProject.id == project_id))
            ).scalar_one_or_none()
            if p is None:
                raise HTTPException(status_code=404, detail="project not found")
            for k, v in patch.items():
                if v is not None and hasattr(p, k):
                    setattr(p, k, v)
            await s.commit()
            await s.refresh(p)
        return _project_to_dict(p)

    async def _delete_project(project_id: int):
        from sqlalchemy import delete, select

        from plugins.ddw_bid_writer.models import BidDocument, BidProject

        async with session_scope() as s, bypass_tenant_filter():
            p = (
                await s.execute(select(BidProject).where(BidProject.id == project_id))
            ).scalar_one_or_none()
            if p is None:
                raise HTTPException(status_code=404, detail="project not found")
            # 先删子标书
            await s.execute(delete(BidDocument).where(BidDocument.bid_project_id == project_id))
            await s.delete(p)
            await s.commit()
        return {"deleted": project_id}

    # ----------- 生成 ----------- #

    async def _generate(project_id: int, req: GenerateReq):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidProject

        async with session_scope() as s, bypass_tenant_filter():
            p = (
                await s.execute(select(BidProject).where(BidProject.id == project_id))
            ).scalar_one_or_none()
            if p is None:
                raise HTTPException(status_code=404, detail="project not found")
            doc = await gen.generate(
                s, p,
                doc_type=req.doc_type, style=req.style, title=req.title,
                extra_requirements=req.extra_requirements, template_id=req.template_id,
                mode=req.mode,
            )
            await s.commit()
        return _doc_to_dict(doc)

    # ----------- 文档 ----------- #

    async def _list_documents(project_id: int):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidDocument

        async with session_scope() as s, bypass_tenant_filter():
            rows = (
                await s.execute(
                    select(BidDocument)
                    .where(BidDocument.bid_project_id == project_id)
                    .order_by(BidDocument.id.desc())
                )
            ).scalars().all()
        return {"total": len(rows), "items": [_doc_to_dict(r) for r in rows]}

    async def _get_document(doc_id: int):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidDocument

        async with session_scope() as s, bypass_tenant_filter():
            d = (
                await s.execute(select(BidDocument).where(BidDocument.id == doc_id))
            ).scalar_one_or_none()
            if d is None:
                raise HTTPException(status_code=404, detail="document not found")
            return _doc_to_dict(d)

    async def _update_document(doc_id: int, req: DocumentUpdateReq):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidDocument

        patch = req.model_dump(exclude_none=True)
        async with session_scope() as s, bypass_tenant_filter():
            d = (
                await s.execute(select(BidDocument).where(BidDocument.id == doc_id))
            ).scalar_one_or_none()
            if d is None:
                raise HTTPException(status_code=404, detail="document not found")
            for k, v in patch.items():
                if v is not None and hasattr(d, k):
                    setattr(d, k, v)
            await s.commit()
            await s.refresh(d)
        return _doc_to_dict(d)

    # ----------- 风格修饰 ----------- #

    async def _refine(doc_id: int, req: RefineReq):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidDocument

        async with session_scope() as s, bypass_tenant_filter():
            d = (
                await s.execute(select(BidDocument).where(BidDocument.id == doc_id))
            ).scalar_one_or_none()
            if d is None:
                raise HTTPException(status_code=404, detail="document not found")
            try:
                new_doc, diff = await sty.refine(s, d, target_style=req.style, instructions=req.instructions)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            await s.commit()
        return {
            "document_id": doc_id,
            "style": req.style,
            "version_before": d.version,
            "version_after": new_doc.version,
            "diff_summary": diff,
            "new_document_id": new_doc.id,
        }

    # ----------- 审查 ----------- #

    async def _review(doc_id: int, req: ReviewReq):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidDocument

        async with session_scope() as s, bypass_tenant_filter():
            d = (
                await s.execute(select(BidDocument).where(BidDocument.id == doc_id))
            ).scalar_one_or_none()
            if d is None:
                raise HTTPException(status_code=404, detail="document not found")
            result = await rev.review(s, d, check_items=req.check_items)
            await s.commit()
        return result

    # ----------- 批准 ----------- #

    async def _approve(doc_id: int, req: ApproveReq):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidDocument, BidProject

        async with session_scope() as s, bypass_tenant_filter():
            d = (
                await s.execute(select(BidDocument).where(BidDocument.id == doc_id))
            ).scalar_one_or_none()
            if d is None:
                raise HTTPException(status_code=404, detail="document not found")
            d.status = "approved"
            if req.notes:
                d.review_notes = (d.review_notes or "") + f"\n[批准:{req.approver or '-'}] {req.notes}"
            # 项目状态 -> approved
            p = (
                await s.execute(
                    select(BidProject).where(BidProject.id == d.bid_project_id)
                )
            ).scalar_one_or_none()
            if p is not None:
                p.status = "approved"
            await s.commit()
        return {"document_id": doc_id, "status": "approved", "approver": req.approver}

    # ----------- 模板 ----------- #

    async def _list_templates(
        doc_type: Optional[str] = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        async with session_scope() as s, bypass_tenant_filter():
            total, rows = await tmpl.list(s, doc_type, page, page_size)
            return {"total": total, "items": [_template_to_dict(r) for r in rows]}

    async def _create_template(req: TemplateCreateReq):
        async with session_scope() as s, bypass_tenant_filter():
            row = await tmpl.create(s, req.model_dump(exclude_none=True))
            await s.commit()
        return _template_to_dict(row)

    async def _update_template(template_id: int, req: TemplateUpdateReq):
        patch = req.model_dump(exclude_none=True)
        async with session_scope() as s, bypass_tenant_filter():
            row = await tmpl.update(s, template_id, patch)
            if row is None:
                raise HTTPException(status_code=404, detail="template not found")
            await s.commit()
        return _template_to_dict(row)

    async def _delete_template(template_id: int):
        async with session_scope() as s, bypass_tenant_filter():
            ok = await tmpl.delete(s, template_id)
            if not ok:
                raise HTTPException(status_code=404, detail="template not found")
            await s.commit()
        return {"deleted": template_id}

    # ============================================================ #
    # C+D+E+F 方案新增 API
    # ============================================================ #

    from plugins.ddw_bid_writer.services.importance_detector import (
        ImportanceDetector as _ImportanceDetector,
    )
    from plugins.ddw_bid_writer.services.knowledge_bootstrap import (
        KnowledgeBootstrap as _KB,
    )

    _kb_bootstrap = _KB()
    _importance = _ImportanceDetector()

    # ----------- 知识库（D 方案）----------- #

    async def _kb_bootstrap_endpoint(req: KnowledgeBootstrapReq):
        from plugins.ddw_bid_writer.services.knowledge_bootstrap import (
            KnowledgeBootstrap,
        )

        kb = KnowledgeBootstrap()
        async with session_scope() as s, bypass_tenant_filter():
            result = await kb.run(s, tenant_id=req.tenant_id, folder=req.folder)
        return result

    async def _kb_status(tenant_id: int = Query(1, ge=1)):
        from plugins.ddw_bid_writer.services.knowledge_bootstrap import (
            KnowledgeBootstrap,
        )

        kb = KnowledgeBootstrap()
        async with session_scope() as s, bypass_tenant_filter():
            return await kb.stats_async(s, tenant_id=tenant_id)

    async def _kb_templates(tenant_id: int = Query(1, ge=1)):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import FactTemplate

        async with session_scope() as s, bypass_tenant_filter():
            rows = (
                await s.execute(
                    select(FactTemplate).where(FactTemplate.tenant_id == tenant_id)
                )
            ).scalars().all()
            return {
                "total": len(rows),
                "items": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "project_type": t.project_type,
                        "doc_type": t.doc_type,
                        "sample_count": t.sample_count,
                        "is_default": bool(t.is_default),
                        "style_baseline": t.style_baseline,
                        "personnel_template": t.personnel_template,
                        "section_structure": t.section_structure,
                        "notes": t.notes,
                    }
                    for t in rows
                ],
            }

    # ----------- 重要项目检测（F 方案）----------- #

    async def _assess_importance(project_id: int, req: AssessImportanceReq):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidDocument, BidProject

        async with session_scope() as s, bypass_tenant_filter():
            p = (
                await s.execute(select(BidProject).where(BidProject.id == project_id))
            ).scalar_one_or_none()
            if p is None:
                raise HTTPException(status_code=404, detail="project not found")
            # 检查是否是首次合作（无历史标书）
            has_history = (
                await s.execute(
                    select(BidDocument.id)
                    .where(BidDocument.bid_project_id == project_id)
                    .limit(1)
                )
            ).first() is not None
            # 简化：本次 is_first_with_client 由请求决定
            is_first = req.is_first_with_client or not has_history
            proj = {
                "project_name": p.project_name,
                "client_name": p.client_name,
                "project_type": p.project_type,
                "estimated_amount": p.estimated_amount,
                "bid_deadline": p.bid_deadline.isoformat() if p.bid_deadline else None,
            }
            assess = _importance.assess(proj, is_first_with_client=is_first, user_marked=req.user_marked)
        return assess.to_dict()

    # ----------- 阶段 1：仅大纲（C 方案）----------- #

    async def _plan(project_id: int, req: GenerateReq):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidProject

        async with session_scope() as s, bypass_tenant_filter():
            p = (
                await s.execute(select(BidProject).where(BidProject.id == project_id))
            ).scalar_one_or_none()
            if p is None:
                raise HTTPException(status_code=404, detail="project not found")
            result = await gen.plan(
                s, p,
                doc_type=req.doc_type, style=req.style,
            )
        return result

    # ----------- 章节级 API（F 渐进式披露）----------- #

    async def _list_sections(doc_id: int):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidSection

        async with session_scope() as s, bypass_tenant_filter():
            rows = (
                await s.execute(
                    select(BidSection)
                    .where(BidSection.bid_document_id == doc_id)
                    .order_by(BidSection.section_index)
                )
            ).scalars().all()
            return {
                "total": len(rows),
                "items": [
                    {
                        "id": r.id,
                        "bid_document_id": r.bid_document_id,
                        "section_index": r.section_index,
                        "section_title": r.section_title,
                        "outline_summary": r.outline_summary,
                        "content": r.content,
                        "rag_context": r.rag_context,
                        "is_locked": r.is_locked,
                        "review_score": r.review_score,
                        "review_notes": r.review_notes,
                    }
                    for r in rows
                ],
            }

    async def _regenerate_section(doc_id: int, section_index: int, req: SectionRegenerateReq):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidDocument, BidProject, BidSection

        async with session_scope() as s, bypass_tenant_filter():
            sec = (
                await s.execute(
                    select(BidSection).where(
                        BidSection.bid_document_id == doc_id,
                        BidSection.section_index == section_index,
                    )
                )
            ).scalar_one_or_none()
            if sec is None:
                raise HTTPException(status_code=404, detail="section not found")
            if sec.is_locked:
                raise HTTPException(status_code=400, detail="section is locked, please unlock first")
            # 单章重写：调用 SectionWriter._write_one
            from plugins.ddw_bid_writer.services.fact_sheet import (
                FactSheet,
                fact_sheet_from_dict,
            )
            from plugins.ddw_bid_writer.services.section_writer import (
                SectionWriter as _SW,
            )
            from plugins.ddw_bid_writer.services.vector_store import (
                TenantKnowledgeStore as _TKS,
            )

            doc = (
                await s.execute(select(BidDocument).where(BidDocument.id == doc_id))
            ).scalar_one_or_none()
            proj = (
                await s.execute(
                    select(BidProject).where(BidProject.id == doc.bid_project_id)
                )
            ).scalar_one_or_none()
            proj_dict = _project_to_dict(proj)
            fs = fact_sheet_from_dict(json.loads(sec.fact_sheet_snapshot or "{}")) if sec.fact_sheet_snapshot else FactSheet()
            sw = _SW()
            kb = _TKS(proj.tenant_id)
            section_dict = {
                "index": sec.section_index,
                "title": sec.section_title,
                "summary": sec.outline_summary or "",
                "target_words": 1200,
            }
            new_sec = await sw._write_one(
                project=proj_dict,
                doc_type=doc.doc_type,
                style=req.style or doc.style,
                section=section_dict,
                fact_sheet=fs,
                kb=kb,
                rag_top_k=3,
                prev_tail=None,
                next_summary=None,
            )
            sec.content = new_sec["content"]
            sec.rag_context = new_sec.get("rag_context", "")
            await s.commit()
        return {
            "section_id": sec.id,
            "new_content": new_sec["content"],
            "rag_hits": len(new_sec.get("rag_hits", [])),
            "locked": bool(sec.is_locked),
        }

    async def _lock_section(doc_id: int, section_index: int, lock: bool = True):
        from sqlalchemy import select

        from plugins.ddw_bid_writer.models import BidSection

        async with session_scope() as s, bypass_tenant_filter():
            sec = (
                await s.execute(
                    select(BidSection).where(
                        BidSection.bid_document_id == doc_id,
                        BidSection.section_index == section_index,
                    )
                )
            ).scalar_one_or_none()
            if sec is None:
                raise HTTPException(status_code=404, detail="section not found")
            sec.is_locked = 1 if lock else 0
            await s.commit()
        return {"section_id": sec.id, "is_locked": sec.is_locked}

    # ----------- 路由注册 ----------- #

    router.add_api_route("/projects", _create_project, methods=["POST"])
    router.add_api_route("/projects", _list_projects, methods=["GET"])
    router.add_api_route("/projects/{project_id}", _get_project, methods=["GET"])
    router.add_api_route("/projects/{project_id}", _update_project, methods=["PUT"])
    router.add_api_route("/projects/{project_id}", _delete_project, methods=["DELETE"])
    router.add_api_route("/projects/{project_id}/generate", _generate, methods=["POST"])
    router.add_api_route("/projects/{project_id}/documents", _list_documents, methods=["GET"])

    router.add_api_route("/documents/{doc_id}", _get_document, methods=["GET"])
    router.add_api_route("/documents/{doc_id}", _update_document, methods=["PUT"])
    router.add_api_route("/documents/{doc_id}/refine", _refine, methods=["POST"])
    router.add_api_route("/documents/{doc_id}/review", _review, methods=["POST"])
    router.add_api_route("/documents/{doc_id}/approve", _approve, methods=["POST"])

    router.add_api_route("/templates", _list_templates, methods=["GET"])
    router.add_api_route("/templates", _create_template, methods=["POST"])
    router.add_api_route("/templates/{template_id}", _update_template, methods=["PUT"])
    router.add_api_route("/templates/{template_id}", _delete_template, methods=["DELETE"])

    # ----------- C+D+E+F 新增路由 ----------- #

    router.add_api_route("/knowledge/bootstrap", _kb_bootstrap_endpoint, methods=["POST"])
    router.add_api_route("/knowledge/status", _kb_status, methods=["GET"])
    router.add_api_route("/knowledge/templates", _kb_templates, methods=["GET"])

    router.add_api_route(
        "/projects/{project_id}/assess-importance", _assess_importance, methods=["POST"]
    )
    router.add_api_route("/projects/{project_id}/plan", _plan, methods=["POST"])

    router.add_api_route("/documents/{doc_id}/sections", _list_sections, methods=["GET"])
    router.add_api_route(
        "/documents/{doc_id}/sections/{section_index}/regenerate",
        _regenerate_section,
        methods=["POST"],
    )
    router.add_api_route(
        "/documents/{doc_id}/sections/{section_index}/lock",
        lambda doc_id, section_index: _lock_section(doc_id, section_index, lock=True),
        methods=["POST"],
    )
    router.add_api_route(
        "/documents/{doc_id}/sections/{section_index}/unlock",
        lambda doc_id, section_index: _lock_section(doc_id, section_index, lock=False),
        methods=["POST"],
    )

    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-bid-writer", "version": "0.1.0", "status": "ok"}

    return router


__all__ = ["build_router"]
