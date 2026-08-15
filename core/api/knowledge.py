"""知识库权限 API（DDW AI Hub v5.4 — 补充 C，2026-08-09 持久化升级）。

.. deprecated::
    本模块端点自 2026-08-11 起标记为 deprecated。请改用插件新端点：
    ``/api/v1/plugins/ddw-knowledge-hierarchy/kb/*``（三层权限版本，
    支持真向量检索，见 TASK_SPEC_D_KB向量检索合并.md）。

端点（deprecated）：
|- ``GET  /api/v1/knowledge/bases``
|- ``POST /api/v1/knowledge/bases``
|- ``GET  /api/v1/knowledge/bases/{id}/permissions``
|- ``PUT  /api/v1/knowledge/bases/{id}/permissions``

存储：SQLite (ddw_main.db)，表 kb_bases / kb_base_permissions。
2026-08-09 升级：从内存 _KB_PERMS 改为持久化（解决"重启后权限丢失"问题）。

注意：逻辑保留，仅 docstring + 响应字段标注 deprecated，避免破坏现有调用。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.jwt import current_admin, current_user
from core.database.models import KnowledgeBase as KBModel, KnowledgeBasePermission as KBPermModel
from core.database.session import session_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


# ─── 默认知识库种子（首次启动时插入）───
_DEFAULT_BASES: List[Dict[str, str]] = [
    {"name": "企业公共知识库", "category": "public"},
    {"name": "客服知识库-A", "category": "cs"},
    {"name": "财务知识库", "category": "finance"},
    {"name": "研发知识库", "category": "rd"},
    {"name": "采购知识库", "category": "procurement"},
    {"name": "高层决策知识库", "category": "executive"},
    {"name": "岗位知识库-销售", "category": "role"},
    {"name": "设备操作手册-注塑机", "category": "equipment"},
]


_DEFAULT_PERMS: Dict[str, List[str]] = {
    "all_users": ["read"],
    "dept_cs": ["read", "write"],
    "dept_finance": ["read"],
    "dept_rd": ["read", "write", "delete"],
    "role_admin": ["read", "write", "delete", "manage"],
}


async def _ensure_seed_bases(s: AsyncSession) -> None:
    """首次启动时插入默认知识库（idempotent：已存在则跳过）。"""
    from sqlalchemy import func as sqlfunc

    result = await s.execute(select(sqlfunc.count(KBModel.id)))
    count = result.scalar() or 0
    if count > 0:
        return
    for b in _DEFAULT_BASES:
        s.add(KBModel(name=b["name"], category=b["category"]))
    await s.commit()
    logger.info("knowledge.py: seeded %d default bases", len(_DEFAULT_BASES))


class KnowledgeBaseReq(BaseModel):
    name: str = Field(..., max_length=200)
    category: str = Field(..., max_length=40)


def _visible_categories(role: str) -> List[str]:
    """根据角色返回可见类别。"""
    table = {
        "owner": [
            "public", "cs", "finance", "rd", "procurement",
            "executive", "role", "equipment",
        ],
        "admin": ["public", "cs", "rd", "procurement", "role", "equipment"],
        "member": ["public", "cs", "role", "equipment"],
    }
    return table.get(role, ["public"])


@router.get("/bases", response_model=List[Dict[str, Any]])
async def list_bases(user: Dict[str, Any] = Depends(current_user)) -> List[Dict[str, Any]]:
    """列出当前用户可见的知识库。

    .. deprecated::
        请改用 ``GET /api/v1/plugins/ddw-knowledge-hierarchy/kb``（三层权限版本）。
    """
    visible = set(_visible_categories(user["role"]))
    out: List[Dict[str, Any]] = []
    async with session_scope() as s:
        await _ensure_seed_bases(s)
        result = await s.execute(select(KBModel).order_by(KBModel.id))
        bases = result.scalars().all()
    for b in bases:
        if b.category in visible:
            out.append({
                "id": b.id,
                "name": b.name,
                "category": b.category,
                "read": True,
                "write": user["role"] in {"owner", "admin"} and b.category != "executive",
                "delete": user["role"] == "owner",
                "_deprecated": True,
                "_migrate_to": "/api/v1/plugins/ddw-knowledge-hierarchy/kb",
            })
    return out


@router.post("/bases", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_base(req: KnowledgeBaseReq, user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """创建新知识库（仅 owner/admin）。

    .. deprecated::
        请改用 ``POST /api/v1/plugins/ddw-knowledge-hierarchy/kb``。
    """
    if user["role"] != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅 owner 可创建知识库")
    async with session_scope() as s:
        new_b = KBModel(name=req.name, category=req.category)
        s.add(new_b)
        await s.flush()
        bid = new_b.id
        await s.commit()
    return {
        "id": bid,
        "name": req.name,
        "category": req.category,
        "created_at": datetime.utcnow().isoformat(),
        "_deprecated": True,
        "_migrate_to": "/api/v1/plugins/ddw-knowledge-hierarchy/kb",
    }


@router.get("/bases/{base_id}/permissions", response_model=Dict[str, Any])
async def get_permissions(base_id: int, user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """读取知识库权限矩阵（仅 owner/admin）。

    .. deprecated::
        插件新版暂无独立 permissions 端点（合并入 KB scope/owner 字段），
        建议改用 ``GET /api/v1/plugins/ddw-knowledge-hierarchy/kb/{kb_id}``。
    """
    if user["role"] != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅 owner 可查看权限")
    async with session_scope() as s:
        result = await s.execute(
            select(KBPermModel).where(
                KBPermModel.base_id == base_id,
                KBPermModel.tenant_id == user["tenant_id"],
            )
        )
        row: Optional[KBPermModel] = result.scalar_one_or_none()
        if row is None:
            return {
                "base_id": base_id,
                "permissions": _DEFAULT_PERMS,
                "_deprecated": True,
                "_migrate_to": "/api/v1/plugins/ddw-knowledge-hierarchy/kb",
            }
        return {
            "base_id": base_id,
            "permissions": row.permissions,
            "_deprecated": True,
            "_migrate_to": "/api/v1/plugins/ddw-knowledge-hierarchy/kb",
        }


@router.put("/bases/{base_id}/permissions", response_model=Dict[str, Any])
async def update_permissions(base_id: int, payload: Dict[str, Any], user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    """更新知识库权限矩阵（仅 owner/admin），重启后保留。

    .. deprecated::
        插件新版用 KB scope（company/department/personal）统一管理权限，
        不再需要单独的 permissions 端点。请改用插件路径。
    """
    if user["role"] != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅 owner 可修改权限")
    perms = payload.get("permissions", {})
    async with session_scope() as s:
        # upsert by (tenant_id, base_id)
        result = await s.execute(
            select(KBPermModel).where(
                KBPermModel.base_id == base_id,
                KBPermModel.tenant_id == user["tenant_id"],
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = KBPermModel(
                base_id=base_id,
                tenant_id=user["tenant_id"],
                permissions=perms,
            )
            s.add(row)
        else:
            row.permissions = perms
        await s.commit()
    return {
        "base_id": base_id,
        "permissions": perms,
        "_deprecated": True,
        "_migrate_to": "/api/v1/plugins/ddw-knowledge-hierarchy/kb",
    }


__all__ = ["router"]