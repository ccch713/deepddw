from __future__ import annotations

"""DDW 许可证管理插件业务逻辑层。

关键设计：
- :func:`generate_license_no` —— 按 LIC-YYYYMMDD-NNN 规则生成单号
- :func:`_auto_mark_expired` —— read 类操作前批量把 active 且
  valid_to<today 的标记为 expired，避免查询时再过滤
- :data:`ALLOWED_TRANSITIONS` —— 状态机迁移白名单
- :data:`_EDITABLE_STATUSES` —— 允许 update 的状态（active / suspended）
- :class:`LicenseService` —— 许可证 CRUD + 状态机 + 续费 + 统计

状态机：
    active     → expired (auto) | suspended | revoked | renewed
    suspended  → active         | revoked
    expired    → renewed
    revoked    → (终态)
    renewed    → (终态)
"""

import logging
from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc
from typing import Any, Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import License
from .schemas import (
    LicenseCreateReq,
    LicenseListResp,
    LicenseRenewalReq,
    LicenseResp,
    LicenseStatsResp,
    LicenseUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------
#
# ALLOWED_TRANSITIONS: {from_status: set of allowed to_status}
# 设计要点：
# - active  -> expired（自动）/ suspended / revoked / renewed
# - suspended -> active / revoked（可恢复）
# - expired -> renewed（已过期的也可以续费）
# - revoked / renewed 是终态，不在任何 from 集合中
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "active": {"expired", "suspended", "revoked", "renewed"},
    "suspended": {"active", "revoked"},
    "expired": {"renewed"},
    "revoked": set(),  # 终态
    "renewed": set(),  # 终态
}

ALL_STATUSES: list[str] = list(ALLOWED_TRANSITIONS.keys())

# 仅 active / suspended 允许修改基本信息（防止破坏已吊销/已续费的审计链）
_EDITABLE_STATUSES: frozenset[str] = frozenset({"active", "suspended"})


# ---------------------------------------------------------------------------
# 辅助函数：单号生成
# ---------------------------------------------------------------------------


async def generate_license_no(db: AsyncSession) -> str:
    """生成当日唯一单号：LIC-YYYYMMDD-NNN（NNN 从 001 开始递增）。

    通过 ``like 'LIC-YYYYMMDD-%'`` 查出当日所有单号，解析末段序号取最大值 + 1。
    极小概率碰撞：理论上同毫秒并发插入可能拿到相同序号，
    数据库 unique 约束兜底（重复时由调用方在 ``IntegrityError`` 中重试）。
    """
    today_str = datetime.now(UTC).date().strftime("%Y%m%d")
    prefix = f"LIC-{today_str}-"
    stmt = select(License.license_no).where(License.license_no.like(f"{prefix}%"))
    rows = (await db.execute(stmt)).scalars().all()
    max_seq = 0
    for no in rows:
        try:
            seq = int(no.rsplit("-", 1)[-1])
            max_seq = max(max_seq, seq)
        except (ValueError, IndexError):
            continue
    return f"{prefix}{max_seq + 1:03d}"


# ---------------------------------------------------------------------------
# 自动过期检查（核心业务规则）
# ---------------------------------------------------------------------------


