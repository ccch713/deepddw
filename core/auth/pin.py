"""PIN-code login (PRD §7.2.1).

PINs are short numeric codes set by the user for fast re-auth on
mobile. We never store the PIN itself; we store a SHA-256 hash
with a per-user random salt.

PIN flow (mobile app side):

1. User enters PIN
2. Backend verifies PIN against ``users.pin_hash``
3. If OK, backend issues a JWT (same as phone+OTP login)

Optional rate limiting: at most 5 attempts per 5 minutes per user.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# In-memory rate limiter (per-process). For multi-worker we
# promote to Redis in the RedisBus (PRD §18.2).
_attempts: Dict[int, list[float]] = {}
WINDOW_SEC = 300
MAX_ATTEMPTS = 5


def _hash_pin(pin: str, salt: str) -> str:
    """Combine salt + pin and return a hex SHA-256 hash.

    Storing only the hash means a database leak does not give an
    attacker usable PINs. Salt prevents rainbow tables.
    """

    h = hashlib.sha256()
    h.update(salt.encode("utf-8"))
    h.update(b":")
    h.update(pin.encode("utf-8"))
    return h.hexdigest()


def hash_pin(pin: str) -> str:
    """Return ``salt$hash`` for a fresh PIN. PIN must be 4-8 digits."""

    if not (pin.isdigit() and 4 <= len(pin) <= 8):
        raise ValueError("PIN must be 4-8 digits")
    salt = secrets.token_hex(8)
    return f"{salt}${_hash_pin(pin, salt)}"


def verify_pin(pin: str, stored: str, *, user_id: Optional[int] = None) -> bool:
    """Verify a PIN against the stored ``salt$hash`` value."""

    if not stored or "$" not in stored:
        return False
    if user_id is not None and not _within_rate_limit(user_id):
        logger.warning("PIN verify rate-limited for user=%s", user_id)
        return False
    salt, expected = stored.split("$", 1)
    actual = _hash_pin(pin, salt)
    ok = hmac.compare_digest(actual, expected)
    if user_id is not None:
        _record_attempt(user_id, ok)
    return ok


def _now() -> float:
    return time.time()


def _within_rate_limit(user_id: int) -> bool:
    bucket = _attempts.setdefault(user_id, [])
    bucket[:] = [t for t in bucket if _now() - t < WINDOW_SEC]
    return len(bucket) < MAX_ATTEMPTS


def _record_attempt(user_id: int, success: bool) -> None:
    bucket = _attempts.setdefault(user_id, [])
    bucket.append(_now())
    if success:
        bucket.clear()
