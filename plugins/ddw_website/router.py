"""FastAPI router for DDW Website plugin.

端点：
- GET  /api/v1/plugins/ddw-website/theme          → 当前主题（前台页面调用）
- PUT  /api/v1/plugins/ddw-website/theme          → 切换主题（管理后台调用）
- GET  /api/v1/plugins/ddw-website/site           → 站点基础信息
- GET  /api/v1/plugins/ddw-website/pages          → 页面清单
- PUT  /api/v1/plugins/ddw-website/site           → 更新站点信息（管理后台）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .config import load_config, save_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plugins/ddw-website", tags=["ddw-website"])


class ThemeRequest(BaseModel):
    theme: str


class SiteUpdateRequest(BaseModel):
    company: Optional[Dict[str, Any]] = None
    links: Optional[Dict[str, Any]] = None


@router.get("/theme")
async def get_theme() -> Dict[str, Any]:
    """前台页面读取当前主题模版。"""
    cfg = load_config()
    theme = cfg.get("theme", {})
    return {
        "theme": theme.get("current", "standard"),
        "available": theme.get("available", ["standard", "holiday", "mourning"]),
    }


@router.put("/theme")
async def set_theme(req: ThemeRequest) -> Dict[str, Any]:
    """管理后台切换主题模版（节日/素色等场景一键切换）。"""
    cfg = load_config()
    available = cfg.get("theme", {}).get("available", ["standard", "holiday", "mourning"])
    if req.theme not in available:
        raise HTTPException(400, f"无效主题: {req.theme}，可用: {available}")
    cfg.setdefault("theme", {})["current"] = req.theme
    save_config(cfg)
    logger.info("ddw-website theme switched to %s", req.theme)
    return {"ok": True, "theme": req.theme}


@router.get("/site")
async def get_site() -> Dict[str, Any]:
    """站点基础信息（公司全称/备案/联系方式）。"""
    cfg = load_config()
    return {"company": cfg.get("company", {}), "links": cfg.get("links", {})}


@router.get("/pages")
async def get_pages() -> Dict[str, Any]:
    """官网页面清单。"""
    cfg = load_config()
    return {"pages": cfg.get("pages", {})}


@router.put("/site")
async def update_site(req: SiteUpdateRequest) -> Dict[str, Any]:
    """管理后台更新站点信息。"""
    cfg = load_config()
    if req.company:
        cfg.setdefault("company", {}).update(req.company)
    if req.links:
        cfg.setdefault("links", {}).update(req.links)
    save_config(cfg)
    return {"ok": True}
