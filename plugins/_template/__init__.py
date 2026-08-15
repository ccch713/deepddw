"""Plugin template — copy this file into a new plugin directory.

A plugin MUST provide:

* ``manifest.yaml`` — name, version, dependencies, permissions
* ``__init__.py`` — a ``register(app)`` function
* (Optional) a ``tests/`` folder

The platform discovers plugins by scanning ``plugins/*/manifest.yaml`` and
imports the matching package. The plugin's ``register`` is called once
at startup to attach its APIRouter to the main FastAPI app.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plugins/_template", tags=["_template"])


@router.get("/health")
async def health() -> dict:
    return {"plugin": "_template", "status": "ok"}


def register(app: Any) -> None:
    app.include_router(router)
    logger.info("_template plugin registered")
