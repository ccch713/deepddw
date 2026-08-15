"""API versioning router (PRD §18.6).

The platform exposes a single FastAPI app and a per-version
``APIRouter`` registered under ``/api/v{N}``. New versions are
added by calling :func:`register_version_router`. The current
default is ``/api/v1``; future versions will add additional
routers without breaking older clients.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List

from fastapi import APIRouter, FastAPI

logger = logging.getLogger(__name__)


# Registry: version -> (prefix, router)
_versions: Dict[str, APIRouter] = {}


def make_version_router(version: str) -> APIRouter:
    """Return a fresh :class:`APIRouter` for the given version, registering it."""

    prefix = f"/api/v{version}"
    if prefix in _versions:
        return _versions[prefix]
    router = APIRouter(prefix=prefix)
    _versions[prefix] = router
    return router


def register_version(app: FastAPI, version: str, configure: Callable[[APIRouter], None]) -> None:
    """Build a version router, hand it to ``configure``, and mount it on ``app``."""

    router = make_version_router(version)
    configure(router)
    app.include_router(router)
    logger.info("API version v%s mounted", version)


def list_versions() -> List[str]:
    return sorted(_versions.keys())


__all__ = ["make_version_router", "register_version", "list_versions"]
