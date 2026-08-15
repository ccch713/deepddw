"""DDW 渠道授权与结算插件 — 试用期测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_channel_auth.services import TrialService


@pytest.mark.anyio
async def test_trial_starts_30_days_full_features(db: AsyncSession):
    """POST /trials/{plugin_id}/start -> 断言 days_remaining=30。"""
    svc = TrialService(db)
    trial = await svc.start_trial("ddw-test-plugin", tenant_id=1)

    assert trial.plugin_id == "ddw-test-plugin"
    assert trial.status == "active"
    # 验证过期时间约 30 天后
    delta = trial.expires_at - trial.started_at
    assert delta.days == 30, f"试用期应为 30 天，实际 {delta.days} 天"


@pytest.mark.anyio
async def test_poc_report_generates_pdf_and_docx_locally(db: AsyncSession):
    """PDF + DOCX 非空字节。"""
    svc = TrialService(db)
    trial = await svc.start_trial("ddw-poc-plugin", tenant_id=1)
    metrics = await svc.get_metrics("ddw-poc-plugin", tenant_id=1)

    from plugins.ddw_channel_auth.trial_poc import render_poc_docx, render_poc_pdf

    pdf_bytes = render_poc_pdf(trial, metrics)
    docx_bytes = render_poc_docx(trial, metrics)

    assert len(pdf_bytes) > 1000, f"PDF 字节数应 > 1000，实际 {len(pdf_bytes)}"
    assert len(docx_bytes) > 1000, f"DOCX 字节数应 > 1000，实际 {len(docx_bytes)}"
    assert pdf_bytes[:4] == b"%PDF", "PDF 应以 %PDF 开头"
    assert docx_bytes[:2] == b"PK", "DOCX 应以 PK 开头（ZIP 格式）"
