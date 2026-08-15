"""Regulatory Evidence Plugin main entry point."""
from __future__ import annotations

from typing import Any


class RegulatoryEvidencePlugin:
    """DDW Regulatory Evidence Plugin.

    Regulatory document management and evidence chain tracking for
    food safety compliance: NHC, EU Novel Food, EFSA, FDA, Codex.
    Supports multi-jurisdiction regulatory intelligence.
    """

    def __init__(self, app: Any):
        self.app = app
        self.service = None
        self.router = None

    def startup(self):
        from .models import Base
        from .router import router, set_service
        from .services import RegulatoryEvidenceService

        db_session = self.app.get_db_session()
        if db_session:
            Base.metadata.create_all(bind=db_session.get_bind())
            self.service = RegulatoryEvidenceService(db_session)
            set_service(self.service)

        self.router = router

    def get_router(self):
        return self.router
