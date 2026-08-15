from __future__ import annotations

from typing import Optional

"""DDW 电子签章适配器插件 ORM 模型。

继承 DDW 平台核心：
- core.database.models.Base: DeclarativeBase 根
- core.database.models.TenantMixin: 自动注入 tenant_id + 标记租户感知
- core.database.models.TimestampMixin: 自动注入 created_at / updated_at

外键策略：
- contract_id -> crm_contracts.id (use_alter=True, ON DELETE SET NULL)
  合同删除不级联删签署请求（保留审计痕迹）
"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class SignatureRequest(Base, TenantMixin, TimestampMixin):
    """电子签章请求主表。

    业务含义：
    - 销售端为某份合同发起电子签章流程
    - provider 字段标识使用哪个第三方签章服务（tencent / dianxiaoyu / esign / manual）
    - external_request_id 是第三方系统返回的请求 ID（用于异步回调关联）
    - signers 是签署方列表（JSON 数组，每个元素为 {name, phone, role, status}）
    - status 状态机：
        * pending   待发起（已落库未调用第三方）
        * signing   签署中（已调用第三方，等待签署方完成）
        * signed    已签署
        * rejected  拒绝签署
        * expired   超时过期
    - document_url 是待签文件的 URL，signed_document_url 是签后文件 URL
    """

    __tablename__ = "crm_signature_requests"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ---- 业务关联 ----
    contract_id: Mapped[Optional[int]] = mapped_column(        BigInt,
        ForeignKey("crm_contracts.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
        index=True,
    )

    # ---- 服务商 ----
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # tencent / dianxiaoyu / esign / manual
    external_request_id: Mapped[Optional[str]] = mapped_column(        String(100), index=True, nullable=True
    )

    # ---- 签署方 ----
    signers: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # 元素形如 {"name": "张三", "phone": "138...", "role": "buyer", "status": "pending"}

    # ---- 文件 ----
    document_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    signed_document_url: Mapped[Optional[str]] = mapped_column(        String(500), nullable=True
    )

    # ---- 状态 ----
    status: Mapped[Optional[str]] = mapped_column(        String(20), default="pending", nullable=False, index=True
    )
    # pending / signing / signed / rejected / expired
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ---- 备注 / 审计 ----
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SignatureRequest id={self.id} provider={self.provider!r} "
            f"status={self.status!r}>"
        )


__all__ = ["SignatureRequest"]
