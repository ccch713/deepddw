"""Common response envelope and Pydantic schemas.

Per PRD §7.1 every API response uses::

    {code, message, data, timestamp}

The :func:`ok` / :func:`fail` helpers produce this envelope.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None
    timestamp: str = Field(default_factory=lambda: dt.datetime.utcnow().isoformat() + "Z")


def ok(data: Any = None, message: str = "ok") -> dict:
    return APIResponse(code=0, message=message, data=data).model_dump()


def fail(message: str, code: int = 1, data: Any = None) -> dict:
    return APIResponse(code=code, message=message, data=data).model_dump()


class Page(BaseModel, Generic[T]):
    items: List[T]
    page: int = 1
    page_size: int = 20
    total: int = 0


__all__ = ["APIResponse", "Page", "ok", "fail"]
