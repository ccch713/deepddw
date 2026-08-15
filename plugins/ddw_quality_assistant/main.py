"""Quality Assistant Plugin main entry point."""
from __future__ import annotations

from typing import Any


class QualityAssistantPlugin:
    """DDW Quality Assistant Plugin.

    AI-powered quality document generation: 8D reports, CAPA drafts,
    deviation investigations, complaint replies, and 5-Why analysis.
    """

    def __init__(self, app: Any):
        self.app = app
        self.service = None
        self.router = None

    def startup(self):
        from .models import Base
        from .router import router, set_service
        from .services import QualityAssistantService

        db_session = self.app.get_db_session()
        if db_session:
            Base.metadata.create_all(bind=db_session.get_bind())
            self.service = QualityAssistantService(db_session)
            set_service(self.service)

        self.router = router

    def get_router(self):
        return self.router
