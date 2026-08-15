"""FastAPI router for SPC Basic plugin."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/plugins/ddw-spc-basic", tags=["spc-basic"])
_service = None


def set_service(service):
    global _service
    _service = service


class ControlChartRequest(BaseModel):
    data: List[float]
    chart_type: str = "I-MR"  # I-MR / Xbar-R / Xbar-S
    parameter_name: str = ""
    product_name: str = ""
    usl: Optional[float] = None
    lsl: Optional[float] = None


class CapabilityRequest(BaseModel):
    data: List[float]
    parameter_name: str = ""
    product_name: str = ""
    usl: Optional[float] = None
    lsl: Optional[float] = None


@router.post("/control-chart")
async def create_control_chart(req: ControlChartRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    if len(req.data) < 3:
        raise HTTPException(400, "Need at least 3 data points")
    chart = _service.create_control_chart(
        data=req.data, chart_type=req.chart_type,
        parameter_name=req.parameter_name, product_name=req.product_name,
        usl=req.usl, lsl=req.lsl
    )
    return {"id": chart.id, "chart_type": chart.chart_type,
            "center_line": chart.center_line, "ucl": chart.ucl, "lcl": chart.lcl,
            "usl": chart.usl, "lsl": chart.lsl, "violations": chart.violations,
            "cp": chart.cp, "cpk": chart.cpk, "pp": chart.pp, "ppk": chart.ppk,
            "interpretation": chart.interpretation}


@router.post("/capability")
async def calculate_capability(req: CapabilityRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    if len(req.data) < 2:
        raise HTTPException(400, "Need at least 2 data points")
    study = _service.calculate_capability(
        data=req.data, parameter_name=req.parameter_name,
        product_name=req.product_name, usl=req.usl, lsl=req.lsl
    )
    return {"id": study.id, "parameter_name": study.parameter_name,
            "sample_size": study.sample_size, "mean": study.mean,
            "std_dev": study.std_dev, "cp": study.cp, "cpk": study.cpk,
            "pp": study.pp, "ppk": study.ppk,
            "capability_grade": study.capability_grade,
            "interpretation": study.interpretation}


@router.get("/control-charts")
async def list_charts(parameter_name: Optional[str] = None, limit: int = 50):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    charts = _service.list_control_charts(parameter_name=parameter_name, limit=limit)
    return [{"id": c.id, "chart_type": c.chart_type,
             "parameter_name": c.parameter_name, "cpk": c.cpk,
             "created_at": c.created_at.isoformat()} for c in charts]


@router.get("/control-charts/{chart_id}")
async def get_chart(chart_id: int):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    chart = _service.get_control_chart(chart_id)
    if not chart:
        raise HTTPException(404, "Chart not found")
    return {"id": chart.id, "chart_type": chart.chart_type,
            "parameter_name": chart.parameter_name,
            "data_points": chart.data_points, "center_line": chart.center_line,
            "ucl": chart.ucl, "lcl": chart.lcl, "usl": chart.usl, "lsl": chart.lsl,
            "violations": chart.violations, "cp": chart.cp, "cpk": chart.cpk,
            "interpretation": chart.interpretation}


@router.get("/health")
async def health():
    return {"status": "ok", "plugin": "ddw-spc-basic", "version": "1.0.0"}
