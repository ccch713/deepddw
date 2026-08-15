"""DDW ESG Report plugin — PDF report generation for ESG assessments.

Provides FastAPI endpoints for generating, downloading, and querying
ESG pre-assessment PDF reports with radar charts, score breakdowns,
meta analysis, and priority recommendations.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw-esg-report",
    tags=["ddw-esg-report"],
)

# Import routes to attach them to the router (relative imports)
try:
    from .routes import (  # noqa: E402
        download_report,
        generate_report,
        get_report_metadata,
        health_check,
    )
except ImportError:
    from routes import (  # type: ignore[no-redef]  # noqa: E402
        download_report,
        generate_report,
        get_report_metadata,
        health_check,
    )

router.add_api_route("/health", health_check, methods=["GET"], name="health")
router.add_api_route("/generate", generate_report, methods=["POST"], name="generate")
router.add_api_route("/report/{report_id}", get_report_metadata, methods=["GET"], name="report_metadata")
router.add_api_route("/download/{report_id}", download_report, methods=["GET"], name="download")


TOOL_ANNOTATIONS: dict[str, dict] = {
    "generate_report": {'readOnly': False},
    "list_reports": {'readOnly': True},
    "download_report": {'readOnly': True},
}

def register(app: Any) -> None:
    """Register the ESG report router with the FastAPI app."""
    app.include_router(router)
    logger.info("ddw-esg-report plugin registered")
