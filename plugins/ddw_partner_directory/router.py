from __future__ import annotations

from typing import Optional

"""DDW 经销商开户插件 API 路由。

API 端点（7 个）：
  健康：GET /health
  开户：POST /partners
  列表：GET /partners
  统计：GET /partners/stats          （必须在 /partners/{id} 之前注册，避免被路径参数吞掉）
  详情：GET /partners/{id}
  更新：PUT /partners/{id}
  软删：DELETE /partners/{id}        （status=suspended）
"""

import logging

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pathlib import Path
from sqlalchemy import select

from core.auth.jwt import create_access_token, current_user
from core.database.models import Tenant, User
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .schemas import (
    DemoAccountCreateReq,
    DemoAccountListResp,
    DemoAccountResp,
    DemoAccountUpdateReq,
    EnterDemoReq,
    EnterDemoResp,
    PaidCustomer,
    PartnerCreateReq,
    PartnerListResp,
    PartnerStatsResp,
    PartnerUpdateReq,
)
from .services import PartnerService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造经销商开户路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-partner-directory",
        tags=["ddw-partner-directory"],
    )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------
    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-partner-directory", "version": "1.0.0", "status": "ok"}

    # -----------------------------------------------------------------------
    # 开户
    # -----------------------------------------------------------------------
    @router.post("/partners", response_model=dict, status_code=201)
    async def create_partner(data: PartnerCreateReq) -> dict:
        """新建经销商开户。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = PartnerService(db)
            return await svc.create(data)

    # -----------------------------------------------------------------------
    # 列表（分页 + 多维筛选）
    # -----------------------------------------------------------------------
    @router.get("/partners", response_model=PartnerListResp)
    async def list_partners(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
        search: Optional[str] = Query(
            None, description="模糊搜索（联系人/区域/行业/备注）"
        ),
        partner_type: Optional[str] = Query(
            None, description="类型筛选：reseller/agent/distributor"
        ),
        level: Optional[str] = Query(
            None, description="等级筛选：normal/silver/gold/strategic"
        ),
        region: Optional[str] = Query(None, description="区域筛选"),
        industry: Optional[str] = Query(None, description="行业筛选"),
        status: Optional[str] = Query(
            None, description="状态筛选：active/inactive/suspended"
        ),
    ) -> PartnerListResp:
        """经销商列表（分页 + 多维筛选 + 模糊搜索）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = PartnerService(db)
            return await svc.list(
                page=page,
                page_size=page_size,
                search=search,
                partner_type=partner_type,
                level=level,
                region=region,
                industry=industry,
                status=status,
            )

    # -----------------------------------------------------------------------
    # 统计概览（必须在 /partners/{id} 之前定义，否则 "stats" 会被解析为 {id}）
    # -----------------------------------------------------------------------
    @router.get("/partners/stats", response_model=PartnerStatsResp)
    async def partner_stats() -> PartnerStatsResp:
        """经销商统计概览（total/active/inactive/suspended + by_type/level/region）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = PartnerService(db)
            return await svc.stats()

    # -----------------------------------------------------------------------
    # 详情
    # -----------------------------------------------------------------------
    @router.get("/partners/{partner_id}", response_model=dict)
    async def get_partner(partner_id: int) -> dict:
        """经销商详情。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = PartnerService(db)
            result = await svc.get(partner_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"partner {partner_id} not found",
                )
            return result

    # -----------------------------------------------------------------------
    # 更新
    # -----------------------------------------------------------------------
    @router.put("/partners/{partner_id}", response_model=dict)
    async def update_partner(partner_id: int, data: PartnerUpdateReq) -> dict:
        """更新经销商。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = PartnerService(db)
            result = await svc.update(partner_id, data)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"partner {partner_id} not found",
                )
            return result

    # -----------------------------------------------------------------------
    # 软删除（暂停）
    # -----------------------------------------------------------------------
    @router.delete("/partners/{partner_id}", response_model=dict)
    async def suspend_partner(partner_id: int) -> dict:
        """暂停经销商（软删除：status=suspended）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = PartnerService(db)
            result = await svc.suspend(partner_id)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"partner {partner_id} not found",
                )
            return result

    # -----------------------------------------------------------------------
    # 经销商 demo 账号清单（名下客户演示账号）
    # -----------------------------------------------------------------------
    @router.get("/demo-accounts", response_model=DemoAccountListResp)
    async def list_demo_accounts(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        status: Optional[str] = Query(None, description="active/expired/disabled"),
    ) -> DemoAccountListResp:
        """当前租户（经销商）名下客户 demo 账号清单。"""
        from sqlalchemy import select as sa_select

        async with session_scope() as db:
            from .models import PartnerDemoAccount

            q = sa_select(PartnerDemoAccount)
            if status:
                q = q.where(PartnerDemoAccount.status == status)
            q = q.order_by(PartnerDemoAccount.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            items = (await db.execute(q)).scalars().all()
            total = len(items)
            return DemoAccountListResp(
                total=total,
                items=[DemoAccountResp.model_validate(i) for i in items],
            )

    @router.post("/demo-accounts", response_model=DemoAccountResp, status_code=201)
    async def create_demo_account(data: DemoAccountCreateReq) -> DemoAccountResp:
        """新增客户 demo 账号（经销商名下）。"""
        from .models import PartnerDemoAccount

        async with session_scope() as db:
            acc = PartnerDemoAccount(**data.model_dump())
            db.add(acc)
            await db.commit()
            await db.refresh(acc)
            return DemoAccountResp.model_validate(acc)

    @router.put("/demo-accounts/{account_id}", response_model=DemoAccountResp)
    async def update_demo_account(account_id: int, data: DemoAccountUpdateReq) -> DemoAccountResp:
        """更新客户 demo 账号。"""
        from .models import PartnerDemoAccount

        async with session_scope() as db:
            acc = (
                await db.execute(
                    select(PartnerDemoAccount).where(PartnerDemoAccount.id == account_id)
                )
            ).scalar_one_or_none()
            if acc is None:
                raise HTTPException(status_code=404, detail="demo account not found")
            for k, v in data.model_dump(exclude_unset=True).items():
                setattr(acc, k, v)
            await db.commit()
            await db.refresh(acc)
            return DemoAccountResp.model_validate(acc)

    @router.delete("/demo-accounts/{account_id}", response_model=dict)
    async def delete_demo_account(account_id: int) -> dict:
        """删除客户 demo 账号。"""
        from .models import PartnerDemoAccount

        async with session_scope() as db:
            acc = (
                await db.execute(
                    select(PartnerDemoAccount).where(PartnerDemoAccount.id == account_id)
                )
            ).scalar_one_or_none()
            if acc is None:
                raise HTTPException(status_code=404, detail="demo account not found")
            await db.delete(acc)
            await db.commit()
            return {"ok": True, "deleted": account_id}

    # -----------------------------------------------------------------------
    # 一键进入 Demo（免密登录）
    # -----------------------------------------------------------------------
    @router.post("/enter-demo", response_model=EnterDemoResp)
    async def enter_demo(
        data: EnterDemoReq,
        user: dict = Depends(current_user),
    ) -> EnterDemoResp:
        """经销商一键进入客户 demo：签发短时 demo token。"""
        from .models import PartnerDemoAccount

        async with session_scope() as db, bypass_tenant_filter():
            acc = (
                await db.execute(
                    select(PartnerDemoAccount).where(PartnerDemoAccount.id == data.account_id)
                )
            ).scalar_one_or_none()
            if acc is None:
                raise HTTPException(status_code=404, detail="demo account not found")

            # 归属校验：account.tenant_id 必须等于当前经销商 tenant_id
            if acc.tenant_id != user["tenant_id"]:
                raise HTTPException(status_code=403, detail="无权访问该 demo 账号")

            if acc.status != "active":
                raise HTTPException(status_code=403, detail="该 demo 账号已停用或过期")

            # 按 demo_phone + 客户租户查 users 表找 demo 用户（同手机号多租户时精确匹配）
            demo_user = (
                await db.execute(
                    select(User).where(
                        User.phone == acc.demo_phone,
                        User.tenant_id == (acc.client_tenant_id or acc.tenant_id),
                    )
                )
            ).scalars().first()
            if demo_user is None:
                raise HTTPException(status_code=404, detail="demo 账号对应的用户不存在")

            # 签发短时 demo token（15 分钟，scope=demo_enter）
            demo_token = create_access_token(
                user_id=demo_user.id,
                tenant_id=acc.client_tenant_id or demo_user.tenant_id,
                role=demo_user.role,
                extra={"scope": "demo_enter", "jti": uuid.uuid4().hex},
                expires_minutes=15,
            )

            return EnterDemoResp(
                demo_token=demo_token,
                demo_url=acc.demo_url,
                expires_in=900,
            )

    # -----------------------------------------------------------------------
    # 付费客户列表（聚合派生，零新表）
    # -----------------------------------------------------------------------
    @router.get("/paid-customers", response_model=list[PaidCustomer])
    async def list_paid_customers(
        user: dict = Depends(current_user),
    ) -> list[PaidCustomer]:
        """当前经销商名下付费客户列表（裸数组）。"""
        from .models import PartnerDemoAccount

        async with session_scope() as db, bypass_tenant_filter():
            # 查当前经销商 tenant_id 名下所有 demo 账号
            rows = (
                await db.execute(
                    select(PartnerDemoAccount).where(
                        PartnerDemoAccount.tenant_id == user["tenant_id"]
                    )
                )
            ).scalars().all()

            if not rows:
                return []

            # 按 client_tenant_id 去重
            seen: dict[int, PartnerDemoAccount] = {}
            for r in rows:
                cid = r.client_tenant_id
                if cid is not None and cid not in seen:
                    seen[cid] = r

            if not seen:
                return []

            # join tenants 取 plan/status/contact_phone
            result: list[PaidCustomer] = []
            for cid, acc in seen.items():
                tenant = (
                    await db.execute(select(Tenant).where(Tenant.id == cid))
                ).scalar_one_or_none()
                if tenant is None:
                    continue
                result.append(
                    PaidCustomer(
                        client_tenant_id=cid,
                        client_name=acc.client_name,
                        plan=tenant.plan or "free",
                        status=tenant.status or "active",
                        contact_phone=tenant.contact_phone,
                        expires_at=acc.expires_at,
                    )
                )

            return result

    # -----------------------------------------------------------------------
    # 客户物料（登录鉴权后返回：演示 PPT / 话术 / 其他物料）
    # 文件存放：plugins/ddw_partner_directory/materials/{account_id}/
    # 安全：未登录 401；非本经销商名下客户 403；文件不存在 404
    # -----------------------------------------------------------------------
    @router.get("/materials/{account_id}/{filename}")
    async def get_customer_material(
        account_id: int,
        filename: str,
        user: dict = Depends(current_user),
    ) -> Response:
        """查看名下客户的物料文件（HTML/PNG 等），鉴权后返回内容。

        可见范围（有账号即可见）：
        - 经销商（acc.tenant_id 匹配）：查看名下全部客户物料
        - 客户账号（user.tenant_id == acc.client_tenant_id）：查看自己的物料（如白皮书）
        - FDE/其他员工：由经销商在工作台转发链接（链接带经销商 token，仍走本鉴权）
        """
        from .models import PartnerDemoAccount

        async with session_scope() as db, bypass_tenant_filter():
            acc = (
                await db.execute(
                    select(PartnerDemoAccount).where(PartnerDemoAccount.id == account_id)
                )
            ).scalar_one_or_none()
            if acc is None:
                raise HTTPException(status_code=404, detail="demo account not found")
            user_tid = user["tenant_id"]
            if acc.tenant_id != user_tid and acc.client_tenant_id != user_tid:
                raise HTTPException(status_code=403, detail="无权访问该客户的物料")

        # 文件名白名单（防路径穿越）
        if not filename or "/" in filename or ".." in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="非法文件名")
        base = Path(__file__).resolve().parent / "materials" / str(account_id)
        fp = base / filename
        if not fp.is_file():
            raise HTTPException(status_code=404, detail="物料文件不存在")

        media_type = "text/html; charset=utf-8" if fp.suffix == ".html" else "image/png"
        return Response(content=fp.read_bytes(), media_type=media_type)

    return router


__all__ = ["build_router"]
