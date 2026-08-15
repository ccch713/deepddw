"""API routes for the DDW ESG Report plugin.

Endpoints:
  - GET  /health          — plugin health + dependency info
  - POST /generate        — generate a PDF report
  - GET  /report/{id}     — get report metadata
  - GET  /download/{id}   — download the PDF file
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from fastapi import HTTPException
from fastapi.responses import FileResponse

try:
    from .fonts import get_font_name, register_fonts
    from .models import (
        ReportGenerateRequest,
        ReportGenerateResponse,
        ReportMetadata,
    )
    from .pdf_generator import generate_pdf
except ImportError:
    from fonts import get_font_name  # type: ignore[no-redef]
    from models import (  # type: ignore[no-redef]
        ReportGenerateRequest,
        ReportGenerateResponse,
        ReportMetadata,
    )
    from pdf_generator import generate_pdf  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# ── In-memory report registry ───────────────────────────────────────
# In production, use a DB. For now, store metadata in memory.
_REPORTS: Dict[str, dict] = {}

# ── Plugin directory (reports stored here) ──────────────────────────
_PLUGIN_DIR = Path(__file__).parent
REPORTS_DIR = str(_PLUGIN_DIR / "reports")


# ── Health check ────────────────────────────────────────────────────

async def health_check() -> dict:
    """Return plugin health status, font availability, and dependency versions."""
    font_name = get_font_name()

    deps: dict[str, str] = {}
    try:
        import reportlab
        deps["reportlab"] = reportlab.Version if hasattr(reportlab, "Version") else "installed"
    except ImportError:
        deps["reportlab"] = "not installed"

    try:
        import matplotlib
        deps["matplotlib"] = matplotlib.__version__
    except ImportError:
        deps["matplotlib"] = "not installed"

    try:
        import pydantic
        deps["pydantic"] = pydantic.__version__
    except ImportError:
        deps["pydantic"] = "not installed"

    return {
        "plugin": "ddw-esg-report",
        "status": "ok",
        "font": font_name,
        "dependencies": deps,
        "reports_dir": REPORTS_DIR,
    }


# ── Generate report ─────────────────────────────────────────────────

async def generate_report(req: ReportGenerateRequest) -> ReportGenerateResponse:
    """Generate an ESG assessment PDF report."""
    t0 = datetime.now(timezone.utc)

    try:
        result = generate_pdf(req, REPORTS_DIR)
    except Exception as exc:
        logger.exception("Failed to generate report")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc

    report_id = result["report_id"]
    file_path = result["file_path"]
    now = datetime.now(timezone.utc)

    # Store metadata for later retrieval
    _REPORTS[report_id] = {
        "report_id": report_id,
        "assessment_id": req.assessment_id,
        "company_name": req.company_name,
        "file_path": file_path,
        "file_size_bytes": result["file_size"],
        "pages": result["pages"],
        "generated_at": now.isoformat(),
    }

    duration_ms = result["duration_ms"]

    return ReportGenerateResponse(
        report_id=report_id,
        assessment_id=req.assessment_id,
        download_url=f"/api/v1/plugins/ddw-esg-report/download/{report_id}",
        file_size_bytes=result["file_size"],
        pages=result["pages"],
        generated_at=now.isoformat(),
        duration_ms=duration_ms,
    )


# ── Get report metadata ─────────────────────────────────────────────

async def get_report_metadata(report_id: str) -> ReportMetadata:
    """Retrieve metadata for a previously generated report."""
    meta = _REPORTS.get(report_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    return ReportMetadata(**meta)


# ── Download report ─────────────────────────────────────────────────

async def download_report(report_id: str) -> FileResponse:
    """Download the generated PDF file."""
    meta = _REPORTS.get(report_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    file_path = meta["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=f"ESG_Report_{report_id}.pdf",
    )
