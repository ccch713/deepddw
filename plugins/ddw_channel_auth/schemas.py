"""DDW 渠道授权与结算插件 Pydantic 请求/响应模型（V1 必备 12 个）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 1. 账号
# ---------------------------------------------------------------------------

class PartnerMeResp(BaseModel):
    """合作伙伴自身信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str  # "personal" / "company"
    parent_partner_id: Optional[int] = None
    banner_required: bool
    contract_signed_at: Optional[datetime] = None


class BannerSeenReq(BaseModel):
    """确认横幅已读。"""

    ack_version: str


# ---------------------------------------------------------------------------
# 2. 报备
# ---------------------------------------------------------------------------

class ClaimCreateReq(BaseModel):
    """新建客户报备。"""

    company_full_name: str = Field(..., min_length=4, max_length=100)
    company_credit_code: str = Field(..., pattern=r"^[0-9A-HJ-NPQRTUWXY]{18}$")
    notes: Optional[str] = None


class ClaimResp(BaseModel):
    """报备记录响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_full_name: str
    company_credit_code: str
    partner_id: int
    state: str
    claimed_at: datetime
    contract_uploaded_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    is_first_to_upload_contract: bool = False
    is_first_to_pay: bool = False


class ClaimHistoryItem(BaseModel):
    """报备历史条目。"""

    claim_id: int
    partner_name: str
    claimed_at: datetime
    outcome: str  # won / released / pending


# ---------------------------------------------------------------------------
# 3. 电子签
# ---------------------------------------------------------------------------

class SignatureDispatchReq(BaseModel):
    """发起电子签。"""

    provider: str
    document_name: str
    signers: List[dict]
    callback_url: str


class SignatureResp(BaseModel):
    """电子签响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    status: str
    external_request_id: Optional[str] = None
    document_name: str
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# 4. 支付
# ---------------------------------------------------------------------------

class PaymentAutoVerifyReq(BaseModel):
    """自动对账请求。"""

    external_trade_no: str
    amount_cents: int
    quote_id: int
    channel: str
    signature: str


class PaymentRecordResp(BaseModel):
    """支付记录响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: int
    channel: str
    amount_cents: int
    quote_amount_cents: int
    verified: bool
    reconciled_by: Optional[int] = None
    reconciled_at: Optional[datetime] = None
    license_code_id: Optional[int] = None


# ---------------------------------------------------------------------------
# 5. 注册码 + 换码
# ---------------------------------------------------------------------------

class LicenseCodeIssueReq(BaseModel):
    """签发注册码。"""

    license_id: int
    company_id: int


class LicenseCodeResp(BaseModel):
    """注册码响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    license_id: int
    company_id: int
    deployment_fingerprint: Optional[str] = None
    activated_at: Optional[datetime] = None
    valid_to: Optional[date] = None
    is_current: bool
    swap_grace_until: Optional[datetime] = None
    revoke_status: str


class SwapReq(BaseModel):
    """换码请求。"""

    new_license_id: int


class BroadcastLogItem(BaseModel):
    """广播日志条目。"""

    node_id: str
    sent_at: datetime
    acked_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# 6. 试用
# ---------------------------------------------------------------------------

class TrialStartReq(BaseModel):
    """启动试用。"""

    plugin_id: str = Field(..., pattern=r"^ddw-[a-z][a-z0-9-]*$")


class TrialResp(BaseModel):
    """试用响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    plugin_id: str
    started_at: datetime
    expires_at: datetime
    days_remaining: int
    status: str
    poc_report_doc_path: Optional[str] = None
    poc_report_pdf_path: Optional[str] = None


class TrialMetricsResp(BaseModel):
    """试用指标响应。"""

    plugin_id: str
    invocation_count: int
    work_orders_processed: int
    estimated_hours_saved: float
    estimated_labor_cost_saved_cents: int
