"""DDW 渠道授权与结算插件业务逻辑。

包含：ClaimService（报备状态机）、CodeSwapService（换码广播）、
PaymentService（支付对账）、SignatureService（电子签管理）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ClaimRecord,
    CodeSwapBroadcast,
    CustomerAssignment,
    DifficultCustomerFlag,
    LicenseCodeInstance,
    PaymentRecord,
    PluginTrial,
    SignatureRequest,
)
from .schemas import (
    ClaimCreateReq,
    LicenseCodeIssueReq,
    PaymentAutoVerifyReq,
    SignatureDispatchReq,
    SwapReq,
)


class ClaimService:
    """报备状态机 V1 实现：claim -> contract -> pay -> 锁定 30 天或释放。"""

    CONTRACT_PRIORITY_DAYS = 7
    LOCK_AFTER_PRIORITY_DAYS = 30

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_claim(self, partner_id: int, req: ClaimCreateReq) -> dict:
        """新建报备 + 同公司 7 天前已有报备 -> 返回历史列表。"""
        existing = await self._find_existing_open_claims(req.company_credit_code)
        claim = ClaimRecord(
            partner_id=partner_id,
            company_full_name=req.company_full_name,
            company_credit_code=req.company_credit_code,
            notes=req.notes,
            state="claimed",
            claimed_at=datetime.utcnow(),
            tenant_id=1,
        )
        self.db.add(claim)
        await self.db.commit()
        await self.db.refresh(claim)
        return {"claim": claim, "history": existing}

    async def get_claim(self, claim_id: int) -> ClaimRecord:
        """获取报备记录。"""
        stmt = select(ClaimRecord).where(ClaimRecord.id == claim_id)
        result = await self.db.execute(stmt)
        claim = result.scalar_one_or_none()
        if claim is None:
            raise ValueError(f"报备记录 {claim_id} 不存在")
        return claim

    async def mark_contract_uploaded(self, claim_id: int, pdf_path: str) -> dict:
        """上传合同 -> 若在公司 7 天窗口内首个上传 = 锁定。"""
        claim = await self.get_claim(claim_id)
        claim.contract_uploaded_at = datetime.utcnow()
        claim.contract_pdf_path = pdf_path
        # 检查是否同公司 7 天内第一个上传
        existing = await self._find_same_company_claims_with_contract(
            claim.company_credit_code, before=claim.contract_uploaded_at
        )
        claim.state = "contract_uploaded"
        is_first = not existing
        if is_first:
            claim.state = "contract_signed"
            await self._lock_customer(claim, lock_reason="contract_first")
        await self.db.commit()
        return {"is_first_to_upload_contract": is_first, "claim": claim}

    async def mark_paid(self, claim_id: int) -> dict:
        """付款到账 -> 锁 + 自动发码。"""
        claim = await self.get_claim(claim_id)
        claim.paid_at = datetime.utcnow()
        claim.state = "paid"
        await self._lock_customer(claim, lock_reason="payment_first")
        await self.db.commit()
        return {"is_first_to_pay": True, "claim": claim}

    async def release_expired(self, claim_id: int) -> dict:
        """30 天无合同 -> 释放（DDW 定时任务调用）。"""
        claim = await self.get_claim(claim_id)
        released = False
        if claim.state == "claimed" and (
            datetime.utcnow() - claim.claimed_at
        ) > timedelta(days=self.LOCK_AFTER_PRIORITY_DAYS):
            claim.state = "released"
            claim.released_at = datetime.utcnow()
            released = True
            await self.db.commit()
        return {"released": released}

    async def list_claims(self, partner_id: Optional[int] = None) -> list[ClaimRecord]:
        """列出报备记录。"""
        stmt = select(ClaimRecord)
        if partner_id is not None:
            stmt = stmt.where(ClaimRecord.partner_id == partner_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _find_existing_open_claims(self, company_credit_code: str) -> list[dict]:
        """查找同公司 7 天内未完结报备。"""
        cutoff = datetime.utcnow() - timedelta(days=self.CONTRACT_PRIORITY_DAYS)
        stmt = (
            select(ClaimRecord)
            .where(
                ClaimRecord.company_credit_code == company_credit_code,
                ClaimRecord.claimed_at >= cutoff,
                ClaimRecord.state.in_(["claimed", "contract_uploaded"]),
            )
            .order_by(ClaimRecord.claimed_at.desc())
        )
        result = await self.db.execute(stmt)
        claims = result.scalars().all()
        return [
            {
                "claim_id": c.id,
                "partner_id": c.partner_id,
                "claimed_at": c.claimed_at,
                "state": c.state,
            }
            for c in claims
        ]

    async def _find_same_company_claims_with_contract(
        self, company_credit_code: str, before: datetime
    ) -> list[ClaimRecord]:
        """查找同公司已上传合同的报备。"""
        cutoff = before - timedelta(days=self.CONTRACT_PRIORITY_DAYS)
        stmt = select(ClaimRecord).where(
            ClaimRecord.company_credit_code == company_credit_code,
            ClaimRecord.contract_uploaded_at.isnot(None),
            ClaimRecord.contract_uploaded_at >= cutoff,
            ClaimRecord.contract_uploaded_at < before,
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _lock_customer(self, claim: ClaimRecord, lock_reason: str) -> None:
        """锁定客户归属。"""
        assignment = CustomerAssignment(
            company_credit_code=claim.company_credit_code,
            company_full_name=claim.company_full_name,
            partner_id=claim.partner_id,
            lock_reason=lock_reason,
            tenant_id=1,
        )
        self.db.add(assignment)


class CodeSwapService:
    """注册码换码 + 网内广播。"""

    GRACE_DAYS = 7

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def swap(self, old_code_id: int, req: SwapReq) -> dict:
        """换码流程：新码 -> 广播 -> 旧码 grace_countdown。"""
        old = await self._get_code(old_code_id)
        new = await self._issue_new_code(req.new_license_id, old.company_id)
        broadcast = CodeSwapBroadcast(
            old_code_id=old.id,
            new_code_id=new.id,
            broadcast_at=datetime.utcnow(),
            grace_until=datetime.utcnow() + timedelta(days=self.GRACE_DAYS),
            ack_nodes_json=[{
                "node_id": "self",
                "sent_at": datetime.utcnow().isoformat(),
            }],
            tenant_id=1,
        )
        old.is_current = False
        old.revoke_status = "grace_countdown"
        old.swap_grace_until = broadcast.grace_until
        new.is_current = True
        new.revoke_status = "active"
        self.db.add(broadcast)
        await self.db.commit()
        return {
            "old_code_id": old.id,
            "new_code_id": new.id,
            "grace_until": broadcast.grace_until,
            "broadcast_id": broadcast.id,
        }

    async def issue(self, req: LicenseCodeIssueReq) -> LicenseCodeInstance:
        """签发新注册码。"""
        code = f"LIC-{uuid.uuid4().hex[:16].upper()}"
        instance = LicenseCodeInstance(
            code=code,
            license_id=req.license_id,
            company_id=req.company_id,
            is_current=True,
            revoke_status="active",
            tenant_id=1,
        )
        self.db.add(instance)
        await self.db.commit()
        await self.db.refresh(instance)
        return instance

    async def activate(self, code_id: int, fingerprint: str) -> LicenseCodeInstance:
        """激活注册码。"""
        code = await self._get_code(code_id)
        code.activated_at = datetime.utcnow()
        code.deployment_fingerprint = fingerprint
        await self.db.commit()
        await self.db.refresh(code)
        return code

    async def re_activate(self, code_id: int) -> LicenseCodeInstance:
        """重新激活。"""
        code = await self._get_code(code_id)
        code.revoke_status = "active"
        code.is_current = True
        await self.db.commit()
        await self.db.refresh(code)
        return code

    async def get_revoke_list(self) -> list[LicenseCodeInstance]:
        """获取吊销列表。"""
        stmt = select(LicenseCodeInstance).where(
            LicenseCodeInstance.revoke_status.in_(["grace_countdown", "revoked"])
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_broadcast_log(self, code_id: int) -> list[dict]:
        """获取换码广播日志。"""
        stmt = (
            select(CodeSwapBroadcast)
            .where(
                (CodeSwapBroadcast.old_code_id == code_id)
                | (CodeSwapBroadcast.new_code_id == code_id)
            )
            .order_by(CodeSwapBroadcast.broadcast_at.desc())
        )
        result = await self.db.execute(stmt)
        broadcasts = result.scalars().all()
        logs = []
        for b in broadcasts:
            for node in (b.ack_nodes_json or []):
                logs.append({
                    "node_id": node.get("node_id", "unknown"),
                    "sent_at": b.broadcast_at,
                    "acked_at": node.get("acked_at"),
                })
        return logs

    async def _get_code(self, code_id: int) -> LicenseCodeInstance:
        """获取注册码实例。"""
        stmt = select(LicenseCodeInstance).where(LicenseCodeInstance.id == code_id)
        result = await self.db.execute(stmt)
        code = result.scalar_one_or_none()
        if code is None:
            raise ValueError(f"注册码 {code_id} 不存在")
        return code

    async def _issue_new_code(
        self, license_id: int, company_id: int,
    ) -> LicenseCodeInstance:
        """生成新注册码。"""
        code = f"LIC-{uuid.uuid4().hex[:16].upper()}"
        instance = LicenseCodeInstance(
            code=code,
            license_id=license_id,
            company_id=company_id,
            is_current=True,
            revoke_status="active",
            tenant_id=1,
        )
        self.db.add(instance)
        await self.db.flush()
        return instance


class PaymentService:
    """支付对账服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def auto_verify(self, req: PaymentAutoVerifyReq) -> PaymentRecord:
        """自动对账：金额比对 + 创建记录。"""
        # V1 mock 签名校验
        if not req.signature:
            raise ValueError("签名不能为空")
        record = PaymentRecord(
            claim_id=req.quote_id,  # 简化：quote_id 映射到 claim_id
            channel=req.channel,
            external_trade_no=req.external_trade_no,
            amount_cents=req.amount_cents,
            quote_amount_cents=req.amount_cents,  # V1 简化
            verified=True,
            tenant_id=1,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get_pending_reconcile(self) -> list[PaymentRecord]:
        """获取待对账列表。"""
        stmt = select(PaymentRecord).where(not PaymentRecord.verified)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def reconcile(self, payment_id: int, reconciled_by: int) -> PaymentRecord:
        """人工对账。"""
        stmt = select(PaymentRecord).where(PaymentRecord.id == payment_id)
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise ValueError(f"支付记录 {payment_id} 不存在")
        record.verified = True
        record.reconciled_by = reconciled_by
        record.reconciled_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(record)
        return record


class SignatureService:
    """电子签管理服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def dispatch(
        self,
        req: SignatureDispatchReq,
        claim_id: Optional[int] = None,
    ) -> SignatureRequest:
        """发起电子签。"""
        from .signature_adapters import ADAPTERS

        adapter = ADAPTERS.get(req.provider)
        if adapter is None:
            raise ValueError(f"不支持的电子签供应商: {req.provider}")
        result = await adapter.create_request(
            req.document_name, req.signers, req.callback_url,
        )
        sig = SignatureRequest(
            claim_id=claim_id,
            provider=req.provider,
            status="pending",
            external_request_id=result.get("external_request_id"),
            document_name=req.document_name,
            signers_json=req.signers,
            callback_url=req.callback_url,
            tenant_id=1,
        )
        self.db.add(sig)
        await self.db.commit()
        await self.db.refresh(sig)
        return sig

    async def get_signature(self, sig_id: int) -> SignatureRequest:
        """获取电子签请求。"""
        stmt = select(SignatureRequest).where(SignatureRequest.id == sig_id)
        result = await self.db.execute(stmt)
        sig = result.scalar_one_or_none()
        if sig is None:
            raise ValueError(f"电子签请求 {sig_id} 不存在")
        return sig

    async def complete_signature(self, sig_id: int) -> SignatureRequest:
        """标记签名完成。"""
        sig = await self.get_signature(sig_id)
        sig.status = "completed"
        sig.completed_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(sig)
        return sig


class TrialService:
    """试用期管理服务。"""

    TRIAL_DAYS = 30

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def start_trial(self, plugin_id: str, tenant_id: int) -> PluginTrial:
        """启动 30 天试用。"""
        now = datetime.utcnow()
        trial = PluginTrial(
            plugin_id=plugin_id,
            tenant_id_trial=tenant_id,
            started_at=now,
            expires_at=now + timedelta(days=self.TRIAL_DAYS),
            status="active",
            tenant_id=1,
        )
        self.db.add(trial)
        await self.db.commit()
        await self.db.refresh(trial)
        return trial

    async def get_trial(self, plugin_id: str, tenant_id: int) -> Optional[PluginTrial]:
        """获取当前试用。"""
        stmt = select(PluginTrial).where(
            PluginTrial.plugin_id == plugin_id,
            PluginTrial.tenant_id_trial == tenant_id,
            PluginTrial.status == "active",
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_available(self, tenant_id: int) -> list[PluginTrial]:
        """列出可用试用。"""
        stmt = select(PluginTrial).where(
            PluginTrial.tenant_id_trial == tenant_id,
            PluginTrial.status == "active",
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def cancel_trial(self, plugin_id: str, tenant_id: int) -> PluginTrial:
        """取消试用。"""
        trial = await self.get_trial(plugin_id, tenant_id)
        if trial is None:
            raise ValueError(f"试用 {plugin_id} 不存在")
        trial.status = "cancelled"
        await self.db.commit()
        await self.db.refresh(trial)
        return trial

    async def get_metrics(self, plugin_id: str, tenant_id: int) -> dict:
        """获取试用指标（mock）。"""
        trial = await self.get_trial(plugin_id, tenant_id)
        if trial is None:
            raise ValueError(f"试用 {plugin_id} 不存在")
        invocation_count = 42
        hours_saved = invocation_count * 0.25
        return {
            "plugin_id": plugin_id,
            "invocation_count": invocation_count,
            "work_orders_processed": 15,
            "estimated_hours_saved": hours_saved,
            "estimated_labor_cost_saved_cents": int(hours_saved * 50 * 100),
        }


class DifficultCustomerService:
    """难缠客户标记服务。"""

    FLAG_THRESHOLD = 3
    FLAG_SPAN_MONTHS = 6

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def flag_customer(
        self,
        company_credit_code: str,
        reason: Optional[str] = None,
    ) -> DifficultCustomerFlag:
        """标记难缠客户。"""
        stmt = select(DifficultCustomerFlag).where(
            DifficultCustomerFlag.company_credit_code == company_credit_code
        )
        result = await self.db.execute(stmt)
        flag = result.scalar_one_or_none()
        if flag is None:
            flag = DifficultCustomerFlag(
                company_credit_code=company_credit_code,
                flag_count=1,
                reason=reason,
                tenant_id=1,
            )
            self.db.add(flag)
        else:
            flag.flag_count += 1
            flag.last_flagged_at = datetime.utcnow()
            if reason:
                flag.reason = reason
        await self.db.commit()
        await self.db.refresh(flag)
        return flag
