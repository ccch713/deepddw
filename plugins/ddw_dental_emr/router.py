"""DDW Dental EMR - FastAPI router.

端点：
    POST   /records                        创建病历
    GET    /records/{id}                   获取单条
    GET    /records                         按 patient_id 过滤 + 分页
    PATCH  /records/{id}/status            更新状态
    POST   /from-transcript                从转写 job_id 一键生成病历草稿
    GET    /templates                       代理模板套件
    GET    /health                          健康检查
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from ddw_clinical_asr.schema import TREATMENT_VALUES
from ddw_dental_emr_template_kit import loader as tpl_loader
from fastapi import APIRouter, HTTPException

from . import PLUGIN_NAME
from .models import (
    DentalRecord,
    DentalRecordCreate,
    DentalRecordListResponse,
    FromTranscriptRequest,
    FromTranscriptResponse,
    HealthResponse,
    StatusUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_dental_emr", tags=["ddw_dental_emr"]
)

# 由 plugin.py 注入
_store: Any = None
_emr_data_dir: Path = Path(__file__).parent / "data"


def set_store(store: Any) -> None:
    global _store
    _store = store


def set_data_dir(d: Path) -> None:
    global _emr_data_dir
    _emr_data_dir = d


def _ensure_ready() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    total = _store.total_count() if _store else 0
    return HealthResponse(
        total_records=total,
        template_count=len(tpl_loader.list_templates()),
    )


@router.post("/records", response_model=DentalRecord, status_code=201)
async def create_record(req: DentalRecordCreate) -> DentalRecord:
    _ensure_ready()
    if req.treatment_type not in TREATMENT_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid treatment_type: {req.treatment_type}",
        )
    if not req.patient_id or not req.doctor_id:
        raise HTTPException(status_code=400, detail="patient_id / doctor_id 必填")
    record = _store.create(req.model_dump())
    return DentalRecord(**record)


@router.get("/records/{record_id}", response_model=DentalRecord)
async def get_record(record_id: str) -> DentalRecord:
    _ensure_ready()
    record = _store.get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"record not found: {record_id}")
    return DentalRecord(**record)


@router.get("/records", response_model=DentalRecordListResponse)
async def list_records(
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    treatment_type: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> DentalRecordListResponse:
    _ensure_ready()
    page = max(page, 1)
    if page_size < 1 or page_size > 200:
        page_size = 20
    if treatment_type and treatment_type not in TREATMENT_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid treatment_type: {treatment_type}",
        )
    if patient_id:
        data = _store.list_by_patient(patient_id, page, page_size)
    else:
        data = _store.list_all(
            doctor_id=doctor_id,
            treatment_type=treatment_type,
            status=status,
            page=page,
            page_size=page_size,
        )
    return DentalRecordListResponse(**data)


@router.patch("/records/{record_id}/status", response_model=DentalRecord)
async def update_status(record_id: str, req: StatusUpdate) -> DentalRecord:
    _ensure_ready()
    if req.status not in ("draft", "reviewed", "finalized"):
        raise HTTPException(
            status_code=400,
            detail=f"invalid status: {req.status}",
        )
    record = _store.update_status(record_id, req.status, req.notes)
    if record is None:
        raise HTTPException(status_code=404, detail=f"record not found: {record_id}")
    return DentalRecord(**record)


@router.post("/from-transcript", response_model=FromTranscriptResponse)
async def from_transcript(req: FromTranscriptRequest) -> FromTranscriptResponse:
    """从转写 job_id 一键生成病历草稿.

    流程：
    1. 读转写 JSON（如果不在则使用兜底 mock transcript）
    2. 调 LLM 抽取（mock 模式）
    3. 用模板做必填字段校验
    4. 落库为 draft
    """
    _ensure_ready()
    if not req.transcript_job_id or not req.patient_id or not req.doctor_id:
        raise HTTPException(
            status_code=400,
            detail="transcript_job_id / patient_id / doctor_id 必填",
        )

    # 1. 取转写文本
    transcript_text = _load_transcript_text(req.transcript_job_id)
    # 2. 抽取（直接调用 T1 内部函数）
    from ddw_clinical_asr import extractor as clinical_extractor

    try:
        result, _ = await clinical_extractor.extract_medical_entities(
            transcript=transcript_text,
            job_id=req.transcript_job_id,
            treatment_hint=req.treatment_hint,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抽取失败: {e}") from e

    # 3. 模板校验
    candidate = {
        "chief_complaint": result.get("chief_complaint", ""),
        "present_illness": result.get("present_illness", ""),
        "past_history": result.get("past_history", ""),
        **result.get("special_findings", {}),
        **result.get("examination", {}),
    }
    tt = result.get("treatment_type", "extraction")
    missing = tpl_loader.validate_required_fields(tt, candidate)
    validation = {
        "missing_fields": [m["field"] for m in missing],
        "warnings": [m["error"] for m in missing],
    }

    # 4. 落库
    record_payload = {
        "patient_id": req.patient_id,
        "doctor_id": req.doctor_id,
        "treatment_type": tt,
        "chief_complaint": result.get("chief_complaint", ""),
        "present_illness": result.get("present_illness", ""),
        "past_history": result.get("past_history", ""),
        "examination": result.get("examination", {}),
        "diagnosis": result.get("diagnosis", ""),
        "treatment_plan": result.get("treatment_plan", ""),
        "special_findings": result.get("special_findings", {}),
        "urgency": result.get("urgency", "routine"),
        "status": "draft",
        "transcript_job_id": req.transcript_job_id,
    }
    saved = _store.create(record_payload)
    return FromTranscriptResponse(
        record=DentalRecord(**saved),
        validation=validation,
    )


def _load_transcript_text(job_id: str) -> str:
    """从 T0 的 output 目录读转写 JSON；读不到就兜底 mock."""
    out_dir = Path(__file__).parent.parent / "ddw_talk_a1_asr" / "output"
    candidate = out_dir / f"{job_id}.json"
    if candidate.exists():
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            return data.get("full_text", "") or ""
        except (OSError, json.JSONDecodeError):
            pass
    # 兜底：mock 转写文本
    return (
        f"患者 {job_id} 主诉牙痛三天，夜间加重，冷热刺激痛。"
        "检查左下6深龋近髓，叩诊阳性。"
    )


@router.get("/templates")
async def list_templates() -> dict[str, Any]:
    """代理 T16 模板列表."""
    return {"plugin": PLUGIN_NAME, "templates": tpl_loader.list_templates()}
