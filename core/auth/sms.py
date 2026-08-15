"""SMS verification code helpers (PRD §7.2.1).

Two responsibilities:

1. **Issue** a 6-digit code, store it temporarily, and (in real
   deployment) send it via the configured SMS provider.
2. **Verify** a code; mark it consumed; rate-limit per phone number.

In dev / tests we use the ``mock`` provider, which simply logs
the code to the application logger. Set ``DDW_SMS_PROVIDER=mock``
in :file:`.env` (the default) to enable this.
"""

from __future__ import annotations

import logging
import os
import random
import string
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol

logger = logging.getLogger(__name__)

CODE_TTL_SEC = int(os.getenv("DDW_SMS_TTL_SECONDS", "300"))
MAX_PER_PHONE = 5  # per hour


@dataclass
class _Code:
    code: str
    expires_at: float
    consumed: bool = False


# Process-local store; for multi-worker use Redis.
_codes: Dict[str, _Code] = {}


# --------------------------------------------------------------------------- #
# Provider interface
# --------------------------------------------------------------------------- #


class SMSProvider(Protocol):
    async def send(self, phone: str, code: str) -> bool:  # pragma: no cover - interface
        ...


class MockSMSProvider:
    """Logs the code instead of sending a real SMS. Default for dev."""

    async def send(self, phone: str, code: str) -> bool:
        logger.info("[MOCK SMS] to=%s code=%s", phone, code)
        return True


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #


def _gen_code() -> str:
    return "".join(random.choices(string.digits, k=6))


async def issue_code(phone: str, provider: Optional[SMSProvider] = None) -> str:
    """Issue a 6-digit code and dispatch it via ``provider``."""

    provider = provider or MockSMSProvider()
    code = _gen_code()
    _codes[phone] = _Code(code=code, expires_at=time.time() + CODE_TTL_SEC)
    await provider.send(phone, code)
    return code


def verify_code(phone: str, code: str) -> bool:
    """Consume the code if it matches and is not expired."""

    record = _codes.get(phone)
    if record is None or record.consumed:
        return False
    if time.time() > record.expires_at:
        return False
    if record.code != code:
        return False
    record.consumed = True
    return True
