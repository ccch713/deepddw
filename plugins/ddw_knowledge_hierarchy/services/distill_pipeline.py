"""Methodology distill pipeline — RIA-TV++ five-extraction + triple-verify + RIA++ construct.

Orchestrates the full distillation process for a document.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KhDistillJob, KhMethodologyUnit
from .distill_llm import call_llm, call_llm_json, call_llm_json_array
from .distill_prompts import (
    LIGHT_SUMMARY_PROMPT,
    LIGHT_SUMMARY_SYSTEM,
    construct_ria_prompt,
    extract_case_prompt,
    extract_counter_example_prompt,
    extract_framework_prompt,
    extract_glossary_prompt,
    extract_principle_prompt,
    verify_unit_prompt,
)
from .distill_quality import check_quality

logger = logging.getLogger(__name__)

# Extraction type mapping
EXTRACT_TYPES = {
    "framework": extract_framework_prompt,
    "principle": extract_principle_prompt,
    "case": extract_case_prompt,
    "counter_example": extract_counter_example_prompt,
    "glossary": extract_glossary_prompt,
}


async def get_document_content(db: AsyncSession, document_id: str) -> Optional[str]:
    """Get document content from chunks.

    支持两种文档体系：
    1. document_id 直接是 kh_documents.id（router.py /documents/upload 体系）
    2. document_id 是 kh_kb_documents.id（kb_router.py /kb/{id}/documents 体系）——
       通过 KBDocument.content_ref 映射到 kh_documents.id
    """
    from ..models import DocumentChunk, KBDocument

    # 先尝试直接按 document_id 查 chunks
    stmt = (
        select(DocumentChunk.content)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = (await db.execute(stmt)).scalars().all()
    if chunks:
        return "\n\n".join(chunks)

    # 再尝试通过 KBDocument.content_ref 映射（kb_router 上传体系）
    if document_id.isdigit():
        kb_doc = (
            await db.execute(
                select(KBDocument).where(KBDocument.id == int(document_id))
            )
        ).scalar_one_or_none()
        if kb_doc is not None and kb_doc.content_ref:
            stmt2 = (
                select(DocumentChunk.content)
                .where(DocumentChunk.document_id == kb_doc.content_ref)
                .order_by(DocumentChunk.chunk_index)
            )
            chunks2 = (await db.execute(stmt2)).scalars().all()
            if chunks2:
                return "\n\n".join(chunks2)

    return None


async def update_job_status(
    db: AsyncSession,
    job: KhDistillJob,
    status: str,
    progress: float,
    error: Optional[str] = None,
) -> None:
    """Update job status and progress."""
    job.status = status
    job.progress = progress
    if error:
        job.error = error
    if status == "completed":
        job.completed_at = datetime.utcnow()
    await db.flush()


async def extract_candidates(
    db: AsyncSession,
    job: KhDistillJob,
    document_content: str,
    strict_mode: bool,
) -> list[dict]:
    """Phase 1: Extract five types of candidate units."""
    candidates = []
    total_types = len(EXTRACT_TYPES)

    for idx, (unit_type, prompt_fn) in enumerate(EXTRACT_TYPES.items()):
        # Update progress: extracting phase (0-50%)
        progress = (idx / total_types) * 50
        await update_job_status(db, job, "extracting", progress)

        prompt = prompt_fn(document_content)
        result = await call_llm_json_array(prompt)

        if result:
            for item in result:
                candidates.append({
                    "unit_type": unit_type,
                    "title": item.get("title", ""),
                    "original_text": item.get("original_text", ""),
                    "source_chapter": item.get("source_chapter", ""),
                })
            logger.info(
                "distill: Extracted %d %s candidates",
                len(result), unit_type,
            )

    return candidates


async def verify_candidates(
    db: AsyncSession,
    job: KhDistillJob,
    candidates: list[dict],
    document_content: str,
    strict_mode: bool,
) -> list[dict]:
    """Phase 1.5: Triple verification of candidates."""
    verified = []
    rejected = []
    total = len(candidates)

    for idx, candidate in enumerate(candidates):
        # Update progress: verifying phase (50-75%)
        progress = 50 + (idx / max(total, 1)) * 25
        await update_job_status(db, job, "verifying", progress)

        prompt = verify_unit_prompt(
            unit_title=candidate["title"],
            unit_type=candidate["unit_type"],
            original_text=candidate["original_text"],
            document_content=document_content,
            strict_mode=strict_mode,
        )
        result = await call_llm_json(prompt)

        if result:
            candidate["v1_passed"] = result.get("v1_passed", False)
            candidate["v2_passed"] = result.get("v2_passed", False)
            candidate["v3_passed"] = result.get("v3_passed", False)
            candidate["status"] = result.get("overall", "rejected")
            candidate["reject_reason"] = result.get("reject_reason", "")

            if candidate["status"] == "verified":
                verified.append(candidate)
            else:
                rejected.append(candidate)

    logger.info(
        "distill: Verification complete — %d verified, %d rejected",
        len(verified), len(rejected),
    )
    return verified + rejected


async def construct_ria_units(
    db: AsyncSession,
    job: KhDistillJob,
    verified_candidates: list[dict],
    document_content: str,
) -> list[dict]:
    """Phase 2: Construct RIA++ six-section for verified units."""
    constructed = []
    total = len(verified_candidates)

    for idx, candidate in enumerate(verified_candidates):
        if candidate.get("status") != "verified":
            continue

        # Update progress: constructing phase (75-95%)
        progress = 75 + (idx / max(total, 1)) * 20
        await update_job_status(db, job, "constructing", progress)

        prompt = construct_ria_prompt(
            unit_title=candidate["title"],
            unit_type=candidate["unit_type"],
            original_text=candidate["original_text"],
            document_content=document_content,
        )
        result = await call_llm_json(prompt)

        if result:
            # Validate six sections completeness
            required_sections = ["r_section", "i_section", "a1_section", "trigger_words", "e_section", "b_section"]
            missing = [s for s in required_sections if not result.get(s)]

            if missing:
                # Retry once for missing sections
                logger.warning(
                    "distill: Missing sections %s for '%s', retrying...",
                    missing, candidate["title"],
                )
                result = await call_llm_json(prompt)

            if result and all(result.get(s) for s in required_sections):
                candidate.update(result)
                constructed.append(candidate)

    return constructed


async def save_units(
    db: AsyncSession,
    job: KhDistillJob,
    candidates: list[dict],
) -> list[KhMethodologyUnit]:
    """Phase 3: Save methodology units to database."""
    units = []

    for candidate in candidates:
        unit = KhMethodologyUnit(
            tenant_id=job.tenant_id,
            distill_job_id=job.id,
            document_id=job.document_id,
            unit_type=candidate.get("unit_type", "framework"),
            title=candidate.get("title", ""),
            trigger_words=candidate.get("trigger_words"),
            r_section=candidate.get("r_section"),
            i_section=candidate.get("i_section"),
            a1_section=candidate.get("a1_section"),
            e_section=candidate.get("e_section"),
            b_section=candidate.get("b_section"),
            v1_passed=candidate.get("v1_passed", False),
            v2_passed=candidate.get("v2_passed", False),
            v3_passed=candidate.get("v3_passed", False),
            status=candidate.get("status", "verified"),
            reject_reason=candidate.get("reject_reason"),
            source_chapter=candidate.get("source_chapter"),
        )
        db.add(unit)
        units.append(unit)

    await db.flush()
    return units


async def distill_light(
    db: AsyncSession,
    job: KhDistillJob,
) -> list[dict]:
    """Light mode: 快速摘要蒸馏（< 30s）。"""
    content = await get_document_content(db, job.document_id)
    if not content:
        return []

    await update_job_status(db, job, "extracting", 30)

    prompt = LIGHT_SUMMARY_PROMPT.format(
        title=job.document_id,
        content=content[:5000],
    )
    result = await call_llm_json(prompt, system=LIGHT_SUMMARY_SYSTEM)

    if not result:
        return []

    await update_job_status(db, job, "constructing", 70)

    # 转为轻量 MethodologyUnit
    unit = {
        "unit_type": result.get("unit_type", "summary"),
        "title": result.get("title", job.document_id),
        "r_section": result.get("summary", ""),
        "i_section": "\n".join(result.get("key_points", [])),
        "a1_section": ", ".join(result.get("applicable_scenarios", [])),
        "trigger_words": ", ".join(result.get("tags", [])),
        "e_section": "",
        "b_section": "",
        "v1_passed": True,
        "v2_passed": True,
        "v3_passed": True,
        "status": "verified",
    }
    return [unit]


async def distill_full(
    db: AsyncSession,
    job: KhDistillJob,
    strict_mode: bool = True,
) -> list[dict]:
    """Full mode: 完整 RIA-TV++ 蒸馏。"""
    content = await get_document_content(db, job.document_id)
    if not content:
        return []

    candidates = await extract_candidates(db, job, content, strict_mode)
    if not candidates:
        return []

    all_candidates = await verify_candidates(db, job, candidates, content, strict_mode)
    await construct_ria_units(db, job, all_candidates, content)
    return [c for c in all_candidates if c.get("status") == "verified"]


async def distill_hybrid(
    db: AsyncSession,
    job: KhDistillJob,
) -> list[dict]:
    """Hybrid mode: 先轻量，质量达标的再深度。"""
    # Phase 1: Light
    light_units = await distill_light(db, job)
    if not light_units:
        return []

    # Phase 2: Quality check on light results
    content = await get_document_content(db, job.document_id) or ""
    qualified = []
    for unit in light_units:
        qc = await check_quality(unit, content, min_score=70.0)
        unit["quality_score"] = qc["overall_score"]
        if qc["pass"]:
            qualified.append(unit)

    if not qualified:
        return light_units  # 保留 light 结果

    # Phase 3: Upgrade qualified units to full RIA++
    await update_job_status(db, job, "constructing", 60)
    full_units = []
    for unit in qualified:
        prompt = construct_ria_prompt(
            unit_title=unit["title"],
            unit_type=unit["unit_type"],
            original_text=unit.get("r_section", ""),
            document_content=content,
        )
        result = await call_llm_json(prompt)
        if result and all(result.get(s) for s in ["r_section", "i_section", "a1_section", "e_section", "b_section"]):
            unit.update(result)
            unit["status"] = "verified"
            full_units.append(unit)
        else:
            full_units.append(unit)  # 保留 light 版本

    return full_units


async def distill_document(
    db: AsyncSession,
    job: KhDistillJob,
    strict_mode: bool = True,
    mode: str = "full",
) -> None:
    """Main distillation pipeline. Supports full/light/hybrid modes."""
    try:
        if mode == "light":
            candidates = await distill_light(db, job)
        elif mode == "hybrid":
            candidates = await distill_hybrid(db, job)
        else:
            candidates = await distill_full(db, job, strict_mode)

        if not candidates:
            await update_job_status(db, job, "failed", 0, "未能提取到任何方法论单元")
            return

        # Quality gate
        content = await get_document_content(db, job.document_id) or ""
        min_score = 60.0 if mode == "light" else 75.0
        for candidate in candidates:
            if not candidate.get("quality_score"):
                qc = await check_quality(candidate, content, min_score=min_score)
                candidate["quality_score"] = qc["overall_score"]
                if not qc["pass"]:
                    candidate["status"] = "quality_rejected"

        # Save
        await update_job_status(db, job, "constructing", 95)
        units = await save_units(db, job, candidates)

        await update_job_status(db, job, "completed", 100)
        logger.info(
            "distill: Job %s completed (mode=%s) — %d units saved",
            job.id, mode, len(units),
        )

    except Exception as exc:
        logger.exception("distill: Pipeline failed for job %s", job.id)
        await update_job_status(db, job, "failed", job.progress, str(exc))
