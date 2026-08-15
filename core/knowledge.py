"""知识库权限 API（DDW AI Hub v5.4 — 补充 C）。

端点：
- ``GET  /api/v1/knowledge/bases``
- ``POST /api/v1/knowledge/bases``
- ``GET  /api/v1/knowledge/bases/{id}/permissions``
- ``PUT  /api/v1/knowledge/bases/{id}/permissions``
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.auth.jwt import current_admin, current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


# 内存存储（dev）：key = (tenant_id, base_id) → 权限矩阵
_KB_PERMS: Dict[Tuple[int, int], Dict[str, Any]] = {}


class KnowledgeBaseReq(BaseModel):
    name: str = Field(..., max_length=200)
    category: str = Field(..., max_length=40)


_BASE_CATALOG = [
    {"id": 1, "name": "企业公共知识库", "category": "public"},
    {"id": 2, "name": "客服知识库-A", "category": "cs"},
    {"id": 3, "name": "财务知识库", "category": "finance"},
    {"id": 4, "name": "研发知识库", "category": "rd"},
    {"id": 5, "name": "采购知识库", "category": "procurement"},
    {"id": 6, "name": "高层决策知识库", "category": "executive"},
    {"id": 7, "name": "岗位知识库-销售", "category": "role"},
    {"id": 8, "name": "设备操作手册-注塑机", "category": "equipment"},
]


def _visible_categories(role: str) -> List[str]:
    """根据角色返回可见类别。"""
    table = {
        "owner": [b["category"] for b in _BASE_CATALOG],
        "admin": ["public", "cs", "rd", "procurement", "role", "equipment"],
        "member": ["public", "cs", "role", "equipment"],
    }
    return table.get(role, ["public"])


@router.get("/bases", response_model=List[Dict[str, Any]])
async def list_bases(user: Dict[str, Any] = Depends(current_user)) -> List[Dict[str, Any]]:
    visible = set(_visible_categories(user["role"]))
    out = []
    for b in _BASE_CATALOG:
        if b["category"] in visible:
            row = dict(b)
            row["read"] = True
            row["write"] = user["role"] in {"owner", "admin"} and b["category"] != "executive"
            row["delete"] = user["role"] == "owner"
            out.append(row)
    return out


@router.post("/bases", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_base(req: KnowledgeBaseReq, user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    if user["role"] != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅 owner 可创建知识库")
    new_id = max(b["id"] for b in _BASE_CATALOG) + 1
    return {"id": new_id, "name": req.name, "category": req.category, "created_at": datetime.utcnow().isoformat()}


@router.get("/bases/{base_id}/permissions", response_model=Dict[str, Any])
async def get_permissions(base_id: int, user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    if user["role"] != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅 owner 可查看权限")
    perms = _KB_PERMS.get((user["tenant_id"], base_id))
    if perms is None:
        perms = {
            "base_id": base_id,
            "permissions": {
                "all_users": ["read"],
                "dept_cs": ["read", "write"],
                "dept_finance": ["read"],
                "dept_rd": ["read", "write", "delete"],
                "role_admin": ["read", "write", "delete", "manage"],
            },
        }
    return perms


@router.put("/bases/{base_id}/permissions", response_model=Dict[str, Any])
async def update_permissions(base_id: int, payload: Dict[str, Any], user: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    if user["role"] != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅 owner 可修改权限")
    _KB_PERMS[(user["tenant_id"], base_id)] = {"base_id": base_id, "permissions": payload.get("permissions", {})}
    return _KB_PERMS[(user["tenant_id"], base_id)]


__all__ = ["router"]
