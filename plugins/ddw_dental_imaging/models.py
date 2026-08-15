"""DDW Dental Imaging - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

IMAGE_TYPES = ("intraoral", "xray", "cbct", "panoramic", "photo")
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".dcm", ".tiff"}


class DentalImage(BaseModel):
    id: Optional[str] = None
    patient_id: str
    record_id: Optional[str] = None
    image_type: str
    file_path: str
    file_size: int = 0
    taken_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class ImageList(BaseModel):
    total: int
    images: list[DentalImage]


class TimelineResponse(BaseModel):
    patient_id: str
    total: int
    timeline: list[DentalImage]


class HealthResponse(BaseModel):
    plugin: str = "ddw_dental_imaging"
    version: str = "0.1.0"
    status: str = "ok"
    total_images: int = 0
