from __future__ import annotations

"""DDW 实例绑定插件业务逻辑层。

关键设计：
- :class:`InstanceService` —— 实例绑定 CRUD + 心跳 + 统计
- :func:`_instance_to_dict` —— ORM -> dict 序列化
- :data:`ALLOWED_INSTANCE_TYPES` —— 类型白名单（saas / on-premise）
- :data:`ALLOWED_ENVIRONMENTS` —— 环境白名单（production / staging / test）
- :data:`ALLOWED_STATUSES` —— 状态白名单（active / inactive / suspended）

软删除：DELETE 走 ``status=suspended``（不真删，保留审计链）。
心跳：POST /instances/{id}/heartbeat 更新 last_heartbeat = now()。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Instance
from .schemas import (
    InstanceCreateReq,
    InstanceHeartbeatReq,
    InstanceListResp,
    InstanceResp,
    InstanceStatsResp,
    InstanceUpdateReq,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 枚举白名单
# ---------------------------------------------------------------------------

ALLOWED_INSTANCE_TYPES: frozenset[str] = frozenset({"saas", "on-premise"})
ALLOWED_ENVIRONMENTS: frozenset[str] = frozenset({"production", "staging", "test"})
ALLOWED_STATUSES: frozenset[str] = frozenset({"active", "inactive", "suspended"})

# 心跳存活窗口：默认 24h
HEARTBEAT_ALIVE_WINDOW = timedelta(hours=24)


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _instance_to_dict(inst: Instance) -> dict[str, Any]:
    """ORM -> dict（用于响应）。"""
    return {
        "id": inst.id,
        "tenant_id": inst.tenant_id,
        "company_id": inst.company_id,
        "license_id": inst.license_id,
        "instance_type": inst.instance_type,
        "instance_id": inst.instance_id,
        "instance_name": inst.instance_name,
        "fingerprint": inst.fingerprint,
        "environment": inst.environment,
        "endpoint": inst.endpoint,
        "status": inst.status,
        "last_heartbeat": inst.last_heartbeat,
        "created_at": inst.created_at,
        "updated_at": inst.updated_at,
        "created_by": inst.created_by,
        "updated_by": inst.updated_by,
    }


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class InstanceService:
    """实例绑定业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- CRUD -----

    async def create(self, data: InstanceCreateReq) -> dict[str, Any]:
        """绑定实例。

        业务规则：
        - 同一 (tenant_id, instance_id, environment) 唯一：
          防止重复绑定同一实例。命中则抛 ValueError。
        - instance_type 必须属于白名单
        - environment 必须属于白名单
        - 至少 company_id / license_id 传一个（实例必须挂到主体下）
        """
        # 枚举校验
        if data.instance_type not in ALLOWED_INSTANCE_TYPES:
            raise ValueError(
                f"instance_type '{data.instance_type}' 不合法，"
                f"合法值: {sorted(ALLOWED_INSTANCE_TYPES)}"
            )
        if data.environment not in ALLOWED_ENVIRONMENTS:
            raise ValueError(
                f"environment '{data.environment}' 不合法，"
                f"合法值: {sorted(ALLOWED_ENVIRONMENTS)}"
            )
        if data.company_id is None and data.license_id is None:
            raise ValueError("company_id 和 license_id 至少传一个")

        # 唯一性校验：同 (tenant, instance_id, environment) 不能重复
        existing = await self._get_by_triple(
            data.instance_id, data.environment, data.tenant_id
        )
        if existing:
            raise ValueError(
                f"实例 '{data.instance_id}' (env={data.environment}) 已存在 "
                f"(id={existing.id})"
            )

        inst = Instance(
            tenant_id=data.tenant_id,
            company_id=data.company_id,
            license_id=data.license_id,
            instance_type=data.instance_type,
            instance_id=data.instance_id,
            instance_name=data.instance_name,
            fingerprint=data.fingerprint,
            environment=data.environment,
            endpoint=data.endpoint,
            status="active",
            created_by=data.created_by,
        )
        self.db.add(inst)
        await self.db.commit()
        await self.db.refresh(inst)
        logger.info(
            "instance created: id=%s type=%s instance_id=%s env=%s",
            inst.id, inst.instance_type, inst.instance_id, inst.environment,
        )
        return _instance_to_dict(inst)

    async def get(self, instance_id: int) -> dict[str, Any] | None:
        """获取实例详情。"""
        inst = await self.db.get(Instance, instance_id)
        if not inst:
            return None
        return _instance_to_dict(inst)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        company_id: Optional[int] = None,
        license_id: Optional[int] = None,
        instance_type: Optional[str] = None,
        environment: Optional[str] = None,
        status: Optional[str] = None,
    ) -> InstanceListResp:
        """实例列表（分页 + 多维筛选）。

        筛选：
        - company_id：按关联企业
        - license_id：按关联许可证
        - instance_type：按类型（saas / on-premise）
        - environment：按环境（production / staging / test）
        - status：按状态（active / inactive / suspended）
        """
        conditions = []
        if company_id is not None:
            conditions.append(Instance.company_id == company_id)
        if license_id is not None:
            conditions.append(Instance.license_id == license_id)
        if instance_type:
            conditions.append(Instance.instance_type == instance_type)
        if environment:
            conditions.append(Instance.environment == environment)
        if status:
            conditions.append(Instance.status == status)

        # total
        count_stmt = select(func.count(Instance.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(Instance)
            .order_by(Instance.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return InstanceListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[InstanceResp(**_instance_to_dict(inst)) for inst in rows],
        )

    async def update(
        self, instance_id: int, data: InstanceUpdateReq
    ) -> dict[str, Any] | None:
        """更新实例。

        业务规则：
        - 状态变更：必须是 ALLOWED_STATUSES 之一
        - 环境变更：必须是 ALLOWED_ENVIRONMENTS 之一
        - instance_id / instance_type / company_id / license_id 不可通过本端点修改
          （防破坏唯一性 + 主体关系）
        """
        inst = await self.db.get(Instance, instance_id)
        if not inst:
            return None
        updates = data.model_dump(exclude_unset=True)

        # 保护字段：唯一标识 + 主体关系不能改
        for protected in ("instance_id", "instance_type", "company_id", "license_id", "tenant_id"):
            updates.pop(protected, None)

        # 枚举校验
        if "environment" in updates and updates["environment"] not in ALLOWED_ENVIRONMENTS:
            raise ValueError(
                f"environment '{updates['environment']}' 不合法，"
                f"合法值: {sorted(ALLOWED_ENVIRONMENTS)}"
            )
        if "status" in updates and updates["status"] not in ALLOWED_STATUSES:
            raise ValueError(
                f"status '{updates['status']}' 不合法，"
                f"合法值: {sorted(ALLOWED_STATUSES)}"
            )

        for k, v in updates.items():
            setattr(inst, k, v)

        await self.db.commit()
        await self.db.refresh(inst)
        logger.info("instance updated: id=%s fields=%s", inst.id, list(updates.keys()))
        return _instance_to_dict(inst)

    async def suspend(self, instance_id: int) -> dict[str, Any] | None:
        """软删除：status -> suspended（保留审计链，不真删）。

        与 update(status="suspended") 等价；单独提出来语义更清晰。
        """
        inst = await self.db.get(Instance, instance_id)
        if not inst:
            return None
        previous = inst.status
        inst.status = "suspended"
        await self.db.commit()
        await self.db.refresh(inst)
        logger.info(
            "instance suspended: id=%s %s -> suspended", inst.id, previous
        )
        return _instance_to_dict(inst)

    # ----- 心跳 -----

    async def heartbeat(
        self, instance_id: int, data: InstanceHeartbeatReq | None = None
    ) -> dict[str, Any] | None:
        """心跳上报：更新 last_heartbeat = now()。

        可选同时更新 status（用于 active <-> inactive 切换）。
        不允许通过心跳变成 suspended（suspended 走专门端点）。
        """
        inst = await self.db.get(Instance, instance_id)
        if not inst:
            return None
        now = datetime.now(timezone.utc)
        # 去掉时区信息以匹配 DateTime 列的 naive 行为
        inst.last_heartbeat = now.replace(tzinfo=None)
        if data and data.status:
            if data.status not in ALLOWED_STATUSES:
                raise ValueError(
                    f"status '{data.status}' 不合法，"
                    f"合法值: {sorted(ALLOWED_STATUSES)}"
                )
            if data.status == "suspended":
                raise ValueError("心跳端点不允许改为 suspended，请走 /instances/{id} DELETE")
            inst.status = data.status
        await self.db.commit()
        await self.db.refresh(inst)
        logger.info(
            "instance heartbeat: id=%s last_heartbeat=%s status=%s",
            inst.id, inst.last_heartbeat, inst.status,
        )
        return _instance_to_dict(inst)

    # ----- 统计 -----

    async def stats(self) -> InstanceStatsResp:
        """统计概览。

        - total / 各状态计数
        - by_instance_type：按类型分组
        - by_environment：按环境分组
        - heartbeat_alive：最近 24h 内有心跳的实例数
        """
        # 按 status
        by_status_rows = (
            await self.db.execute(
                select(Instance.status, func.count(Instance.id)).group_by(
                    Instance.status
                )
            )
        ).all()
        by_status: dict[str, int] = {s: c for s, c in by_status_rows}

        # 按 instance_type
        by_type_rows = (
            await self.db.execute(
                select(Instance.instance_type, func.count(Instance.id)).group_by(
                    Instance.instance_type
                )
            )
        ).all()
        by_type: dict[str, int] = {t: c for t, c in by_type_rows}

        # 按 environment
        by_env_rows = (
            await self.db.execute(
                select(Instance.environment, func.count(Instance.id)).group_by(
                    Instance.environment
                )
            )
        ).all()
        by_env: dict[str, int] = {e: c for e, c in by_env_rows}

        # heartbeat_alive：last_heartbeat >= now - 24h
        alive_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - HEARTBEAT_ALIVE_WINDOW
        alive = (
            await self.db.execute(
                select(func.count(Instance.id)).where(
                    Instance.last_heartbeat.isnot(None),
                    Instance.last_heartbeat >= alive_cutoff,
                )
            )
        ).scalar_one()

        return InstanceStatsResp(
            total=sum(by_status.values()),
            active=by_status.get("active", 0),
            inactive=by_status.get("inactive", 0),
            suspended=by_status.get("suspended", 0),
            by_instance_type=by_type,
            by_environment=by_env,
            heartbeat_alive=int(alive or 0),
        )

    # ----- 内部辅助 -----

    async def _get_by_triple(
        self,
        instance_id: str,
        environment: str,
        tenant_id: int,
    ) -> Instance | None:
        """按 (instance_id, environment, tenant_id) 查重。"""
        stmt = select(Instance).where(
            Instance.instance_id == instance_id,
            Instance.environment == environment,
            Instance.tenant_id == tenant_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()


__all__ = [
    "ALLOWED_ENVIRONMENTS",
    "ALLOWED_INSTANCE_TYPES",
    "ALLOWED_STATUSES",
    "HEARTBEAT_ALIVE_WINDOW",
    "InstanceService",
]
