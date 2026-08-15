"""DDW 渠道授权与结算插件 API 路由。

30 个端点，前缀：/api/v1/plugins/ddw-channel-auth
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from core.database.session import session_scope

from .schemas import (
    BannerSeenReq,
    BroadcastLogItem,
    ClaimCreateReq,
    ClaimHistoryItem,
    ClaimResp,
    LicenseCodeIssueReq,
    LicenseCodeResp,
    PartnerMeResp,
    PaymentAutoVerifyReq,
    PaymentRecordResp,
    SignatureDispatchReq,
    SignatureResp,
    SwapReq,
    TrialMetricsResp,
    TrialResp,
)
from .services import (
    ClaimService,
    CodeSwapService,
    DifficultCustomerService,
    PaymentService,
    SignatureService,
    TrialService,
)

logger = logging.getLogger(__name__)

# 模拟当前合作伙伴 ID（V1 简化，V2 走 JWT）
_MOCK_PARTNER_ID = 1
_MOCK_TENANT_ID = 1


def build_router() -> APIRouter:
    """构造渠道授权路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-channel-auth",
        tags=["ddw-channel-auth"],
    )

    # =======================================================================
    # 健康检查
    # =======================================================================

    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-channel-auth", "version": "1.0.0", "status": "ok"}

    # =======================================================================
    # accounts 账号
    # =======================================================================

    @router.get("/accounts/me", response_model=PartnerMeResp)
    async def accounts_me() -> PartnerMeResp:
        """获取当前合作伙伴信息。"""
        from sqlalchemy import select
        from .models import ChannelPartner

        async with session_scope() as db:
            stmt = select(ChannelPartner).where(ChannelPartner.id == _MOCK_PARTNER_ID)
            result = await db.execute(stmt)
            partner = result.scalar_one_or_none()
            if partner is None:
                raise HTTPException(status_code=404, detail="合作伙伴不存在")
            return PartnerMeResp(
                id=partner.id,
                name=partner.name,
                type=partner.partner_type,
                parent_partner_id=partner.parent_partner_id,
                banner_required=partner.banner_required,
                contract_signed_at=partner.contract_signed_at,
            )

    @router.post("/accounts/{partner_id}/banner/seen")
    async def banner_seen(partner_id: int, req: BannerSeenReq) -> dict:
        """确认横幅已读。"""
        from sqlalchemy import select
        from .models import ChannelPartner

        async with session_scope() as db:
            stmt = select(ChannelPartner).where(ChannelPartner.id == partner_id)
            result = await db.execute(stmt)
            partner = result.scalar_one_or_none()
            if partner is None:
                raise HTTPException(status_code=404, detail="合作伙伴不存在")
            partner.banner_required = False
            partner.banner_ack_version = req.ack_version
            await db.commit()
            return {"ok": True}

    @router.get("/accounts/banner/check")
    async def banner_check() -> dict:
        """检查横幅状态。"""
        from sqlalchemy import select
        from .models import ChannelPartner

        async with session_scope() as db:
            stmt = select(ChannelPartner).where(ChannelPartner.id == _MOCK_PARTNER_ID)
            result = await db.execute(stmt)
            partner = result.scalar_one_or_none()
            if partner is None:
                return {"banner_required": False}
            return {"banner_required": partner.banner_required}

    # =======================================================================
    # claims 报备
    # =======================================================================

    @router.post("/claims", response_model=ClaimResp, status_code=201)
    async def create_claim(req: ClaimCreateReq) -> ClaimResp:
        """新建客户报备。"""
        async with session_scope() as db:
            svc = ClaimService(db)
            try:
                result = await svc.create_claim(_MOCK_PARTNER_ID, req)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            claim = result["claim"]
            return ClaimResp(
                id=claim.id,
                company_full_name=claim.company_full_name,
                company_credit_code=claim.company_credit_code,
                partner_id=claim.partner_id,
                state=claim.state,
                claimed_at=claim.claimed_at,
            )

    @router.get("/claims", response_model=list[ClaimResp])
    async def list_claims(
        partner_id: Optional[int] = Query(None, description="按合作伙伴筛选"),
    ) -> list[ClaimResp]:
        """列出报备记录。"""
        async with session_scope() as db:
            svc = ClaimService(db)
            claims = await svc.list_claims(partner_id)
            return [
                ClaimResp(
                    id=c.id,
                    company_full_name=c.company_full_name,
                    company_credit_code=c.company_credit_code,
                    partner_id=c.partner_id,
                    state=c.state,
                    claimed_at=c.claimed_at,
                    contract_uploaded_at=c.contract_uploaded_at,
                    paid_at=c.paid_at,
                    released_at=c.released_at,
                )
                for c in claims
            ]

    @router.get("/claims/{claim_id}", response_model=ClaimResp)
    async def get_claim(claim_id: int) -> ClaimResp:
        """获取单条报备。"""
        async with session_scope() as db:
            svc = ClaimService(db)
            try:
                claim = await svc.get_claim(claim_id)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return ClaimResp(
                id=claim.id,
                company_full_name=claim.company_full_name,
                company_credit_code=claim.company_credit_code,
                partner_id=claim.partner_id,
                state=claim.state,
                claimed_at=claim.claimed_at,
                contract_uploaded_at=claim.contract_uploaded_at,
                paid_at=claim.paid_at,
                released_at=claim.released_at,
            )

    @router.post("/claims/{claim_id}/upload-contract")
    async def upload_contract(claim_id: int, file: UploadFile = File(...)) -> dict:
        """上传合同（PDF/JPG ≤10MB）。"""
        if file.content_type not in ("application/pdf", "image/jpeg", "image/png"):
            raise HTTPException(status_code=422, detail="仅支持 PDF/JPG/PNG")
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=422, detail="文件大小不能超过 10MB")
        # 保存到临时目录
        suffix = ".pdf" if file.content_type == "application/pdf" else ".jpg"
        fd, path = tempfile.mkstemp(suffix=suffix, prefix="ddw_contract_")
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        async with session_scope() as db:
            svc = ClaimService(db)
            try:
                result = await svc.mark_contract_uploaded(claim_id, path)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {
                "is_first_to_upload_contract": result["is_first_to_upload_contract"],
                "claim_id": claim_id,
            }

    @router.post("/claims/{claim_id}/sign-auth-contract")
    async def sign_auth_contract(claim_id: int) -> dict:
        """签署授权合同（标记合同已签）。"""
        async with session_scope() as db:
            svc = ClaimService(db)
            try:
                claim = await svc.get_claim(claim_id)
                claim.state = "contract_signed"
                await db.commit()
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {"claim_id": claim_id, "state": "contract_signed"}

    @router.post("/claims/{claim_id}/pay")
    async def pay_claim(claim_id: int) -> dict:
        """报备付款。"""
        async with session_scope() as db:
            svc = ClaimService(db)
            try:
                result = await svc.mark_paid(claim_id)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {"is_first_to_pay": result["is_first_to_pay"], "claim_id": claim_id}

    @router.post("/claims/{claim_id}/release")
    async def release_claim(claim_id: int) -> dict:
        """释放报备（30 天无合同自动释放）。"""
        async with session_scope() as db:
            svc = ClaimService(db)
            try:
                result = await svc.release_expired(claim_id)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {"released": result["released"], "claim_id": claim_id}

    @router.get("/claims/{claim_id}/history", response_model=list[ClaimHistoryItem])
    async def claim_history(claim_id: int) -> list[ClaimHistoryItem]:
        """获取报备历史。"""
        from sqlalchemy import select
        from .models import ClaimRecord, ChannelPartner

        async with session_scope() as db:
            claim_stmt = select(ClaimRecord).where(ClaimRecord.id == claim_id)
            claim_result = await db.execute(claim_stmt)
            claim = claim_result.scalar_one_or_none()
            if claim is None:
                raise HTTPException(status_code=404, detail="报备不存在")
            # 查找同公司历史
            stmt = (
                select(ClaimRecord, ChannelPartner)
                .join(ChannelPartner, ClaimRecord.partner_id == ChannelPartner.id)
                .where(ClaimRecord.company_credit_code == claim.company_credit_code)
                .order_by(ClaimRecord.claimed_at.desc())
            )
            result = await db.execute(stmt)
            rows = result.all()
            items = []
            for c, p in rows:
                outcome = "won" if c.state in ("contract_signed", "paid") else (
                    "released" if c.state == "released" else "pending"
                )
                items.append(ClaimHistoryItem(
                    claim_id=c.id,
                    partner_name=p.name,
                    claimed_at=c.claimed_at,
                    outcome=outcome,
                ))
            return items

    @router.post("/difficult-customers/{company_id}/flag")
    async def flag_difficult_customer(
        company_id: int, reason: Optional[str] = None,
    ) -> dict:
        """标记难缠客户。"""
        from sqlalchemy import select
        from .models import ClaimRecord

        async with session_scope() as db:
            # 通过 company_id 查找 credit_code
            claim_stmt = select(ClaimRecord).where(ClaimRecord.id == company_id)
            claim_result = await db.execute(claim_stmt)
            claim = claim_result.scalar_one_or_none()
            if claim is None:
                raise HTTPException(status_code=404, detail="客户不存在")
            svc = DifficultCustomerService(db)
            flag = await svc.flag_customer(claim.company_credit_code, reason)
            return {"flagged": True, "flag_count": flag.flag_count}

    # =======================================================================
    # signatures 电子签
    # =======================================================================

    @router.get("/signatures/providers")
    async def signature_providers() -> dict:
        """列出支持的电子签供应商。"""
        from .signature_adapters import ADAPTERS
        return {"providers": list(ADAPTERS.keys())}

    @router.post("/signatures/dispatch", response_model=SignatureResp, status_code=201)
    async def dispatch_signature(req: SignatureDispatchReq) -> SignatureResp:
        """发起电子签。"""
        async with session_scope() as db:
            svc = SignatureService(db)
            try:
                sig = await svc.dispatch(req)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return SignatureResp(
                id=sig.id,
                provider=sig.provider,
                status=sig.status,
                external_request_id=sig.external_request_id,
                document_name=sig.document_name,
                completed_at=sig.completed_at,
            )

    @router.get("/signatures/{sig_id}", response_model=SignatureResp)
    async def get_signature(sig_id: int) -> SignatureResp:
        """获取电子签请求。"""
        async with session_scope() as db:
            svc = SignatureService(db)
            try:
                sig = await svc.get_signature(sig_id)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return SignatureResp(
                id=sig.id,
                provider=sig.provider,
                status=sig.status,
                external_request_id=sig.external_request_id,
                document_name=sig.document_name,
                completed_at=sig.completed_at,
            )

    @router.post("/signatures/{sig_id}/callback/{provider}")
    async def signature_callback(
        sig_id: int, provider: str, payload: dict = {},
    ) -> dict:
        """电子签回调。"""
        async with session_scope() as db:
            svc = SignatureService(db)
            try:
                await svc.complete_signature(sig_id)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {"status": "completed", "signature_id": sig_id}

    @router.post("/signatures/{sig_id}/manual-upload")
    async def manual_upload_signature(
        sig_id: int, file: UploadFile = File(...),
    ) -> dict:
        """手动上传已签文件。"""
        if file.content_type not in ("application/pdf",):
            raise HTTPException(status_code=422, detail="仅支持 PDF")
        content = await file.read()
        fd, path = tempfile.mkstemp(suffix=".pdf", prefix="ddw_signed_")
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        async with session_scope() as db:
            svc = SignatureService(db)
            try:
                sig = await svc.get_signature(sig_id)
                sig.signed_pdf_path = path
                sig.status = "completed"
                sig.completed_at = datetime.utcnow()
                await db.commit()
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {"status": "completed", "signature_id": sig_id}

    # =======================================================================
    # payments 支付
    # =======================================================================

    @router.post(
        "/payments/auto-verify",
        response_model=PaymentRecordResp,
        status_code=201,
    )
    async def auto_verify_payment(req: PaymentAutoVerifyReq) -> PaymentRecordResp:
        """自动对账。"""
        async with session_scope() as db:
            svc = PaymentService(db)
            try:
                record = await svc.auto_verify(req)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
            return PaymentRecordResp(
                id=record.id,
                claim_id=record.claim_id,
                channel=record.channel,
                amount_cents=record.amount_cents,
                quote_amount_cents=record.quote_amount_cents,
                verified=record.verified,
                reconciled_by=record.reconciled_by,
                reconciled_at=record.reconciled_at,
                license_code_id=record.license_code_id,
            )

    @router.get("/payments/pending-reconcile", response_model=list[PaymentRecordResp])
    async def pending_reconcile() -> list[PaymentRecordResp]:
        """获取待对账列表。"""
        async with session_scope() as db:
            svc = PaymentService(db)
            records = await svc.get_pending_reconcile()
            return [
                PaymentRecordResp(
                    id=r.id,
                    claim_id=r.claim_id,
                    channel=r.channel,
                    amount_cents=r.amount_cents,
                    quote_amount_cents=r.quote_amount_cents,
                    verified=r.verified,
                    reconciled_by=r.reconciled_by,
                    reconciled_at=r.reconciled_at,
                    license_code_id=r.license_code_id,
                )
                for r in records
            ]

    @router.post("/payments/{payment_id}/reconcile", response_model=PaymentRecordResp)
    async def reconcile_payment(payment_id: int) -> PaymentRecordResp:
        """人工对账。"""
        async with session_scope() as db:
            svc = PaymentService(db)
            try:
                record = await svc.reconcile(payment_id, reconciled_by=_MOCK_PARTNER_ID)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return PaymentRecordResp(
                id=record.id,
                claim_id=record.claim_id,
                channel=record.channel,
                amount_cents=record.amount_cents,
                quote_amount_cents=record.quote_amount_cents,
                verified=record.verified,
                reconciled_by=record.reconciled_by,
                reconciled_at=record.reconciled_at,
                license_code_id=record.license_code_id,
            )

    # =======================================================================
    # license_codes 注册码
    # =======================================================================

    @router.post(
        "/license-codes/issue",
        response_model=LicenseCodeResp,
        status_code=201,
    )
    async def issue_license_code(req: LicenseCodeIssueReq) -> LicenseCodeResp:
        """签发注册码。"""
        async with session_scope() as db:
            svc = CodeSwapService(db)
            instance = await svc.issue(req)
            return LicenseCodeResp(
                id=instance.id,
                code=instance.code,
                license_id=instance.license_id,
                company_id=instance.company_id,
                deployment_fingerprint=instance.deployment_fingerprint,
                activated_at=instance.activated_at,
                valid_to=instance.valid_to,
                is_current=instance.is_current,
                swap_grace_until=instance.swap_grace_until,
                revoke_status=instance.revoke_status,
            )

    @router.post("/license-codes/{code_id}/activate", response_model=LicenseCodeResp)
    async def activate_license_code(
        code_id: int, fingerprint: str = Query(...),
    ) -> LicenseCodeResp:
        """激活注册码。"""
        async with session_scope() as db:
            svc = CodeSwapService(db)
            try:
                instance = await svc.activate(code_id, fingerprint)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return LicenseCodeResp(
                id=instance.id,
                code=instance.code,
                license_id=instance.license_id,
                company_id=instance.company_id,
                deployment_fingerprint=instance.deployment_fingerprint,
                activated_at=instance.activated_at,
                valid_to=instance.valid_to,
                is_current=instance.is_current,
                swap_grace_until=instance.swap_grace_until,
                revoke_status=instance.revoke_status,
            )

    @router.post("/license-codes/{code_id}/swap", status_code=201)
    async def swap_license_code(code_id: int, req: SwapReq) -> dict:
        """换码。"""
        async with session_scope() as db:
            svc = CodeSwapService(db)
            try:
                result = await svc.swap(code_id, req)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return result

    @router.get("/license-codes/revoke-list", response_model=list[LicenseCodeResp])
    async def revoke_list() -> list[LicenseCodeResp]:
        """获取吊销列表。"""
        async with session_scope() as db:
            svc = CodeSwapService(db)
            codes = await svc.get_revoke_list()
            return [
                LicenseCodeResp(
                    id=c.id,
                    code=c.code,
                    license_id=c.license_id,
                    company_id=c.company_id,
                    deployment_fingerprint=c.deployment_fingerprint,
                    activated_at=c.activated_at,
                    valid_to=c.valid_to,
                    is_current=c.is_current,
                    swap_grace_until=c.swap_grace_until,
                    revoke_status=c.revoke_status,
                )
                for c in codes
            ]

    @router.post("/license-codes/{code_id}/re-activate", response_model=LicenseCodeResp)
    async def re_activate_license_code(code_id: int) -> LicenseCodeResp:
        """重新激活注册码。"""
        async with session_scope() as db:
            svc = CodeSwapService(db)
            try:
                instance = await svc.re_activate(code_id)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return LicenseCodeResp(
                id=instance.id,
                code=instance.code,
                license_id=instance.license_id,
                company_id=instance.company_id,
                deployment_fingerprint=instance.deployment_fingerprint,
                activated_at=instance.activated_at,
                valid_to=instance.valid_to,
                is_current=instance.is_current,
                swap_grace_until=instance.swap_grace_until,
                revoke_status=instance.revoke_status,
            )

    @router.get(
        "/license-codes/{code_id}/broadcast-log",
        response_model=list[BroadcastLogItem],
    )
    async def broadcast_log(code_id: int) -> list[BroadcastLogItem]:
        """获取换码广播日志。"""
        async with session_scope() as db:
            svc = CodeSwapService(db)
            try:
                logs = await svc.get_broadcast_log(code_id)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return [
                BroadcastLogItem(
                    node_id=log["node_id"],
                    sent_at=log["sent_at"],
                    acked_at=log.get("acked_at"),
                )
                for log in logs
            ]

    # =======================================================================
    # trials 试用
    # =======================================================================

    @router.get("/trials/available", response_model=list[TrialResp])
    async def trials_available() -> list[TrialResp]:
        """列出可用试用。"""
        async with session_scope() as db:
            svc = TrialService(db)
            trials = await svc.list_available(_MOCK_TENANT_ID)
            return [
                TrialResp(
                    id=t.id,
                    plugin_id=t.plugin_id,
                    started_at=t.started_at,
                    expires_at=t.expires_at,
                    days_remaining=max(0, (t.expires_at - datetime.utcnow()).days),
                    status=t.status,
                    poc_report_doc_path=t.poc_report_doc_path,
                    poc_report_pdf_path=t.poc_report_pdf_path,
                )
                for t in trials
            ]

    @router.post("/trials/{plugin_id}/start", response_model=TrialResp, status_code=201)
    async def start_trial(plugin_id: str) -> TrialResp:
        """启动 30 天试用。"""
        async with session_scope() as db:
            svc = TrialService(db)
            trial = await svc.start_trial(plugin_id, _MOCK_TENANT_ID)
            return TrialResp(
                id=trial.id,
                plugin_id=trial.plugin_id,
                started_at=trial.started_at,
                expires_at=trial.expires_at,
                days_remaining=30,
                status=trial.status,
            )

    @router.get("/trials/me", response_model=Optional[TrialResp])
    async def trials_me() -> Optional[TrialResp]:
        """获取当前试用。"""
        async with session_scope() as db:
            svc = TrialService(db)
            # V1 返回第一个活跃试用
            trials = await svc.list_available(_MOCK_TENANT_ID)
            if not trials:
                return None
            t = trials[0]
            return TrialResp(
                id=t.id,
                plugin_id=t.plugin_id,
                started_at=t.started_at,
                expires_at=t.expires_at,
                days_remaining=max(0, (t.expires_at - datetime.utcnow()).days),
                status=t.status,
                poc_report_doc_path=t.poc_report_doc_path,
                poc_report_pdf_path=t.poc_report_pdf_path,
            )

    @router.post("/trials/{plugin_id}/cancel")
    async def cancel_trial(plugin_id: str) -> dict:
        """取消试用。"""
        async with session_scope() as db:
            svc = TrialService(db)
            try:
                await svc.cancel_trial(plugin_id, _MOCK_TENANT_ID)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {"cancelled": True, "plugin_id": plugin_id}

    @router.post("/trials/{plugin_id}/generate-poc-report")
    async def generate_poc_report(plugin_id: str) -> dict:
        """生成 POC 报告。"""
        async with session_scope() as db:
            svc = TrialService(db)
            trial = await svc.get_trial(plugin_id, _MOCK_TENANT_ID)
            if trial is None:
                raise HTTPException(status_code=404, detail="试用不存在")
            metrics = await svc.get_metrics(plugin_id, _MOCK_TENANT_ID)
            from .trial_poc import render_poc_docx, render_poc_pdf

            pdf_bytes = render_poc_pdf(trial, metrics)
            docx_bytes = render_poc_docx(trial, metrics)
            # 保存到临时目录
            pdf_path = tempfile.mktemp(suffix=".pdf", prefix="ddw_poc_")
            docx_path = tempfile.mktemp(suffix=".docx", prefix="ddw_poc_")
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            with open(docx_path, "wb") as f:
                f.write(docx_bytes)
            trial.poc_report_pdf_path = pdf_path
            trial.poc_report_doc_path = docx_path
            await db.commit()
            return {"pdf_path": pdf_path, "docx_path": docx_path}

    @router.get("/trials/{plugin_id}/metrics", response_model=TrialMetricsResp)
    async def trial_metrics(plugin_id: str) -> TrialMetricsResp:
        """获取试用指标。"""
        async with session_scope() as db:
            svc = TrialService(db)
            try:
                metrics = await svc.get_metrics(plugin_id, _MOCK_TENANT_ID)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return TrialMetricsResp(**metrics)

    # =======================================================================
    # portal 门户
    # =======================================================================

    @router.get("/portal/banner")
    async def portal_banner() -> dict:
        """获取门户横幅。"""
        return {
            "title": "一级分销红线提醒",
            "content": "DDW 渠道体系仅限一级分销，禁止发展下级分销商。",
            "version": "v1",
        }

    @router.get("/portal/dashboard")
    async def portal_dashboard() -> dict:
        """获取门户仪表盘。"""
        return {
            "partner_id": _MOCK_PARTNER_ID,
            "summary": {
                "total_claims": 0,
                "active_trials": 0,
                "pending_payments": 0,
            },
        }

    return router


# ---------------------------------------------------------------------------
# 一级分销红线：禁止发展下级分销
# ---------------------------------------------------------------------------


async def create_sub_agent_attempt(db, parent_id: int):
    """铁律：禁止任何下级分销入口。"""
    raise HTTPException(
        status_code=403,
        detail="一级分销红线：禁止发展下级分销（DDW 渠道体系仅一级）",
    )
