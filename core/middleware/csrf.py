"""S5: CSRF protection middleware (PRD v5.7 §31.5).

One API issue: Cookie authentication has no CSRF token.
Fix: SameSite=Strict + CSRF Token validation for state-changing requests.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# CSRF token lifetime (seconds) — tokens expire after this
CSRF_TOKEN_LIFETIME = 3600  # 1 hour

# Methods that require CSRF protection
STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _get_csrf_secret() -> str:
    """Get CSRF secret from environment or generate one."""
    secret = os.getenv("DDW_CSRF_SECRET")
    if not secret:
        secret = os.getenv("DDW_JWT_SECRET", "csrf-fallback-secret")
    return secret


def generate_csrf_token(session_id: Optional[str] = None) -> str:
    """Generate a CSRF token tied to the session.

    Format: timestamp.hmac_hex
    """
    now = int(time.time())
    payload = f"{now}:{session_id or 'anonymous'}"
    secret = _get_csrf_secret()
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{now}.{sig}"


def validate_csrf_token(token: str, session_id: Optional[str] = None) -> bool:
    """Validate a CSRF token.

    Returns True if the token is valid and not expired.
    """
    if not token or "." not in token:
        return False

    try:
        ts_str, sig = token.split(".", 1)
        ts = int(ts_str)
    except (ValueError, TypeError):
        return False

    # Check expiry
    if time.time() - ts > CSRF_TOKEN_LIFETIME:
        return False

    # Verify HMAC
    payload = f"{ts}:{session_id or 'anonymous'}"
    secret = _get_csrf_secret()
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig, expected)


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF protection middleware.

    Enforces CSRF token validation for state-changing requests (POST/PUT/PATCH/DELETE)
    when the request uses cookie-based authentication.

    Skip conditions:
    - GET, HEAD, OPTIONS (safe methods)
    - Bearer token authentication (not cookie-based)
    - API key authentication
    - Content-Type: application/json with X-Requested-With header (SPA pattern)
    """

    async def dispatch(self, request: Request, call_next):
        # Skip safe methods
        if request.method not in STATE_CHANGING_METHODS:
            return await call_next(request)

        # Skip if using Bearer token (not cookie-based auth)
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            return await call_next(request)

        # Skip if using API key header
        if request.headers.get("x-api-key"):
            return await call_next(request)

        # Skip if X-Requested-With is set (SPA/AJAX pattern — tokens in headers)
        if request.headers.get("x-requested-with"):
            return await call_next(request)

        # Check for CSRF token in header or form data
        csrf_token = (
            request.headers.get("x-csrf-token")
            or request.headers.get("x-xsrf-token")
        )

        # Also check form data for non-JSON requests
        if not csrf_token and "application/x-www-form-urlencoded" in (
            request.headers.get("content-type", "")
        ):
            form = await request.form()
            csrf_token_raw = form.get("_csrf_token")
            if isinstance(csrf_token_raw, str):
                csrf_token = csrf_token_raw

        if not csrf_token:
            logger.warning("CSRF token missing for %s %s", request.method, request.url.path)
            return Response(
                status_code=403,
                content='{"detail": "CSRF token required"}',
                media_type="application/json",
            )

        # Validate token
        session_id = request.cookies.get("session_id")
        if not validate_csrf_token(csrf_token, session_id):
            logger.warning("CSRF token invalid for %s %s", request.method, request.url.path)
            return Response(
                status_code=403,
                content='{"detail": "Invalid CSRF token"}',
                media_type="application/json",
            )

        return await call_next(request)
