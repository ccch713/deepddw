"""DDW 渠道授权与结算插件 ORM 模型（七张表）。

全部继承 core.database.models.Base / TenantMixin / TimestampMixin，
使用 SQLAlchemy 2.0 Mapped[] + mapped_column() 语法。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Date,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

BigInt = BigInteger().with_variant(Integer(), "sqlite")


class ChannelPartner(Base, TenantMixin, TimestampMixin):
    """渠道合作伙伴账号。"""

    __tablename__ = "ca_channel_partners"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    partner_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="personal"
    )  # personal / company
    parent_partner_id: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    banner_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    banner_ack_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    contract_signed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )


class CustomerAssignment(Base, TenantMixin, TimestampMixin):
    """客户归属分配（锁定关系）。"""

    __tablename__ = "ca_customer_assignments"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    company_credit_code: Mapped[str] = mapped_column(
        String(18), nullable=False, index=True
    )
    company_full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    partner_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("ca_channel_partners.id"),
        nullable=False, index=True,
    )
    locked_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    lock_reason: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # contract_first / payment_first


class ClaimRecord(Base, TenantMixin, TimestampMixin):
    """客户报备记录 + 状态机。"""

    __tablename__ = "ca_claim_records"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    company_full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_credit_code: Mapped[str] = mapped_column(
        String(18), nullable=False, index=True
    )
    partner_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("ca_channel_partners.id"),
        nullable=False, index=True,
    )
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="claimed")
    # claimed / contract_uploaded / contract_signed / paid / released / archived
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    contract_uploaded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    contract_pdf_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DifficultCustomerFlag(Base, TenantMixin, TimestampMixin):
    """难缠客户标记。"""

    __tablename__ = "ca_difficult_customer_flags"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    company_credit_code: Mapped[str] = mapped_column(
        String(18), nullable=False, index=True
    )
    flag_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_flagged_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    last_flagged_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SignatureRequest(Base, TenantMixin, TimestampMixin):
    """电子签请求。"""

    __tablename__ = "ca_signature_requests"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    claim_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("ca_claim_records.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # pending / signing / completed / failed
    external_request_id: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    document_name: Mapped[str] = mapped_column(String(200), nullable=False)
    signers_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    callback_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    signed_pdf_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class PaymentRecord(Base, TenantMixin, TimestampMixin):
    """支付记录。"""

    __tablename__ = "ca_payment_records"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    claim_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("ca_claim_records.id"),
        nullable=False, index=True,
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # alipay / wechat
    external_trade_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reconciled_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    reconciled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    license_code_id: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)


class LicenseCodeInstance(Base, TenantMixin, TimestampMixin):
    """注册码实例。"""

    __tablename__ = "ca_license_code_instances"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    license_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    company_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    deployment_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    swap_grace_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    revoke_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    # active / grace_countdown / revoked


class CodeSwapBroadcast(Base, TenantMixin, TimestampMixin):
    """换码广播日志。"""

    __tablename__ = "ca_code_swap_broadcasts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    old_code_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("ca_license_code_instances.id"),
        nullable=False,
    )
    new_code_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("ca_license_code_instances.id"),
        nullable=False,
    )
    broadcast_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    grace_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ack_nodes_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)


class PluginTrial(Base, TenantMixin, TimestampMixin):
    """插件试用记录。"""

    __tablename__ = "ca_plugin_trials"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    plugin_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tenant_id_trial: Mapped[int] = mapped_column(BigInt, nullable=False)  # 试用租户
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # active / expired / cancelled
    poc_report_doc_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    poc_report_pdf_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
