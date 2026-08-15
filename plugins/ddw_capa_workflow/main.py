"""CAPA Workflow Plugin main entry point."""
from __future__ import annotations

from typing import Any


class CAPAWorkflowPlugin:
    """DDW CAPA Workflow Plugin.

    Full lifecycle management for Corrective and Preventive Actions (CAPA):
    creation, investigation, action planning, effectiveness verification,
    and closure with complete audit trail.
    """

    def __init__(self, app: Any):
        self.app = app
        self.service = None
        self.router = None

    def startup(self):
        from .models import Base
        from .router import router, set_service
        from .services import CAPAService

        db_session = self.app.get_db_session()
        if db_session:
            Base.metadata.create_all(bind=db_session.get_bind())
            self.service = CAPAService(db_session)
            set_service(self.service)

        self.router = router

    def get_router(self):
        return self.router
