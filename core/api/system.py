"""Health & system routes (PRD §7.2.13)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from core.api_response import ok
from core.database.factory import get_engine_factory
from core.llm_gateway.gateway import health as llm_health
from core.middleware.tenant import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/system", tags=["system"])


@router.get("/health")
async def health() -> Any:
    factory = get_engine_factory()
    db_results = {}
    for name in factory._config:  # noqa: SLF001
        db_results[name] = await factory.health_check(name)
    llm = await llm_health()
    return ok({"databases": db_results, "llm": llm})


@router.get("/config")
async def config_view(claims=Depends(require_admin)) -> Any:
    """Read-only snapshot of the loaded deployment config."""

    from core.config import get_deployment

    dep = get_deployment()
    return ok({
        "mode": dep.mode,
        "server": dep.server.model_dump(),
        "databases": {k: v.model_dump() for k, v in dep.databases.items()},
        "llm": dep.llm.model_dump(),
        "billing": dep.billing.model_dump(),
    })


@router.post("/reload")
async def reload(claims=Depends(require_admin)) -> Any:
    """Force a config reload (PRD §18.5 hot reloader entry point)."""

    from core.config import reload_settings

    reload_settings()
    return ok({"reloaded": True})
