"""SQLite compatibility helpers.

A handful of small differences vs. server-class RDBMS that
we have to compensate for:

* SQLite does **not** support ``ALTER TABLE DROP COLUMN``
  (PRD §22.1 pitfall #1). Alembic will rewrite the table
  on drop, but at the application layer we must not emit
  raw ALTER statements.
* SQLite's ``DateTime`` is text — we already normalise on
  the write side in :mod:`core.database.types`.
* SQLite serialises writes — no concurrent writers. The
  async driver (aiosqlite) already provides per-connection
  serialisation; we just expose a helper that creates the
  data directory on demand.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def ensure_sqlite_path(url: str) -> str:
    """If ``url`` points to a SQLite file, ensure the directory exists.

    Returns the URL unchanged otherwise.
    """

    if not url.startswith("sqlite"):
        return url
    # Strip the prefix and the aiosqlite driver tag.
    body = url.split("///", 1)[-1]
    if body.startswith("./") or body.startswith("/"):
        path = Path(body).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
    return url


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def sqlite_alter_drop_column_workaround() -> dict[str, Any]:
    """Information for upstream code that needs to do a DROP COLUMN
    against SQLite. Returns a small description; concrete rebuild
    logic is delegated to Alembic."""
    return {
        "supported": False,
        "strategy": "rebuild_table",
        "note": "Use Alembic op.create_table + op.drop_table pattern, see PRD §22.1",
    }
