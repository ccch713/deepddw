"""DDW 渠道授权与结算插件 — 注册码换码测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_channel_auth.schemas import LicenseCodeIssueReq, SwapReq
from plugins.ddw_channel_auth.services import CodeSwapService


@pytest.mark.anyio
async def test_swap_broadcast_marks_old_code_grace_then_revoked(db: AsyncSession):
    """发新码 -> swap -> 断言旧码 swap_grace_until != None
    + revoke_status='grace_countdown'。"""
    svc = CodeSwapService(db)

    # 签发旧码
    old_req = LicenseCodeIssueReq(license_id=100, company_id=200)
    old_code = await svc.issue(old_req)
    assert old_code.revoke_status == "active", "新签发码应为 active"
    assert old_code.is_current is True

    # 签发新码（作为 swap 的新码）
    new_req = LicenseCodeIssueReq(license_id=101, company_id=200)
    await svc.issue(new_req)

    # 执行换码
    swap_req = SwapReq(new_license_id=101)
    result = await svc.swap(old_code.id, swap_req)

    # 断言旧码状态
    old_after = await svc._get_code(old_code.id)
    assert old_after.swap_grace_until is not None, "旧码 swap_grace_until 应不为 None"
    assert old_after.revoke_status == "grace_countdown", "旧码应为 grace_countdown"
    assert old_after.is_current is False, "旧码 is_current 应为 False"

    # 断言新码状态
    new_after = await svc._get_code(result["new_code_id"])
    assert new_after.is_current is True, "新码 is_current 应为 True"
    assert new_after.revoke_status == "active", "新码应为 active"

    # 断言广播记录
    assert result["old_code_id"] == old_code.id
    assert result["new_code_id"] != old_code.id
