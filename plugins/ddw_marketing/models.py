"""DDW Marketing - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

CAMPAIGN_STATUSES = ("draft", "scheduled", "sent")


class Campaign(BaseModel):
    id: Optional[str] = None
    name: str
    content: str
    target_tags: list[str] = Field(default_factory=list)
    target_levels: list[str] = Field(default_factory=list)
    channel: str = "wechat"
    status: str = "draft"
    scheduled_at: Optional[datetime] = None
    sent_count: int = 0
    click_count: int = 0
    created_at: Optional[datetime] = None


class CampaignCreate(BaseModel):
    name: str
    content: str
    target_tags: list[str] = Field(default_factory=list)
    target_levels: list[str] = Field(default_factory=list)
    channel: str = "wechat"
    scheduled_at: Optional[datetime] = None


class CampaignList(BaseModel):
    total: int
    campaigns: list[Campaign]


class CampaignStats(BaseModel):
    campaign_id: str
    sent: int
    click: int
    conversion_rate: float


class HealthResponse(BaseModel):
    plugin: str = "ddw_marketing"
    version: str = "0.1.0"
    status: str = "ok"
    total_campaigns: int = 0
