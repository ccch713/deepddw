"""DDW CAPA全流程闭环管理 — Plugin entry point for DDW AI Hub loader."""
from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """CAPA全流程闭环管理"""

    name = "ddw-capa-workflow"
    version = "1.0.0"
    router_prefix = "/api/v1/plugins/ddw-capa-workflow"

    def setup(self) -> None:
        """Register FastAPI router + initialize service (SQLite file, self-contained)."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from .models import Base
        from .router import router, set_service
        from .services import CAPAService

        db_path = self.config.get("db_path", "./data/capa_workflow.db")
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        set_service(CAPAService(session))

        self._router = router
        self.app.include_router(router)
        logger.info("ddw-capa-workflow v1.0.0 registered (service initialized)")


__all__ = ["Plugin"]
