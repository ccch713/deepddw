"""DDW Talk A1 ASR - FastAPI router.

端点：
    POST /upload              上传音频文件，异步转写
    GET  /status/{job_id}     查询任务状态
    GET  /jobs                列出所有任务（按状态过滤）
    GET  /health              健康检查
    GET  /config              查看运行时配置（脱敏）
"""
from __future__ import annotations

import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import PLUGIN_NAME, VERSION, config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plugins/ddw_talk_a1_asr", tags=["ddw_talk_a1_asr"])

# 由 plugin.py 在 initialize 阶段注入
_store: Any = None
_plugin: Any = None


def set_store(store: Any) -> None:
    global _store
    _store = store


def set_plugin(plugin: Any) -> None:
    global _plugin
    _plugin = plugin


# === Response Models ===

class HealthResponse(BaseModel):
    plugin: str = "ddw_talk_a1_asr"
    version: str = "0.1.0"
    status: str = "ok"
    whisper_model: str
    queue_size: int
    total_jobs: int


class UploadResponse(BaseModel):
    job_id: str
    status: str = "queued"
    message: str = "音频已接收，正在转写中"
    audio_path: str
    doctor_id: Optional[str] = None
    patient_name: Optional[str] = None
    session_type: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: float = 0.0
    full_text: Optional[str] = None
    segments: list[dict[str, Any]] = Field(default_factory=list)
    duration_seconds: Optional[float] = None
    output_path: Optional[str] = None
    error: Optional[str] = None
    doctor_id: Optional[str] = None
    patient_name: Optional[str] = None
    session_type: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class JobListResponse(BaseModel):
    total: int
    jobs: list[JobStatusResponse]


# === Helpers ===

def _ensure_ready() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


def _validate_audio(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    ext = Path(file.filename).suffix.lower()
    if ext not in config.ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported audio format: {ext}. allowed: {sorted(config.ALLOWED_AUDIO_EXTENSIONS)}",
        )
    return ext


def _save_upload(file: UploadFile, doctor_id: Optional[str]) -> tuple[str, Path]:
    """落盘上传的音频文件，返回 (job_id, audio_path)."""
    ext = _validate_audio(file)
    config.QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:8]
    prefix = f"{doctor_id}_" if doctor_id else ""
    target = config.QUEUE_DIR / f"{prefix}{job_id}{ext}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return job_id, target


# === Endpoints ===

@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    queue_size = _store.queue_size() if _store else 0
    total = _store.total_count() if _store else 0
    return HealthResponse(
        whisper_model=config.WHISPER_MODEL,
        queue_size=queue_size,
        total_jobs=total,
    )


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload(
    file: UploadFile = File(..., description="音频文件 (wav/mp3/m4a/m4b/ogg/flac)"),  # noqa: B008
    doctor_id: Optional[str] = Form(None, description="医生 ID，如 doc_001"),
    patient_name: Optional[str] = Form(None, description="患者姓名（标识用）"),
    session_type: Optional[str] = Form("consultation", description="consultation/follow_up/emergency"),
) -> UploadResponse:
    """上传音频并触发异步转写。返回 job_id，调用 /status/{job_id} 查进度."""
    _ensure_ready()
    if session_type and session_type not in config.SESSION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid session_type: {session_type}. allowed: {config.SESSION_TYPES}",
        )

    job_id, audio_path = _save_upload(file, doctor_id)

    # 大小校验
    size = audio_path.stat().st_size
    if size > config.MAX_AUDIO_BYTES:
        audio_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=f"file too large: {size} bytes > {config.MAX_AUDIO_BYTES}",
        )

    _store.create_job(
        job_id=job_id,
        audio_path=str(audio_path),
        doctor_id=doctor_id,
        patient_name=patient_name,
        session_type=session_type,
    )

    if _plugin is not None and hasattr(_plugin, "submit_job"):
        _plugin.submit_job(
            job_id=job_id,
            audio_path=str(audio_path),
            doctor_id=doctor_id,
            patient_name=patient_name,
            session_type=session_type,
        )
    else:
        # 没有 plugin 实例（例如在裸 FastAPI 测试中）：同步转写兜底
        from .transcriber import TranscriptionError, transcribe_audio

        try:
            result = transcribe_audio(str(audio_path))
            _store.save_result(
                job_id=job_id,
                full_text=result.full_text,
                segments=result.segments,
                duration_seconds=result.duration_seconds,
                language=result.language,
                model=result.model,
            )
        except (TranscriptionError, FileNotFoundError, RuntimeError) as e:
            _store.update_status(job_id, "failed", error=str(e))

    return UploadResponse(
        job_id=job_id,
        status="queued",
        audio_path=str(audio_path),
        doctor_id=doctor_id,
        patient_name=patient_name,
        session_type=session_type,
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_status(job_id: str) -> JobStatusResponse:
    _ensure_ready()
    job = _store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    if job["status"] == "transcribing" and not job.get("full_text"):
        # 没有具体进度信息时返回兜底值
        job.setdefault("progress", config.PROGRESS_TRANSIENT)
    return JobStatusResponse(**job)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = None,
    limit: int = 50,
) -> JobListResponse:
    _ensure_ready()
    if status and status not in config.JOB_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid status: {status}. allowed: {config.JOB_STATUSES}",
        )
    jobs = _store.list_by_status(status)
    if limit and len(jobs) > limit:
        jobs = jobs[-limit:]
    return JobListResponse(total=len(jobs), jobs=[JobStatusResponse(**j) for j in jobs])


@router.get("/config")
async def get_config() -> dict[str, Any]:
    """返回运行时配置（脱敏），便于运维诊断."""
    return {
        "plugin": PLUGIN_NAME,
        "version": VERSION,
        "whisper_model": config.WHISPER_MODEL,
        "whisper_model_dir": str(config.WHISPER_MODEL_DIR),
        "whisper_cli": config.WHISPER_CLI,
        "audio_sample_rate": config.AUDIO_SAMPLE_RATE,
        "audio_channels": config.AUDIO_CHANNELS,
        "max_concurrent_jobs": config.MAX_CONCURRENT_JOBS,
        "max_audio_bytes": config.MAX_AUDIO_BYTES,
        "allowed_extensions": sorted(config.ALLOWED_AUDIO_EXTENSIONS),
        "queue_dir": str(config.QUEUE_DIR),
        "output_dir": str(config.OUTPUT_DIR),
        "db_path": str(config.DB_PATH),
        "session_types": list(config.SESSION_TYPES),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
