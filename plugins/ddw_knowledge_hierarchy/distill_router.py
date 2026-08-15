"""Methodology Distill Engine API Router.

Endpoints (TASK_SPEC E.3):
- POST /distill/methodology/start — 启动方法论蒸馏任务
- GET  /distill/methodology/{job_id} — 查询蒸馏进度
- GET  /distill/methodology/{job_id}/units — 获取方法论单元列表
- GET  /distill/methodology/units/{unit_id} — 单元详情（RIA++ 六段全文）
- POST /distill/methodology/units/{unit_id}/reject — 人工驳回单元
- GET  /distill/methodology/units?status=rejected — 被淘汰单元
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .acl import Principal
from .deps import get_principal
from .models import KBDocument, KhDistillJob, KhMethodologyUnit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Methodology Distill"])


# ─── Request / Response schemas ───


class DistillStartRequest(BaseModel):
    knowledge_base_id: int
    document_id: str
    strict_mode: bool = True
    mode: str = "full"  # full | light | hybrid
    auto_export_to_memory: bool = False
    target_memory_layer: str = "department"


class DistillStartResponse(BaseModel):
    job_id: str
    status: str
    document_id: str
    knowledge_base_id: int
    estimated_steps: int = 4


class DistillProgressResponse(BaseModel):
    job_id: str
    status: str
    progress: float
    phase_detail: str = ""
    units_count: int = 0
    verified_count: int = 0
    rejected_count: int = 0


class MethodologyUnitBrief(BaseModel):
    id: str
    unit_type: str
    title: str
    trigger_words: str | None = None
    v1_passed: bool = False
    v2_passed: bool = False
    v3_passed: bool = False
    status: str = "verified"


class MethodologyUnitDetail(MethodologyUnitBrief):
    r_section: str | None = None
    i_section: str | None = None
    a1_section: str | None = None
    e_section: str | None = None
    b_section: str | None = None
    reject_reason: str | None = None
    source_chapter: str | None = None
    created_at: str = ""


class UnitListResponse(BaseModel):
    items: list[MethodologyUnitBrief]
    total: int


# ─── Helpers ───


def _unit_to_brief(unit: KhMethodologyUnit) -> MethodologyUnitBrief:
    return MethodologyUnitBrief(
        id=unit.id,
        unit_type=unit.unit_type,
        title=unit.title,
        trigger_words=unit.trigger_words,
        v1_passed=unit.v1_passed,
        v2_passed=unit.v2_passed,
        v3_passed=unit.v3_passed,
        status=unit.status,
    )


def _unit_to_detail(unit: KhMethodologyUnit) -> MethodologyUnitDetail:
    return MethodologyUnitDetail(
        id=unit.id,
        unit_type=unit.unit_type,
        title=unit.title,
        trigger_words=unit.trigger_words,
        v1_passed=unit.v1_passed,
        v2_passed=unit.v2_passed,
        v3_passed=unit.v3_passed,
        status=unit.status,
        r_section=unit.r_section,
        i_section=unit.i_section,
        a1_section=unit.a1_section,
        e_section=unit.e_section,
        b_section=unit.b_section,
        reject_reason=unit.reject_reason,
        source_chapter=unit.source_chapter,
        created_at=unit.created_at.isoformat() if unit.created_at else "",
    )


async def _get_job_with_acl(
    s, job_id: str, principal: Principal
) -> KhDistillJob:
    """Fetch a distill job and verify tenant isolation."""
    job = (
        await s.execute(
            select(KhDistillJob).where(KhDistillJob.id == job_id)
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "蒸馏任务不存在")
    if job.tenant_id != principal.tenant_id:
        raise HTTPException(403, "无权访问此蒸馏任务")
    return job


async def _get_unit_with_acl(
    s, unit_id: str, principal: Principal
) -> KhMethodologyUnit:
    """Fetch a methodology unit and verify tenant isolation."""
    unit = (
        await s.execute(
            select(KhMethodologyUnit).where(KhMethodologyUnit.id == unit_id)
        )
    ).scalar_one_or_none()
    if unit is None:
        raise HTTPException(404, "方法论单元不存在")
    if unit.tenant_id != principal.tenant_id:
        raise HTTPException(403, "无权访问此方法论单元")
    return unit


async def _run_distill_pipeline(job_id: str, strict_mode: bool, mode: str = "full", auto_export: bool = False, target_layer: str = "department") -> None:
    """Run distill pipeline in background."""
    from .services.distill_pipeline import distill_document

    try:
        async with session_scope() as s, bypass_tenant_filter():
            job = (
                await s.execute(
                    select(KhDistillJob).where(KhDistillJob.id == job_id)
                )
            ).scalar_one_or_none()
            if job is None:
                logger.error("distill: Job %s not found", job_id)
                return
            await distill_document(s, job, strict_mode, mode=mode)
            await s.commit()
    except Exception:
        logger.exception("distill: Background pipeline failed for job %s", job_id)


# ─── Endpoints ───


@router.post("/distill/methodology/start", response_model=DistillStartResponse, status_code=201)
async def start_distill(
    req: DistillStartRequest,
    principal: Principal = Depends(get_principal),
):
    """启动方法论蒸馏任务。"""
    async with session_scope() as s, bypass_tenant_filter():
        # Verify document exists and belongs to the KB
        doc = (
            await s.execute(
                select(KBDocument).where(
                    KBDocument.id == req.document_id,
                    KBDocument.kb_id == req.knowledge_base_id,
                    KBDocument.tenant_id == principal.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if doc is None:
            raise HTTPException(404, "文档不存在或不属于此知识库")

        # Create distill job
        job = KhDistillJob(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            knowledge_base_id=req.knowledge_base_id,
            document_id=req.document_id,
            status="queued",
            progress=0.0,
        )
        s.add(job)
        await s.flush()
        job_id = job.id
        await s.commit()

    # Run pipeline in background
    asyncio.create_task(_run_distill_pipeline(job_id, req.strict_mode, mode=req.mode, auto_export=req.auto_export_to_memory, target_layer=req.target_memory_layer))

    return DistillStartResponse(
        job_id=job_id,
        status="queued",
        document_id=req.document_id,
        knowledge_base_id=req.knowledge_base_id,
        estimated_steps=4,
    )


@router.get("/distill/methodology/{job_id}", response_model=DistillProgressResponse)
async def get_distill_progress(
    job_id: str,
    principal: Principal = Depends(get_principal),
):
    """查询蒸馏进度。"""
    async with session_scope() as s, bypass_tenant_filter():
        job = await _get_job_with_acl(s, job_id, principal)

        # Get unit counts
        units_stmt = select(KhMethodologyUnit).where(
            KhMethodologyUnit.distill_job_id == job_id
        )
        units = (await s.execute(units_stmt)).scalars().all()

        verified_count = sum(1 for u in units if u.status == "verified")
        rejected_count = sum(1 for u in units if u.status == "rejected")

        # Build phase detail
        phase_detail = ""
        if job.status == "extracting":
            phase_detail = "五类提取中"
        elif job.status == "verifying":
            phase_detail = "三重验证中"
        elif job.status == "constructing":
            phase_detail = "RIA++ 构造中"
        elif job.status == "completed":
            phase_detail = f"完成 — {verified_count} 个方法论单元"

        return DistillProgressResponse(
            job_id=job.id,
            status=job.status,
            progress=job.progress,
            phase_detail=phase_detail,
            units_count=len(units),
            verified_count=verified_count,
            rejected_count=rejected_count,
        )


@router.get("/distill/methodology/{job_id}/units", response_model=UnitListResponse)
async def list_distill_units(
    job_id: str,
    status: str | None = Query(None, description="Filter by status: verified|rejected"),
    principal: Principal = Depends(get_principal),
):
    """获取方法论单元列表。"""
    async with session_scope() as s, bypass_tenant_filter():
        # ACL check (side effect: raises 403/404 if unauthorized)
        await _get_job_with_acl(s, job_id, principal)

        stmt = select(KhMethodologyUnit).where(
            KhMethodologyUnit.distill_job_id == job_id
        )
        if status:
            stmt = stmt.where(KhMethodologyUnit.status == status)

        units = (await s.execute(stmt)).scalars().all()
        return UnitListResponse(
            items=[_unit_to_brief(u) for u in units],
            total=len(units),
        )


@router.get("/distill/methodology/units/{unit_id}", response_model=MethodologyUnitDetail)
async def get_unit_detail(
    unit_id: str,
    principal: Principal = Depends(get_principal),
):
    """单元详情（RIA++ 六段全文）。"""
    async with session_scope() as s, bypass_tenant_filter():
        unit = await _get_unit_with_acl(s, unit_id, principal)
        return _unit_to_detail(unit)


@router.post("/distill/methodology/units/{unit_id}/reject")
async def reject_unit(
    unit_id: str,
    principal: Principal = Depends(get_principal),
):
    """人工驳回单元（可捞回）。"""
    async with session_scope() as s, bypass_tenant_filter():
        unit = await _get_unit_with_acl(s, unit_id, principal)
        unit.status = "rejected"
        unit.reject_reason = unit.reject_reason or "人工驳回"
        await s.commit()
        return {"id": unit.id, "status": "rejected"}


@router.get("/distill/methodology/units")
async def list_rejected_units(
    status: str = Query("rejected", description="Filter by status"),
    principal: Principal = Depends(get_principal),
):
    """被淘汰单元（含原因，支持捞回）。"""
    async with session_scope() as s, bypass_tenant_filter():
        stmt = (
            select(KhMethodologyUnit)
            .where(
                KhMethodologyUnit.tenant_id == principal.tenant_id,
                KhMethodologyUnit.status == status,
            )
            .order_by(KhMethodologyUnit.created_at.desc())
        )
        units = (await s.execute(stmt)).scalars().all()
        return {
            "items": [_unit_to_detail(u).model_dump() for u in units],
            "total": len(units),
        }


# ─── 批量蒸馏 ───


class DistillBatchRequest(BaseModel):
    document_ids: list[str]
    knowledge_base_id: int
    mode: str = "hybrid"
    strict_mode: bool = True
    auto_export_to_memory: bool = False
    target_memory_layer: str = "department"


@router.post("/distill/batch", status_code=201)
async def batch_distill(
    req: DistillBatchRequest,
    principal: Principal = Depends(get_principal),
):
    """批量蒸馏。"""
    job_ids = []
    async with session_scope() as s, bypass_tenant_filter():
        for doc_id in req.document_ids:
            job = KhDistillJob(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                knowledge_base_id=req.knowledge_base_id,
                document_id=doc_id,
                status="queued",
                progress=0.0,
            )
            s.add(job)
            await s.flush()
            job_ids.append(job.id)
            asyncio.create_task(_run_distill_pipeline(job.id, req.strict_mode, mode=req.mode))
        await s.commit()

    return {"job_ids": job_ids, "total": len(job_ids), "status": "queued"}


# ─── 导出到记忆引擎 ───


class DistillExportRequest(BaseModel):
    job_id: str
    target_layer: str = "department"
    department_id: int | None = None
    position_id: int | None = None
    filter_min_quality: float = 60.0


@router.post("/distill/export", status_code=200)
async def export_to_memory(
    req: DistillExportRequest,
    principal: Principal = Depends(get_principal),
):
    """导出蒸馏结果到记忆引擎。"""
    from .services.distill_memory_export import export_distill_to_memory

    async with session_scope() as s, bypass_tenant_filter():
        _job = await _get_job_with_acl(s, req.job_id, principal)

        # 获取 job 的所有 verified 单元
        stmt = select(KhMethodologyUnit).where(
            KhMethodologyUnit.distill_job_id == req.job_id,
            KhMethodologyUnit.status == "verified",
        )
        units = (await s.execute(stmt)).scalars().all()

        unit_dicts = [
            {
                "id": u.id,
                "title": u.title,
                "unit_type": u.unit_type,
                "r_section": u.r_section or "",
                "a1_section": u.a1_section or "",
                "quality_score": getattr(u, "quality_score", None),
            }
            for u in units
        ]

    # 调用导出
    async def _create_memory(**kwargs):
        from plugins.ddw_memory.service import MemoryService
        svc = MemoryService()
        return (await svc.create_memory(tenant_id=principal.tenant_id, creator_id=principal.user_id, **kwargs)).model_dump(mode="json")

    result = await export_distill_to_memory(
        units=unit_dicts,
        target_layer=req.target_layer,
        department_id=req.department_id,
        position_id=req.position_id,
        create_memory_fn=_create_memory,
        filter_min_quality=req.filter_min_quality,
    )

    return result


# ─── 用户反馈 ───


class DistillFeedbackRequest(BaseModel):
    unit_id: str
    rating: int  # 1-5
    feedback_text: str | None = None
    is_useful: bool = True


@router.post("/distill/feedback")
async def submit_feedback(
    req: DistillFeedbackRequest,
    principal: Principal = Depends(get_principal),
):
    """提交蒸馏结果反馈。"""
    async with session_scope() as s, bypass_tenant_filter():
        unit = await _get_unit_with_acl(s, req.unit_id, principal)
        # 在 unit 上记录反馈（用 reject_reason 字段暂存，或加新字段）
        if not req.is_useful:
            unit.status = "rejected"
            unit.reject_reason = f"用户反馈: rating={req.rating}, {req.feedback_text or ''}"
        await s.commit()
        return {"unit_id": req.unit_id, "rating": req.rating, "recorded": True}


# ─── 队列状态 ───


@router.get("/distill/queue/status")
async def queue_status(
    principal: Principal = Depends(get_principal),
):
    """队列状态。"""
    async with session_scope() as s, bypass_tenant_filter():
        from sqlalchemy import func as sqlfunc
        stmt = (
            select(KhDistillJob.status, sqlfunc.count())
            .where(KhDistillJob.tenant_id == principal.tenant_id)
            .group_by(KhDistillJob.status)
        )
        rows = (await s.execute(stmt)).all()
        status_map = {row[0]: row[1] for row in rows}
        return {
            "pending": status_map.get("queued", 0),
            "running": status_map.get("extracting", 0) + status_map.get("verifying", 0) + status_map.get("constructing", 0),
            "completed": status_map.get("completed", 0),
            "failed": status_map.get("failed", 0),
            "total": sum(status_map.values()),
        }
