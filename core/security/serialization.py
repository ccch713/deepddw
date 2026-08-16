"""S2: Safe serialization for API responses (PRD v5.7 §31.3).

One API issue: Channel `key` field serializes to JSON directly.
Fix: Pydantic field_serializer masks API keys before response.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_serializer


def mask_api_key(value: Optional[str], show_prefix: int = 4, show_suffix: int = 3) -> str:
    """Mask an API key for safe display.

    Examples:
        "sk-abc123def456ghi789" → "sk-a***789"
        "short" → "***"
        None → "***"
    """
    if not value or len(value) < 8:
        return "***"
    prefix = value[:show_prefix]
    suffix = value[-show_suffix:] if show_suffix > 0 else ""
    return f"{prefix}***{suffix}"


class SafeUserResponse(BaseModel):
    """Safe user response — never exposes password_hash or pin_hash."""

    id: int
    phone: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: str = "user"
    is_active: bool = True

    model_config = {"from_attributes": True}


class SafeSessionResponse(BaseModel):
    """Safe session response — never exposes JTI tokens."""

    id: int
    user_id: int
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    expires_at: str
    revoked: bool = False

    model_config = {"from_attributes": True}
