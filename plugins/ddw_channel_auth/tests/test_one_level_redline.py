"""DDW 渠道授权与结算插件 — 一级分销红线测试。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from plugins.ddw_channel_auth.router import create_sub_agent_attempt


@pytest.mark.anyio
async def test_one_level_distribution_redline_blocks_subagent_creation():
    """调 create_sub_agent -> 403 + 红线文案。"""
    with pytest.raises(HTTPException) as exc_info:
        await create_sub_agent_attempt(db=None, parent_id=1)

    assert exc_info.value.status_code == 403, (
        f"应返回 403，实际 {exc_info.value.status_code}"
    )
    assert "一级分销红线" in str(exc_info.value.detail), "应包含红线文案"
