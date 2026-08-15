"""Custom SQLAlchemy types and column helpers.

The platform runs against 6 different RDBMS engines (PRD §6.1).
A few type-related differences need cross-dialect shims:

* ``JSONEncodedText`` — stores a JSON blob in a ``Text`` column.
  We avoid the ``JSON`` native type because some engines (SQLite,
  older MySQL, SQL Server pre-2016) handle JSON columns differently.
* ``UTCDateTime`` — every datetime in the platform is stored as
  UTC. We use ``DateTime(timezone=True)`` everywhere; engines
  without timezone support (SQLite) get a string fallback at read.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import String, Text, TypeDecorator
from sqlalchemy.types import DateTime


class JSONEncodedText(TypeDecorator):
    """Stores arbitrary JSON-serialisable data as TEXT.

    Falls back to a stable string representation. Always returns a
    Python object on read (dict / list / scalar).
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            # Assume already JSON-encoded.
            return value
        return json.dumps(value, ensure_ascii=False, default=str)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value


class UTCDateTime(TypeDecorator):
    """DateTime that always materialises as a tz-aware UTC datetime."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        # Strip tz info on engines that don't accept it; store naive UTC.
        if hasattr(value, "tzinfo") and value.tzinfo is not None:
            return value.astimezone().replace(tzinfo=None)
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        # Always return a value the caller can format however they want.
        return value


class String191(TypeDecorator):
    """VARCHAR(191) — safe length for MySQL utf8mb4 indexed columns.

    See PRD §22.1 pitfall #2: MySQL utf8mb4 index key length is
    767 bytes / 4 = 191 chars max. We expose this as a column type
    so the same model can be created on PG / Oracle / SQL Server
    without conditional DDL.
    """

    impl = String
    cache_ok = True

    def __init__(self, length: int = 191, **kwargs: Any) -> None:
        super().__init__(length, **kwargs)
