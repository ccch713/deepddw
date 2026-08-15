"""DDW Marketing - FastAPI router."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .models import (
    Campaign,
    CampaignCreate,
    CampaignList,
    CampaignStats,
    HealthResponse,
)
from .store import CampaignStore
from .targeter import estimate_recipients

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_marketing", tags=["ddw_marketing"]
)
_store: CampaignStore | None = None


def set_store(s: CampaignStore) -> None:
    global _store
    _store = s


def _ensure() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if _store is None:
        return HealthResponse()
    return HealthResponse(total_campaigns=_store.total_count())


@router.post("/campaigns", response_model=Campaign, status_code=201)
async def create_campaign(req: CampaignCreate) -> Campaign:
    _ensure()
    if not req.name.strip() or not req.content.strip():
        raise HTTPException(status_code=400, detail="name / content 必填")
    d = _store.create(req.model_dump())
    return Campaign(**d)


@router.get("/campaigns", response_model=CampaignList)
async def list_campaigns() -> CampaignList:
    _ensure()
    items = _store.list_all()
    return CampaignList(total=len(items), campaigns=items)


@router.post("/campaigns/{campaign_id}/send", response_model=Campaign)
async def send_campaign(campaign_id: str) -> Campaign:
    _ensure()
    c = _store.get(campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"campaign not found: {campaign_id}")
    if c["status"] == "sent":
        raise HTTPException(status_code=400, detail="已发送")
    recipients = estimate_recipients(
        _store.db_path, c["target_tags"], c["target_levels"]
    )
    updated = _store.update(campaign_id, {"status": "sent", "sent_count": recipients})
    return Campaign(**updated)  # type: ignore[arg-type]


@router.get("/campaigns/{campaign_id}/stats", response_model=CampaignStats)
async def campaign_stats(campaign_id: str) -> CampaignStats:
    _ensure()
    c = _store.get(campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"campaign not found: {campaign_id}")
    sent = c["sent_count"]
    click = c["click_count"]
    rate = round(click / sent, 3) if sent else 0.0
    return CampaignStats(campaign_id=campaign_id, sent=sent, click=click, conversion_rate=rate)
