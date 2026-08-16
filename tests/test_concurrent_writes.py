"""P0-1（multidevice）：SQLite 并发写加固测试。

验收：20 并发任务同时写记忆与知识库，连续 3 轮无
``database is locked`` / ``OperationalError``；PRAGMA 生效。
"""

from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-concurrent-writes-token")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch, tmp_path):
    """每测试独立库 + 清连接池/写锁。"""
    from core import knowledge as kb
    from core.database import session as db_session

    monkeypatch.setattr(kb, "_db_path", lambda: tmp_path / "kb.db")
    monkeypatch.setattr(db_session, "_engine", None)
    monkeypatch.setattr(db_session, "_session_maker", None)
    monkeypatch.setattr(db_session, "_write_lock", None)
    kb.reset_conn_pool()
    yield
    kb.reset_conn_pool()


async def _concurrent_write_round(n: int = 20) -> list[str]:
    """一轮 n 路并发写：async（chat 落库路径）+ sync（记忆/知识库路径）。"""
    import asyncio

    from core.api import chat as chat_mod
    from core.database.session import get_write_lock
    from core.knowledge import memory_log_append, reset_conn_pool

    errors: list[str] = []

    async def async_writer(i: int) -> None:
        try:
            from core.database.session import session_scope
            from sqlalchemy import text

            async with get_write_lock():
                async with session_scope() as session:
                    await session.execute(text(
                        "CREATE TABLE IF NOT EXISTS t_async (i INTEGER)"
                    ))
                    await session.execute(text(
                        "INSERT INTO t_async (i) VALUES (:i)"), {"i": i}
                    )
                    await session.commit()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"async#{i}: {exc!r}")

    def sync_writer(i: int) -> None:
        try:
            memory_log_append(f"并发写{i}", auto=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"sync#{i}: {exc!r}")

    await asyncio.gather(*(async_writer(i) for i in range(n)))
    # 同步写走线程池（knowledge 单连接锁串行化）
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(sync_writer, range(n)))
    reset_conn_pool()
    return errors


@pytest.mark.asyncio
async def test_20_concurrent_writes_no_locked(tmp_path):
    """20 并发 × 3 轮：无 database is locked / OperationalError。"""
    for round_no in range(3):
        errors = await _concurrent_write_round(20)
        assert not errors, f"round {round_no + 1} errors: {errors[:5]}"


def test_sqlite_wal_pragma_enabled(tmp_path):
    """PRAGMA：async 引擎连接 journal_mode=WAL + busy_timeout 生效。"""
    import asyncio

    import core.database.session as db_session
    from sqlalchemy import text

    asyncio.get_event_loop().run_until_complete(_ensure_engine(tmp_path))
    assert db_session._engine is not None

    async def check() -> None:
        engine = db_session.get_engine()
        async with engine.connect() as conn:
            mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
            timeout = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
            sync = (await conn.execute(text("PRAGMA synchronous"))).scalar()
        return mode, timeout, sync

    mode, timeout, sync = asyncio.get_event_loop().run_until_complete(check())
    assert str(mode).lower() == "wal"
    assert timeout == 5000
    assert sync == 1  # NORMAL


async def _ensure_engine(tmp_path) -> None:
    import core.database.session as db_session
    from core.config import get_settings

    settings = get_settings()
    settings.databases["main"] = {
        "engine": "sqlite",
        "path": str(tmp_path / "main.db"),
        "url": f"sqlite+aiosqlite:///{tmp_path}/main.db",
    }
    # 重建引擎（fixture 已置 None）
    db_session.get_engine()
