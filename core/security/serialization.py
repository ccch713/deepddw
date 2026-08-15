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


class SafeChannelResponse(BaseModel):
    """Safe channel response model — hides API keys in JSON serialization.

    Use this model for any API endpoint that returns channel/provider data
    containing sensitive key fields.
    """

    id: int
    name: str
    type: int
    status: int
    base_url: str
    models: str
    key: Optional[str] = None

    @field_serializer("key")
    def mask_key(self, value: Optional[str]) -> str:
        """API Key masking: sk-abc...xyz → sk-a***xyz"""
        return mask_api_key(value)


class SafeLLMProviderResponse(BaseModel):
    """Safe LLM provider response — masks api_key_ref field."""

    id: int
    name: str
    api_base: Optional[str] = None
    api_key_ref: Optional[str] = None
    default_model: Optional[str] = None
    enabled: bool = True

    @field_serializer("api_key_ref")
    def mask_api_key_ref(self, value: Optional[str]) -> str:
        """Mask the API key reference."""
        return mask_api_key(value)


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
