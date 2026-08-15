from __future__ import annotations

from typing import Optional

"""DDW 续费与预警插件业务逻辑层。

本插件为 **跨插件聚合查询**：
- 不创建新表
- 不调用 LLM
- 直接 query ``crm_licenses``（P4-2 license_core）+ ``crm_contracts``（P2 contract_core）

设计要点：
- 金额字段全部用 ``func.coalesce(func.sum(...), 0)`` SQL 端聚合
- LEFT JOIN (``outerjoin``) crm_companies 拿企业名，企业被归档 / 删除时为 NULL
- 所有 SQL 严格走 ``tenant_id`` 隔离
- 续费报价 = 上次合同单日单价 * 续费天数；无历史 → 0 元（仅占位）
- 续费率 = renewed / (renewed + expired)（终止态已续 vs 已过期）
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_company_profile.models import Company
from plugins.ddw_contract_core.models import Contract
from plugins.ddw_license_core.models import License

from .schemas import (
    ExpiringItem,
    ExpiringResp,
    OverdueItem,
    OverdueResp,
    QuoteBreakdown,
    QuoteResp,
    RenewalStatsBucket,
    RenewalStatsResp,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部常量
# ---------------------------------------------------------------------------


ZERO = Decimal(0)
DEFAULT_RENEWAL_UNIT_DAYS = 365  # 续费默认时长（天）


# 续费率分子：已续费 = status='renewed'
# 续费率分母：终止态 = renewed + expired
# 注意：active 不算分母（在用）


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _today_utc() -> date:
    """获取 UTC 当天日期。

    与 license_core / contract_core 保持一致用 naive datetime 取 UTC。
    """
    return datetime.now(timezone.utc).date()


def _license_to_expiring(
    row: tuple,
    today: date,
) -> ExpiringItem:
    """SELECT row → ExpiringItem。

    行顺序：id, license_no, license_type, status, company_id, company_name,
            product_ids, plugin_entitlements, max_users, max_nodes,
            valid_from, valid_to, created_at, updated_at
    """
    (
        lid,
        lno,
        ltype,
        lstatus,
        company_id,
        company_name,
        product_ids,
        plugin_entitlements,
        max_users,
        max_nodes,
        valid_from,
        valid_to,
        created_at,
        updated_at,
    ) = row
    days_remaining = (valid_to - today).days
    return ExpiringItem(
        id=lid,
        license_no=lno,
        license_type=ltype,
        status=lstatus,
        company_id=company_id,
        company_name=company_name,
        product_ids=list(product_ids or []),
        plugin_entitlements=list(plugin_entitlements or []),
        max_users=max_users or 0,
        max_nodes=max_nodes or 0,
        valid_from=valid_from,
        valid_to=valid_to,
        days_remaining=days_remaining,
        created_at=created_at,
        updated_at=updated_at,
    )


def _license_to_overdue(row: tuple, today: date) -> OverdueItem:
    """SELECT row → OverdueItem。

    行顺序：id, license_no, license_type, status, company_id, company_name,
            valid_from, valid_to, parent_license_id, created_at, updated_at
    """
    (
        lid,
        lno,
        ltype,
        lstatus,
        company_id,
        company_name,
        valid_from,
        valid_to,
        parent_license_id,
        created_at,
        updated_at,
    ) = row
    days_overdue = (today - valid_to).days
    return OverdueItem(
        id=lid,
        license_no=lno,
        license_type=ltype,
        status=lstatus,
        company_id=company_id,
        company_name=company_name,
        valid_from=valid_from,
        valid_to=valid_to,
        days_overdue=days_overdue,
        parent_license_id=parent_license_id,
        created_at=created_at,
        updated_at=updated_at,
    )


# ---------------------------------------------------------------------------
# RenewalService
# ---------------------------------------------------------------------------


class RenewalService:
    """续费与预警聚合查询服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # 1. Expiring（即将到期）
    # ------------------------------------------------------------------ #

    async def expiring(
        self, tenant_id: int = 1, days: int = 30
    ) -> ExpiringResp:
        """即将到期许可证：status=active 且 ``today <= valid_to <= today + days``。

        按 valid_to 升序，LEFT JOIN crm_companies 拿企业名。
        """
        today = _today_utc()
        # SQL ``BETWEEN`` 是包含两端的；这里等价于
        #   valid_to >= today AND valid_to <= today + days
        upper = today.fromordinal(today.toordinal() + days)

        stmt = (
            select(
                License.id,
                License.license_no,
                License.license_type,
                License.status,
                License.company_id,
                Company.name.label("company_name"),
                License.product_ids,
                License.plugin_entitlements,
                License.max_users,
                License.max_nodes,
                License.valid_from,
                License.valid_to,
                License.created_at,
                License.updated_at,
            )
            .outerjoin(Company, Company.id == License.company_id)
            .where(
                License.tenant_id == tenant_id,
                License.status == "active",
                License.valid_to >= today,
                License.valid_to <= upper,
            )
            .order_by(License.valid_to.asc(), License.id.asc())
        )
        rows = (await self.db.execute(stmt)).all()
        items = [_license_to_expiring(r, today) for r in rows]

        return ExpiringResp(
            tenant_id=tenant_id,
            window_days=days,
            today=today,
            total=len(items),
            items=items,
        )

    # ------------------------------------------------------------------ #
    # 2. Overdue（已逾期）
    # ------------------------------------------------------------------ #

    async def overdue(self, tenant_id: int = 1) -> OverdueResp:
        """已逾期许可证：status IN ('active', 'expired') 且 valid_to < today。

        - active 状态但已逾期的（业务上「该过期但还没被自动标记」）
        - expired 状态（已被 license_core 的 _auto_mark_expired 标记）

        按 valid_to 升序（最早逾期的在最前），LEFT JOIN crm_companies 拿企业名。
        """
        today = _today_utc()
        stmt = (
            select(
                License.id,
                License.license_no,
                License.license_type,
                License.status,
                License.company_id,
                Company.name.label("company_name"),
                License.valid_from,
                License.valid_to,
                License.parent_license_id,
                License.created_at,
                License.updated_at,
            )
            .outerjoin(Company, Company.id == License.company_id)
            .where(
                License.tenant_id == tenant_id,
                License.status.in_(["active", "expired"]),
                License.valid_to < today,
            )
            .order_by(License.valid_to.asc(), License.id.asc())
        )
        rows = (await self.db.execute(stmt)).all()
        items = [_license_to_overdue(r, today) for r in rows]

        return OverdueResp(
            tenant_id=tenant_id,
            today=today,
            total=len(items),
            items=items,
        )

    # ------------------------------------------------------------------ #
    # 3. Quote（续费报价估算）
    # ------------------------------------------------------------------ #

    async def quote(
        self,
        tenant_id: int = 1,
        license_id: int = 0,
        renewal_unit_days: Optional[int] = None,
    ) -> QuoteResp:
        """续费报价估算。

        步骤：
        1. 查询 license（valid_to / valid_from / license_type / company_id）
        2. 算续费时长：
           - 入参 renewal_unit_days 优先
           - 否则取上次 license 时长 = valid_to - valid_from
           - 兜底 default_renewal_unit_days
        3. 查 ``crm_contracts`` 找历史合同价：
           - 同 company_id 的「生效中」合同（status IN ('active', 'completed')）
           - 按 effective_to DESC 拿最近一张
           - 单价 = total_amount / (effective_to - effective_from) （单位 CNY/天）
        4. 估算金额 = 单价 * 续费天数；无历史 → 0（fallback）

        抛 ValueError：
        - license 不存在
        - license 已 revoked（终态不允许续费）
        - license 已 renewed（已被续费过）
        """
        if license_id <= 0:
            raise ValueError("license_id 必须为正整数")

        # 1) 查 license
        license_row = (
            await self.db.execute(
                select(License).where(
                    License.id == license_id,
                    License.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if license_row is None:
            raise ValueError(f"license {license_id} 不存在")

        if license_row.status == "revoked":
            raise ValueError(f"license {license_id} 已吊销（revoked），不可续费")
        if license_row.status == "renewed":
            raise ValueError(
                f"license {license_id} 已被续费（renewed），请用新许可证的 ID"
            )

        valid_from = license_row.valid_from
        valid_to = license_row.valid_to

        # 2) 算续费时长
        last_days = (valid_to - valid_from).days
        if last_days <= 0:
            last_days = DEFAULT_RENEWAL_UNIT_DAYS
        if renewal_unit_days is None:
            renewal_unit_days = last_days
        renewal_unit_days = int(renewal_unit_days)

        # 3) 查历史合同
        historical_unit_price: Optional[Decimal] = None
        historical_contract_id: Optional[int] = None
        historical_contract_no: Optional[str] = None
        historical_contract_total: Optional[Decimal] = None
        historical_contract_days: Optional[int] = None
        fallback_used = False

        if license_row.company_id is not None:
            # 拿同 company 最近一张已生效的合同（active / completed）
            hist_stmt = (
                select(Contract)
                .where(
                    Contract.tenant_id == tenant_id,
                    Contract.company_id == license_row.company_id,
                    Contract.status.in_(["active", "completed"]),
                    Contract.effective_from.isnot(None),
                    Contract.effective_to.isnot(None),
                    Contract.total_amount.isnot(None),
                )
                .order_by(Contract.effective_to.desc(), Contract.id.desc())
                .limit(1)
            )
            hist = (await self.db.execute(hist_stmt)).scalar_one_or_none()
            if hist is not None:
                hist_total = Decimal(hist.total_amount or 0)
                hist_days = (hist.effective_to - hist.effective_from).days
                if hist_days > 0 and hist_total > 0:
                    historical_unit_price = (hist_total / Decimal(hist_days)).quantize(
                        Decimal("0.0001")
                    )
                    historical_contract_id = hist.id
                    historical_contract_no = hist.contract_no
                    historical_contract_total = hist_total
                    historical_contract_days = hist_days

        if historical_unit_price is None:
            # 无历史 → 兜底 0
            historical_unit_price = ZERO
            fallback_used = True

        # 4) 估算金额
        estimated_amount = (historical_unit_price * Decimal(renewal_unit_days)).quantize(
            Decimal("0.01")
        )

        # 企业名（LEFT JOIN，单条）
        company_name: Optional[str] = None
        if license_row.company_id is not None:
            cn_row = (
                await self.db.execute(
                    select(Company.name).where(Company.id == license_row.company_id)
                )
            ).scalar_one_or_none()
            company_name = cn_row

        breakdown = QuoteBreakdown(
            historical_unit_price=historical_unit_price,
            historical_contract_id=historical_contract_id,
            historical_contract_no=historical_contract_no,
            historical_contract_total=historical_contract_total,
            historical_contract_days=historical_contract_days,
            renewal_unit_days=renewal_unit_days,
            estimated_unit_price=historical_unit_price,
            fallback_used=fallback_used,
        )

        return QuoteResp(
            tenant_id=tenant_id,
            license_id=license_row.id,
            license_no=license_row.license_no,
            license_type=license_row.license_type,
            company_id=license_row.company_id,
            company_name=company_name,
            valid_from=valid_from,
            valid_to=valid_to,
            estimated_amount=estimated_amount,
            currency="CNY",
            breakdown=breakdown,
        )

    # ------------------------------------------------------------------ #
    # 4. Stats（续费统计概览）
    # ------------------------------------------------------------------ #

    async def stats(self, tenant_id: int = 1) -> RenewalStatsResp:
        """续费统计概览：

        - active / overdue / renewed_total
        - 30/60/90 天窗口内到期数 + 用户/节点容量合计
        - 续费率 = renewed / (renewed + expired)
        """
        today = _today_utc()

        # 1) active 总数
        active_total = (
            await self.db.execute(
                select(func.count(License.id)).where(
                    License.tenant_id == tenant_id,
                    License.status == "active",
                )
            )
        ).scalar_one()

        # 2) 已续费（status=renewed）总数
        renewed_total = (
            await self.db.execute(
                select(func.count(License.id)).where(
                    License.tenant_id == tenant_id,
                    License.status == "renewed",
                )
            )
        ).scalar_one()

        # 3) 已过期（status=expired）总数
        expired_total = (
            await self.db.execute(
                select(func.count(License.id)).where(
                    License.tenant_id == tenant_id,
                    License.status == "expired",
                )
            )
        ).scalar_one()

        # 4) 已逾期（status IN active/expired 且 valid_to < today）总数
        overdue_total = (
            await self.db.execute(
                select(func.count(License.id)).where(
                    License.tenant_id == tenant_id,
                    License.status.in_(["active", "expired"]),
                    License.valid_to < today,
                )
            )
        ).scalar_one()

        # 5) 续费率
        denom = renewed_total + expired_total
        renewal_rate = (
            round(renewed_total / denom, 4) if denom > 0 else 0.0
        )

        # 6) 30/60/90 天窗口到期数 + 用户 / 节点容量
        windows: list[RenewalStatsBucket] = []
        expiring_30 = expiring_60 = expiring_90 = 0
        total_users_90 = 0
        total_nodes_90 = 0
        for window in (30, 60, 90):
            upper = today.fromordinal(today.toordinal() + window)
            row = (
                await self.db.execute(
                    select(
                        func.count(License.id).label("cnt"),
                        func.coalesce(func.sum(License.max_users), 0).label("users"),
                        func.coalesce(func.sum(License.max_nodes), 0).label("nodes"),
                    ).where(
                        License.tenant_id == tenant_id,
                        License.status == "active",
                        License.valid_to >= today,
                        License.valid_to <= upper,
                    )
                )
            ).one()
            cnt, users, nodes = int(row.cnt or 0), int(row.users or 0), int(row.nodes or 0)
            if window == 30:
                expiring_30 = cnt
            elif window == 60:
                expiring_60 = cnt
            elif window == 90:
                expiring_90 = cnt
                total_users_90 = users
                total_nodes_90 = nodes
            windows.append(
                RenewalStatsBucket(
                    window_days=window,
                    expiring=cnt,
                    total_users=users,
                    total_nodes=nodes,
                )
            )

        return RenewalStatsResp(
            tenant_id=tenant_id,
            today=today,
            active=active_total,
            overdue=overdue_total,
            renewed_total=renewed_total,
            renewal_rate=renewal_rate,
            windows=windows,
            expiring_30=expiring_30,
            expiring_60=expiring_60,
            expiring_90=expiring_90,
            total_users_at_risk=total_users_90,
            total_nodes_at_risk=total_nodes_90,
        )


__all__ = ["RenewalService"]
