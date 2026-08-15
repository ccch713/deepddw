"""DDW 主题系统 API 路由"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from plugins.ddw_theme.models import (
    ExportFormat,
    Theme,
    ThemeSwitchRequest,
)

logger = logging.getLogger(__name__)


class ThemeCreateReq(BaseModel):
    theme_id: str
    name: str
    description: str = ""
    css_variables: Dict[str, str] = {}
    icon_set: str = "default"


class ThemeUpdateReq(BaseModel):
    name: str | None = None
    description: str | None = None
    css_variables: Dict[str, str] | None = None
    icon_set: str | None = None


def build_router(plugin: Any) -> APIRouter:
    router = APIRouter(prefix=plugin.router_prefix, tags=[plugin.name])
    svc = plugin.theme_service

    # ---- Theme CRUD ----

    @router.get("/themes", response_model=List[Theme])
    async def list_themes():
        return svc.list_themes()

    @router.post("/themes", response_model=Theme, status_code=201)
    async def create_theme(req: ThemeCreateReq):
        try:
            theme = Theme(
                theme_id=req.theme_id,
                name=req.name,
                description=req.description,
                css_variables=req.css_variables,
                icon_set=req.icon_set,
            )
            return svc.create_theme(theme)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @router.get("/themes/{theme_id}", response_model=Theme)
    async def get_theme(theme_id: str):
        theme = svc.get_theme(theme_id)
        if theme is None:
            raise HTTPException(status_code=404, detail=f"Theme '{theme_id}' not found")
        return theme

    @router.put("/themes/{theme_id}", response_model=Theme)
    async def update_theme(theme_id: str, req: ThemeUpdateReq):
        try:
            updates = req.model_dump(exclude_none=True)
            return svc.update_theme(theme_id, updates)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.delete("/themes/{theme_id}")
    async def delete_theme(theme_id: str):
        try:
            svc.delete_theme(theme_id)
            return {"deleted": True}
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ---- Presets ----

    @router.get("/themes/presets/list")
    async def list_presets():
        return svc.list_presets()

    # ---- Switch ----

    @router.post("/themes/switch")
    async def switch_theme(req: ThemeSwitchRequest):
        try:
            return svc.switch_theme(req)
        except (KeyError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ---- CSS preview ----

    @router.get("/themes/{theme_id}/css")
    async def get_css(theme_id: str):
        theme = svc.get_theme(theme_id)
        if theme is None:
            raise HTTPException(status_code=404, detail=f"Theme '{theme_id}' not found")
        return {"theme_id": theme_id, "css": svc.generate_css_variables(theme)}

    # ---- Export / Import ----

    @router.get("/themes/{theme_id}/export")
    async def export_theme(theme_id: str, format: str = "json", include_custom: bool = True):
        try:
            fmt = ExportFormat(format)
            return svc.export_theme(theme_id, fmt, include_custom)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/themes/import", response_model=Theme, status_code=201)
    async def import_theme(data: Dict[str, Any]):
        try:
            return svc.import_theme(data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    return router
