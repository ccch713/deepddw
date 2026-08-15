"""DDW Dental Imaging - FastAPI router."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from .models import (
    ALLOWED_EXT,
    IMAGE_TYPES,
    DentalImage,
    HealthResponse,
    ImageList,
    TimelineResponse,
)
from .store import ImageStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_dental_imaging", tags=["ddw_dental_imaging"]
)
_store: ImageStore | None = None


def set_store(s: ImageStore) -> None:
    global _store
    _store = s


def _ensure() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if _store is None:
        return HealthResponse()
    return HealthResponse(total_images=_store.total_count())


@router.post("/images", response_model=DentalImage, status_code=201)
async def upload_image(
    file: UploadFile = File(...),  # noqa: B008
    patient_id: str = Form(...),
    image_type: str = Form(...),
    record_id: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    taken_at: Optional[str] = Form(None),
) -> DentalImage:
    _ensure()
    if image_type not in IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid image_type: {image_type}")
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"unsupported extension: {ext}")
    # 落盘: root_dir/{patient_id}/{image_type}/{timestamp}_{filename}
    target_dir = _store.root_dir / patient_id / image_type
    target_dir.mkdir(parents=True, exist_ok=True)
    import uuid as _uuid
    target_path = target_dir / f"{_uuid.uuid4().hex[:8]}_{file.filename}"
    with target_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    payload = {
        "patient_id": patient_id,
        "record_id": record_id,
        "image_type": image_type,
        "file_path": str(target_path),
        "file_size": target_path.stat().st_size,
        "taken_at": taken_at,
        "notes": notes,
    }
    d = _store.create(payload)
    return DentalImage(**d)


@router.get("/images", response_model=ImageList)
async def list_images(
    patient_id: str, image_type: Optional[str] = None
) -> ImageList:
    _ensure()
    if image_type and image_type not in IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid image_type: {image_type}")
    rows = _store.list_for_patient(patient_id, image_type=image_type)
    return ImageList(total=len(rows), images=rows)


@router.get("/images/{image_id}", response_model=DentalImage)
async def get_image(image_id: str) -> DentalImage:
    _ensure()
    d = _store.get(image_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"image not found: {image_id}")
    return DentalImage(**d)


@router.delete("/images/{image_id}", status_code=204, response_class=Response)
async def delete_image(image_id: str) -> Response:
    _ensure()
    if not _store.delete(image_id):
        raise HTTPException(status_code=404, detail=f"image not found: {image_id}")
    return Response(status_code=204)


@router.get("/timeline", response_model=TimelineResponse)
async def timeline(patient_id: str) -> TimelineResponse:
    _ensure()
    rows = _store.timeline(patient_id)
    return TimelineResponse(patient_id=patient_id, total=len(rows), timeline=rows)
