"""DDW Doctor Schedule - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

SLOT_TYPES = ("normal", "on_call", "off", "leave")
TITLES = ("住院医师", "主治医师", "副主任医师", "主任医师")


class Doctor(BaseModel):
    id: Optional[str] = None
    name: str
    title: Optional[str] = None
    specialty: list[str] = Field(default_factory=list)
    phone: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


class DoctorCreate(BaseModel):
    name: str
    title: Optional[str] = None
    specialty: list[str] = Field(default_factory=list)
    phone: Optional[str] = None


class DoctorUpdate(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    specialty: Optional[list[str]] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


class ScheduleSlot(BaseModel):
    id: Optional[str] = None
    doctor_id: str
    date: str                          # YYYY-MM-DD
    start_time: str                    # HH:MM
    end_time: str                      # HH:MM
    slot_type: str = "normal"
    max_patients: int = 10
    booked_count: int = 0
    created_at: Optional[datetime] = None


class ScheduleSlotCreate(BaseModel):
    doctor_id: str
    date: str
    start_time: str
    end_time: str
    slot_type: str = "normal"
    max_patients: int = 10


class ScheduleSlotUpdate(BaseModel):
    slot_type: Optional[str] = None
    max_patients: Optional[int] = None
    booked_count: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class DoctorList(BaseModel):
    total: int
    doctors: list[Doctor]


class SlotList(BaseModel):
    total: int
    slots: list[ScheduleSlot]


class HealthResponse(BaseModel):
    plugin: str = "ddw_doctor_schedule"
    version: str = "0.1.0"
    status: str = "ok"
    total_doctors: int = 0
    total_slots: int = 0
