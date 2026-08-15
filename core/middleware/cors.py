"""CORS configuration helpers (PRD §19 + v5.7 §31.4).

One API issue: CORS("*") allows all origins.
Fix: Whitelist mode with environment variable configuration.
Cloud mode: never allows "*" — replaced with safe default.
"""

from __future__ import annotations

import logging
import os
from typing import List

from fastapi.middleware.cors import CORSMiddleware

from core.config import get_deployment

logger = logging.getLogger(__name__)


def build_cors_middleware(app):
    """Attach a CORSMiddleware to ``app`` using deployment.yaml config.

    In standalone mode we are typically permissive (CORS allows
    ``*``); in cloud mode operators are expected to lock this down.

    v5.7 fix: Environment variable DDW_CORS_ORIGINS overrides config.
    """
    cfg = get_deployment().cors
    origins: List[str] = list(cfg.allow_origins)

    # v5.7 S3 fix: Allow environment variable override
    env_origins = os.getenv("DDW_CORS_ORIGINS")
    if env_origins:
        origins = [o.strip() for o in env_origins.split(",") if o.strip()]

    # Cloud deployments must never allow ``*``
    if get_deployment().mode == "cloud" and "*" in origins:
        logger.warning("CORS '*' not allowed in cloud mode — using safe default")
        origins = ["https://localhost:8500"]

    # Security: wildcard origin + credentials = CSRF wide open; auto-downgrade
    if "*" in origins:
        logger.warning("CORS: wildcard origin with credentials is disabled for security")
        origins = ["http://localhost:8500"]

    # v5.7: Restrict allowed methods (no wildcard)
    allowed_methods = list(cfg.allow_methods)
    if "*" in allowed_methods:
        allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=allowed_methods,
        allow_headers=list(cfg.allow_headers) if cfg.allow_headers != ["*"] else [
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Requested-With",
            "X-CSRF-Token",
        ],
        max_age=600,  # Cache preflight for 10 minutes
    )
    return app
