"""DDW Followup - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

FOLLOWUP_TYPES = ("postop_recall", "satisfaction", "birthday", "custom")
STATUSES = ("pending", "sent", "responded", "skipped")
CHANNELS = ("wechat", "sms", "phone")


class FollowupTask(BaseModel):
    id: Optional[str] = None
    patient_id: str
    doctor_id: Optional[str] = None
    record_id: Optional[str] = None
    followup_type: str
    due_date: str  # YYYY-MM-DD
    message_template: str
    status: str = "pending"
    channel: str = "wechat"
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None


class FollowupTaskCreate(BaseModel):
    patient_id: str
    doctor_id: Optional[str] = None
    record_id: Optional[str] = None
    followup_type: str
    due_date: str
    message_template: str
    channel: str = "wechat"


class FollowupTaskUpdate(BaseModel):
    status: Optional[str] = None
    sent_at: Optional[datetime] = None
    message_template: Optional[str] = None


class FollowupTemplate(BaseModel):
    id: Optional[str] = None
    name: str
    followup_type: str
    delay_days: int
    message_template: str
    is_active: bool = True


class FollowupTemplateCreate(BaseModel):
    name: str
    followup_type: str
    delay_days: int
    message_template: str


class TaskList(BaseModel):
    total: int
    tasks: list[FollowupTask]


class TemplateList(BaseModel):
    total: int
    templates: list[FollowupTemplate]


class StatsByType(BaseModel):
    count: int
    sent: int
    responded: int


class StatsResponse(BaseModel):
    period: str
    total_tasks: int
    sent: int
    responded: int
    response_rate: float
    by_type: dict[str, StatsByType]


class HealthResponse(BaseModel):
    plugin: str = "ddw_followup"
    version: str = "0.1.0"
    status: str = "ok"
    total_tasks: int = 0
