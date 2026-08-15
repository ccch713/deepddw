"""LLM 管理 API（/llm）— 提供商 / 路由规则。

前端 admin.html 频道依赖：
- GET /llm/providers    LLM 提供商健康/列表
- GET /llm/rules        路由规则
- GET /llm/fallback     回退链
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends

from core.auth.jwt import current_admin
from core.llm_gateway.gateway import health as llm_health
from core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/providers", response_model=Dict[str, Any])
async def list_providers(claims: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """LLM 提供商列表/健康状态。"""
    try:
        h = await llm_health()
        return {"items": h if isinstance(h, list) else [h], "total": 1}
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_health failed: %s", exc)
        return {"items": [], "total": 0, "error": str(exc)}


@router.get("/rules", response_model=Dict[str, Any])
async def list_rules(claims: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """路由规则列表。"""
    try:
        settings = get_settings()
        rules = getattr(settings, "llm_routing_rules", None)
        if rules is None and hasattr(settings, "llm"):
            rules = getattr(settings.llm, "routing_rules", None)
        items = []
        if rules:
            for r in rules:
                items.append(r.model_dump() if hasattr(r, "model_dump") else dict(r))
        return {"items": items, "total": len(items)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_rules failed: %s", exc)
        return {"items": [], "total": 0, "error": str(exc)}


@router.get("/fallback", response_model=Dict[str, Any])
async def fallback(claims: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """回退链。"""
    try:
        settings = get_settings()
        chain = getattr(settings, "llm_fallback_chain", None)
        if chain is None and hasattr(settings, "llm"):
            chain = getattr(settings.llm, "fallback_chain", None)
        return {"chain": chain or []}
    except Exception as exc:  # noqa: BLE001
        logger.warning("fallback failed: %s", exc)
        return {"chain": [], "error": str(exc)}
