"""EngineFactory — SQLite-focused database engine factory.

deepDDW (开源版) focuses on SQLite for simplicity and portability.
The factory supports SQLite with optional aiosqlite for async operations.

Note: Commercial DDW AI Hub version supports multiple engines (PostgreSQL,
MySQL, etc.). This is a simplified version for the open-source release.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.config import DatabaseInstanceConfig, get_deployment
from core.database.sqlite_compat import ensure_sqlite_path

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base used by every ORM model in the platform."""

    pass


SUPPORTED_ENGINES = {"sqlite"}  # deepDDW only supports SQLite


def _dialect_url(cfg: DatabaseInstanceConfig) -> str:
    """Resolve a database instance config to a SQLAlchemy URL."""

    if cfg.url:
        return ensure_sqlite_path(cfg.url)
    if cfg.engine == "sqlite" and cfg.path:
        return ensure_sqlite_path(f"sqlite+aiosqlite:///{cfg.path}")
    # For open-source version, only SQLite is supported
    raise ValueError(f"Unsupported engine: {cfg.engine}. deepDDW only supports SQLite.")


class EngineFactory:
    """Holds async engines + session factories for every DB instance.

    The factory is a singleton in normal operation, but the class
    is plain and can be instantiated multiple times (e.g. by tests).
    """

    def __init__(self, config: Optional[Dict[str, DatabaseInstanceConfig]] = None) -> None:
        self._config = config or get_deployment().databases
        self._engines: Dict[str, AsyncEngine] = {}
        self._session_factories: Dict[str, async_sessionmaker[AsyncSession]] = {}

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _new_engine(self, name: str, cfg: DatabaseInstanceConfig) -> AsyncEngine:
        if cfg.engine not in SUPPORTED_ENGINES:
            raise ValueError(f"Unknown engine '{cfg.engine}' for db '{name}'. deepDDW only supports SQLite.")

        url = _dialect_url(cfg)
        kwargs: dict = {"echo": False, "future": True}
        # SQLite + async: enforce check_same_thread=False (aiosqlite
        # already manages this but be explicit).
        kwargs["connect_args"] = {"check_same_thread": False}
        engine = create_async_engine(url, **kwargs)
        logger.info("EngineFactory: created engine for %s (%s)", name, cfg.engine)
        return engine

    def create_engine(self, db_name: str) -> AsyncEngine:
        """Get (or create) the async engine for ``db_name``."""

        if db_name in self._engines:
            return self._engines[db_name]
        cfg = self._config.get(db_name)
        if cfg is None:
            raise KeyError(f"No database named '{db_name}' in deployment.yaml")
        engine = self._new_engine(db_name, cfg)
        self._engines[db_name] = engine
        return engine

    def get_session_factory(self, db_name: str) -> async_sessionmaker[AsyncSession]:
        """Get (or create) an async session factory for ``db_name``."""

        if db_name in self._session_factories:
            return self._session_factories[db_name]
        engine = self.create_engine(db_name)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        self._session_factories[db_name] = factory
        return factory

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #

    @asynccontextmanager
    async def session(self, db_name: str = "main") -> AsyncIterator[AsyncSession]:
        """Open a session, commit on success, rollback on error."""

        factory = self.get_session_factory(db_name)
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                raise

    async def init_all_databases(self) -> None:
        """Create all tables on all known databases.

        For production we rely on Alembic; this helper is convenient
        for fresh-install / tests. Per-instance DDL is per-engine
        because of cross-dialect type differences (e.g. JSON / BLOB).
        """

        # Import models so Base.metadata is populated.
        from core.database import models  # noqa: F401

        for name in self._config:
            engine = self.create_engine(name)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("EngineFactory: schema ensured for %s", name)

    async def health_check(self, db_name: str) -> dict:
        """Return a small health dict for the named DB."""

        engine = self.create_engine(db_name)
        try:
            async with engine.connect() as conn:
                from sqlalchemy import text

                result = await conn.execute(text("SELECT 1"))
                row = result.first()
                return {
                    "db": db_name,
                    "ok": row is not None and row[0] == 1,
                    "engine": self._config[db_name].engine,
                }
        except Exception as exc:  # noqa: BLE001
            logger.exception("health_check failed for %s", db_name)
            return {"db": db_name, "ok": False, "error": str(exc)}

    async def dispose(self) -> None:
        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()
        self._session_factories.clear()


# --------------------------------------------------------------------------- #
# Module-level singleton (process-wide).
# --------------------------------------------------------------------------- #


_factory: Optional[EngineFactory] = None


def get_engine_factory() -> EngineFactory:
    """Return the process-wide :class:`EngineFactory` singleton."""

    global _factory
    if _factory is None:
        _factory = EngineFactory()
    return _factory
