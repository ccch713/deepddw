"""Test fixtures for plugin tests (PRD §18.12)."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture
def temp_data_dir() -> Iterator[Path]:
    """Yield a fresh temp dir for SQLite files."""

    d = Path(tempfile.mkdtemp(prefix="ddw-test-"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
