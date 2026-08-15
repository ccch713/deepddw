"""SQLAlchemy ORM and Pydantic models for ESG payment plugin."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship

# ---------------------------------------------------------------------------
# SQLAlchemy ORM
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "esg_orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(64), nullable=False, index=True)
    plan_id = Column(String(32), nullable=False)
    original_amount = Column(Integer, nullable=False)
    discount_amount = Column(Integer, default=0)
    coupon_amount = Column(Integer, default=0)
    final_amount = Column(Integer, nullable=False)
    currency = Column(String(8), default="CNY")
    pay_method = Column(String(16))
    trade_no = Column(String(64), unique=True)
    provider_trade_no = Column(String(128))
    status = Column(String(16), default="pending", index=True)
    paid_at = Column(DateTime)
    refunded_at = Column(DateTime)
    promo_code = Column(String(9))
    attribution_id = Column(String(36))
    coupon_id = Column(String(36))
    assessment_id = Column(String(36))
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    payments = relationship("Payment", back_populates="order")
    commission = relationship("Commission", back_populates="order")


class Payment(Base):
    __tablename__ = "esg_payments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("esg_orders.id"), nullable=False, index=True)
    channel = Column(String(16), nullable=False)
    channel_order_id = Column(String(128))
    amount = Column(Integer, nullable=False)
    currency = Column(String(8), default="CNY")
    status = Column(String(16), default="pending")
    webhook_raw = Column(JSON)
    webhook_received_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    order = relationship("Order", back_populates="payments")


class Promotion(Base):
    __tablename__ = "esg_promotions"

    code = Column(String(9), primary_key=True)
    promoter_id = Column(String(64), nullable=False, index=True)
    promo_type = Column(String(16), nullable=False)
    prefix = Column(String(4))
    is_special_channel = Column(Boolean, default=False)
    commission_rate = Column(Float, default=0.30)
    withdrawal_type = Column(String(8), default="cash")
    valid_from = Column(DateTime, nullable=False)
    valid_to = Column(DateTime, nullable=False)
    click_count = Column(Integer, default=0)
    register_count = Column(Integer, default=0)
    pay_count = Column(Integer, default=0)
    total_commission = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class Attribution(Base):
    __tablename__ = "esg_attributions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    promoter_id = Column(String(64), nullable=False, index=True)
    customer_id = Column(String(64), nullable=False, index=True)
    promo_code = Column(String(9), nullable=False)
    source_ip = Column(String(45))
    device_fp = Column(String(128))
    bind_at = Column(DateTime, nullable=False, server_default=func.now())
    expire_at = Column(DateTime, nullable=False)
    status = Column(String(16), default="active", index=True)
    first_pay_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class Commission(Base):
    __tablename__ = "esg_commissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("esg_orders.id"), nullable=False)
    promoter_id = Column(String(64), nullable=False, index=True)
    customer_id = Column(String(64), nullable=False)
    amount = Column(Integer, nullable=False)
    rate = Column(Float, nullable=False)
    status = Column(String(16), default="pending")
    confirmed_at = Column(DateTime)
    reversed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    order = relationship("Order", back_populates="commission")


class Coupon(Base):
    __tablename__ = "esg_coupons"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(64), nullable=False, index=True)
    code = Column(String(32), nullable=False)
    amount = Column(Integer, nullable=False)
    min_order_amount = Column(Integer, default=0)
    used_at = Column(DateTime)
    order_id = Column(String(36))
    valid_from = Column(DateTime, nullable=False)
    valid_to = Column(DateTime, nullable=False)
    status = Column(String(16), default="active")
    created_at = Column(DateTime, server_default=func.now())


class Withdrawal(Base):
    __tablename__ = "esg_withdrawals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(64), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    status = Column(String(16), default="pending")
    bank_info = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    processed_at = Column(DateTime)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class OrderCreate(BaseModel):
    user_id: str
    plan_id: str
    promo_code: Optional[str] = None
    coupon_id: Optional[str] = None
    assessment_id: Optional[str] = None
    pay_method: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class OrderResponse(BaseModel):
    id: str
    user_id: str
    plan_id: str
    original_amount: int
    discount_amount: int
    coupon_amount: int
    final_amount: int
    currency: str
    pay_method: Optional[str] = None
    trade_no: Optional[str] = None
    status: str
    promo_code: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PromoCodeCreate(BaseModel):
    promoter_id: str
    prefix: str = "HY"
    promo_type: str = "channel"


class PromoCodeResponse(BaseModel):
    code: str
    promoter_id: str
    promo_type: str
    prefix: str
    valid_from: datetime
    valid_to: datetime

    class Config:
        from_attributes = True


class CommissionResponse(BaseModel):
    id: str
    order_id: str
    promoter_id: str
    customer_id: str
    amount: int
    rate: float
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WithdrawalCreate(BaseModel):
    user_id: str
    amount: int
    bank_info: dict = Field(default_factory=dict)


class WithdrawalResponse(BaseModel):
    id: str
    user_id: str
    amount: int
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CouponResponse(BaseModel):
    id: str
    user_id: str
    code: str
    amount: int
    min_order_amount: int
    status: str
    valid_from: datetime
    valid_to: datetime

    class Config:
        from_attributes = True
