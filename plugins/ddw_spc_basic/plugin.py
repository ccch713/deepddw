"""DDW 控制图/过程能力/判异规则检测 — Plugin entry point for DDW AI Hub loader."""
from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """控制图/过程能力/判异规则检测"""

    name = "ddw-spc-basic"
    version = "1.0.0"
    router_prefix = "/api/v1/plugins/ddw-spc-basic"

    def setup(self) -> None:
        """Register FastAPI router + initialize service (SQLite file, self-contained)."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from .models import Base
        from .router import router, set_service
        from .services import SPCService

        db_path = self.config.get("db_path", "./data/spc_basic.db")
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        set_service(SPCService(session))

        self._router = router
        self.app.include_router(router)
        logger.info("ddw-spc-basic v1.0.0 registered (service initialized)")


__all__ = ["Plugin"]
