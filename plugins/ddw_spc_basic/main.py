"""SPC Basic Plugin main entry point."""
from __future__ import annotations

from typing import Any


class SPCBasicPlugin:
    """DDW SPC Basic Plugin.

    Statistical Process Control: control charts (I-MR, Xbar-R, Xbar-S),
    process capability indices (Cp, Cpk, Pp, Ppk), Nelson rules violation
    detection, and AI-powered interpretation.
    """

    def __init__(self, app: Any):
        self.app = app
        self.service = None
        self.router = None

    def startup(self):
        from .models import Base
        from .router import router, set_service
        from .services import SPCService

        db_session = self.app.get_db_session()
        if db_session:
            Base.metadata.create_all(bind=db_session.get_bind())
            self.service = SPCService(db_session)
            set_service(self.service)

        self.router = router

    def get_router(self):
        return self.router