async def _auto_mark_expired(db: AsyncSession) -> None:
    """批量把 active 中 valid_to<today 的标记为 expired。

    在 read 类操作（list / get / stats）前调用一次，避免业务侧在 read 时
    还要再次按 valid_to 过滤。

    注意：suspended / revoked / renewed 不动（只把真正"过期但仍在 active 状态"
    的记录标记为 expired）。已过期的 active 才会被批量转换。
    """
    today = datetime.now(UTC).date()
    stmt = (
        update(License)
        .where(
            License.status == "active",
            License.valid_to < today,
        )
        .values(status="expired")
    )
    await db.execute(stmt)
    await db.commit()


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _license_to_dict(lic: License) -> dict[str, Any]:
    """ORM -> dict（用于响应）。"""
    return {
        "id": lic.id,
        "tenant_id": lic.tenant_id,
        "company_id": lic.company_id,
        "parent_license_id": lic.parent_license_id,
        "license_no": lic.license_no,
        "license_type": lic.license_type,
        "product_ids": lic.product_ids or [],
        "plugin_entitlements": lic.plugin_entitlements or [],
        "max_users": lic.max_users,
        "max_nodes": lic.max_nodes,
        "valid_from": lic.valid_from,
        "valid_to": lic.valid_to,
        "status": lic.status,
        "notes": lic.notes,
        "created_at": lic.created_at,
        "updated_at": lic.updated_at,
        "created_by": lic.created_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class LicenseService:
    """许可证业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- CRUD -----

    async def create(self, data: LicenseCreateReq) -> dict[str, Any]:
        """新建许可证。

        - 自动生成 license_no（LIC-YYYYMMDD-NNN）
        - 默认 status=active
        - 如果 valid_to<today，list/get 时会被 _auto_mark_expired 转成 expired
          （不在 create 时直接判定，避免并发问题）
        """
        if data.valid_to < data.valid_from:
            raise ValueError(
                f"valid_to ({data.valid_to}) 早于 valid_from ({data.valid_from})"
            )

        license_no = await generate_license_no(self.db)
        lic = License(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            license_no=license_no,
            license_type=data.license_type,
            product_ids=data.product_ids or [],
            plugin_entitlements=data.plugin_entitlements or [],
            max_users=data.max_users,
            max_nodes=data.max_nodes,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            status="active",
            notes=data.notes,
            created_by=data.created_by,
        )
        self.db.add(lic)
        await self.db.commit()
        await self.db.refresh(lic)
        logger.info(
            "license created: id=%s no=%s type=%s valid_to=%s",
            lic.id, lic.license_no, lic.license_type, lic.valid_to,
        )
        return _license_to_dict(lic)

    async def get(self, license_id: int) -> dict[str, Any] | None:
        """获取许可证详情（read 前自动过期检查）。"""
        await _auto_mark_expired(self.db)
        lic = await self.db.get(License, license_id)
        if not lic:
            return None
        return _license_to_dict(lic)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        company_id: Optional[int] = None,
        license_type: Optional[str] = None,
        status: Optional[str] = None,
        valid_to_before: Optional[date] = None,
        valid_to_after: Optional[date] = None,
    ) -> LicenseListResp:
        """许可证列表（分页 + 多维筛选；查询前自动标记过期）。

        筛选：
        - company_id：按关联企业
        - license_type：按类型（trial / formal / renewal）
        - status：按状态
        - valid_to_before / valid_to_after：按有效期截止范围
        """
        await _auto_mark_expired(self.db)

        conditions = []
        if company_id is not None:
            conditions.append(License.company_id == company_id)
        if license_type:
            conditions.append(License.license_type == license_type)
        if status:
            conditions.append(License.status == status)
        if valid_to_before is not None:
            conditions.append(License.valid_to <= valid_to_before)
        if valid_to_after is not None:
            conditions.append(License.valid_to >= valid_to_after)

        # total
        count_stmt = select(func.count(License.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(License)
            .order_by(License.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return LicenseListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[LicenseResp(**_license_to_dict(lic)) for lic in rows],
        )

    async def update(
        self, license_id: int, data: LicenseUpdateReq
    ) -> dict[str, Any] | None:
        """更新许可证（仅 active / suspended 状态可改基本信息）。

        业务规则：
        - status 字段不允许通过 update 改（必须走 suspend/resume/revoke 端点）
        - 如果同时更新了 valid_from / valid_to 且 valid_to<valid_from，抛 ValueError
        - license_no 不允许通过 update 改（保持审计稳定）
        """
        lic = await self.db.get(License, license_id)
        if not lic:
            return None
        if lic.status not in _EDITABLE_STATUSES:
            raise ValueError(
                f"当前 status='{lic.status}' 不允许修改（仅允许 active/suspended）"
            )

        updates = data.model_dump(exclude_unset=True)
        # 保护字段：单号/状态不能通过 update 改
        updates.pop("license_no", None)
        updates.pop("status", None)
        updates.pop("parent_license_id", None)

        # 校验日期合法性
        new_from = updates.get("valid_from", lic.valid_from)
        new_to = updates.get("valid_to", lic.valid_to)
        if new_to < new_from:
            raise ValueError(
                f"valid_to ({new_to}) 早于 valid_from ({new_from})"
            )

        for k, v in updates.items():
            setattr(lic, k, v)

        await self.db.commit()
        await self.db.refresh(lic)
        logger.info("license updated: id=%s fields=%s", lic.id, list(updates.keys()))
        return _license_to_dict(lic)

    # ----- 状态机迁移 -----

    async def _transition(
        self, license_id: int, target: str
    ) -> dict[str, Any] | None:
        """通用状态机迁移（suspend/resume/revoke 共用）。"""
        lic = await self.db.get(License, license_id)
        if not lic:
            return None
        current = lic.status
        if target not in ALLOWED_TRANSITIONS:
            raise ValueError(
                f"invalid target status '{target}'，合法值: {ALL_STATUSES}"
            )
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ValueError(
                f"invalid transition: {current} -> {target} "
                f"（仅允许: {sorted(allowed) if allowed else '（无）'}）"
            )
        lic.status = target
        await self.db.commit()
        await self.db.refresh(lic)
        logger.info("license %s: id=%s %s -> %s", target, lic.id, current, target)
        return _license_to_dict(lic)

    async def suspend(self, license_id: int) -> dict[str, Any] | None:
        """暂停许可证（active -> suspended）。"""
        return await self._transition(license_id, "suspended")

    async def resume(self, license_id: int) -> dict[str, Any] | None:
        """恢复许可证（suspended -> active）。"""
        return await self._transition(license_id, "active")

    async def revoke(self, license_id: int) -> dict[str, Any] | None:
        """吊销许可证（active / suspended / expired -> revoked）。"""
        return await self._transition(license_id, "revoked")

    # ----- 续费 -----

    async def renewal(
        self, license_id: int, data: LicenseRenewalReq
    ) -> dict[str, Any] | None:
        """为旧许可证续费。

        业务规则：
        - 旧许可证必须存在，且 status 必须是 active / expired / suspended
          （不允许续费已被 revoked / renewed 的许可证）
        - 创建新许可证（type='renewal'，自动生成单号）
        - 新许可证继承旧许可证的：company_id / product_ids / plugin_entitlements
          （不传则继承，传则覆盖）
        - 新许可证的 parent_license_id 指向旧许可证
        - 旧许可证状态变更为 renewed（终态）
        - 校验：valid_to 必须在 valid_from 之后
        """
        old = await self.db.get(License, license_id)
        if not old:
            return None
        if old.status not in {"active", "expired", "suspended"}:
            raise ValueError(
                f"当前 status='{old.status}' 不允许续费（仅允许 active/expired/suspended）"
            )

        # 默认日期：valid_from=today, valid_to=today+1y
        today = datetime.now(UTC).date()
        new_from = data.valid_from or today
        new_to = data.valid_to or (new_from + timedelta(days=365))
        if new_to < new_from:
            raise ValueError(
                f"valid_to ({new_to}) 早于 valid_from ({new_from})"
            )

        # 继承旧许可证的字段（未传则继承）
        new_license_no = await generate_license_no(self.db)
        new_lic = License(
            tenant_id=data.tenant_id,
            company_id=old.company_id,
            parent_license_id=old.id,
            license_no=new_license_no,
            license_type="renewal",
            product_ids=data.product_ids if data.product_ids is not None else (old.product_ids or []),
            plugin_entitlements=(
                data.plugin_entitlements
                if data.plugin_entitlements is not None
                else (old.plugin_entitlements or [])
            ),
            max_users=data.max_users or old.max_users,
            max_nodes=data.max_nodes or old.max_nodes,
            valid_from=new_from,
            valid_to=new_to,
            status="active",
            notes=data.notes,
            created_by=data.created_by,
        )
        self.db.add(new_lic)
        # 旧许可证：status -> renewed（终态）
        old.status = "renewed"
        await self.db.commit()
        await self.db.refresh(new_lic)
        await self.db.refresh(old)
        logger.info(
            "license renewed: old_id=%s old_no=%s new_id=%s new_no=%s",
            old.id, old.license_no, new_lic.id, new_lic.license_no,
        )
        return _license_to_dict(new_lic)

    # ----- 统计 -----

    async def stats(self) -> LicenseStatsResp:
        """许可证统计概览（read 前自动过期检查）。

        - total / 各状态计数
        - by_license_type：按类型分组
        - active_total_users / active_total_nodes：当前 active 容量合计
        """
        await _auto_mark_expired(self.db)

        # 按 status
        by_status_rows = (
            await self.db.execute(
                select(License.status, func.count(License.id)).group_by(
                    License.status
                )
            )
        ).all()
        by_status: dict[str, int] = {s: c for s, c in by_status_rows}

        # 按 license_type
        by_type_rows = (
            await self.db.execute(
                select(License.license_type, func.count(License.id)).group_by(
                    License.license_type
                )
            )
        ).all()
        by_type: dict[str, int] = {t: c for t, c in by_type_rows}

        # active 容量合计
        active_capacity = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(License.max_users), 0).label("users"),
                    func.coalesce(func.sum(License.max_nodes), 0).label("nodes"),
                ).where(License.status == "active")
            )
        ).one()
        total_users = int(active_capacity.users or 0)
        total_nodes = int(active_capacity.nodes or 0)

        return LicenseStatsResp(
            total=sum(by_status.values()),
            active=by_status.get("active", 0),
            expired=by_status.get("expired", 0),
            suspended=by_status.get("suspended", 0),
            revoked=by_status.get("revoked", 0),
            renewed=by_status.get("renewed", 0),
            by_license_type=by_type,
            active_total_users=total_users,
            active_total_nodes=total_nodes,
        )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "LicenseService",
    "_auto_mark_expired",
    "generate_license_no",
]
