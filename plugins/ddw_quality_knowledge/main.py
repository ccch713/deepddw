"""Quality Knowledge Plugin main entry point."""
from __future__ import annotations

from typing import Any


class QualityKnowledgePlugin:
    """DDW Quality Knowledge Plugin.

    Intelligent knowledge retrieval for food safety standards (ISO 22000,
    FSSC 22000, HACCP), SOPs, case studies, and regulatory documents.
    """

    def __init__(self, app: Any):
        self.app = app
        self.service = None
        self.router = None

    def startup(self):
        from .models import Base
        from .router import router, set_service
        from .services import QualityKnowledgeService

        db_session = self.app.get_db_session()
        if db_session:
            Base.metadata.create_all(bind=db_session.get_bind())
            self.service = QualityKnowledgeService(db_session)
            set_service(self.service)

        self.router = router

    def get_router(self):
        return self.router
