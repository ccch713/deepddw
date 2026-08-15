"""DDW Dental EMR Template Kit - FastAPI router.

端点：
    GET  /templates            列出所有 9 类诊疗模板
    GET  /templates/{type}     获取单个模板完整定义
    POST /templates/{type}/validate  校验数据是否满足必填字段
    GET  /health               健康检查
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import PLUGIN_NAME, VERSION
from .loader import (
    get_template_full,
    list_templates,
    validate_required_fields,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_dental_emr_template_kit",
    tags=["ddw_dental_emr_template_kit"],
)


class HealthResponse(BaseModel):
    plugin: str = PLUGIN_NAME
    version: str = VERSION
    status: str = "ok"
    template_count: int = 0


class ValidateRequest(BaseModel):
    data: dict[str, Any]


class ValidateResponse(BaseModel):
    treatment_type: str
    valid: bool
    missing: list[dict[str, Any]] = []
    required_fields: list[str] = []


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(template_count=len(list_templates()))


@router.get("/templates")
async def list_all() -> dict[str, Any]:
    """列出所有模板（summary 形式）."""
    items = list_templates()
    return {
        "plugin": PLUGIN_NAME,
        "version": VERSION,
        "count": len(items),
        "templates": items,
    }


@router.get("/templates/{treatment_type}")
async def get_one(treatment_type: str) -> dict[str, Any]:
    """获取单个模板完整定义."""
    tpl = get_template_full(treatment_type)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"未知诊疗类型: {treatment_type}")
    return tpl


@router.post("/templates/{treatment_type}/validate", response_model=ValidateResponse)
async def validate(treatment_type: str, req: ValidateRequest) -> ValidateResponse:
    tpl = get_template_full(treatment_type)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"未知诊疗类型: {treatment_type}")
    missing = validate_required_fields(treatment_type, req.data)
    return ValidateResponse(
        treatment_type=treatment_type,
        valid=len(missing) == 0,
        missing=missing,
        required_fields=tpl.get("required_fields", []),
    )
