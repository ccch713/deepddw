"""用户绑定 API（DDW AI Hub v5.4 — 模块 B6）。

端点：
- ``GET    /api/v1/user/bindings``          查询已绑定的第三方账号
- ``POST   /api/v1/user/bindings/wechat``   绑定微信（stub）
- ``POST   /api/v1/user/bindings/dingtalk`` 绑定钉钉（stub）
- ``DELETE /api/v1/user/bindings/{id}``     解绑
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.auth.jwt import current_user
from core.database.models import UserBinding
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/user", tags=["user"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BindWechatReq(BaseModel):
    code: str = Field(..., description="微信授权 code")


class BindDingtalkReq(BaseModel):
    code: str = Field(..., description="钉钉授权 code")


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/bindings", response_model=List[Dict[str, Any]])
async def list_bindings(user: Dict[str, Any] = Depends(current_user)) -> List[Dict[str, Any]]:
    """查询当前用户已绑定的第三方账号。"""
    async with session_scope() as session, bypass_tenant_filter():
        rows = (
            await session.execute(
                select(UserBinding)
                .where(UserBinding.user_id == user["user_id"], UserBinding.is_active == True)  # noqa: E712
                .order_by(UserBinding.id)
            )
        ).scalars().all()
        return [
            {
                "id": b.id,
                "provider": b.provider,
                "provider_uid": b.provider_uid,
                "provider_name": b.provider_name,
                "binding_type": b.binding_type,
                "is_primary": b.is_primary,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in rows
        ]


@router.post("/bindings/wechat", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def bind_wechat(req: BindWechatReq, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    """绑定微信账号（stub：生成授权链接，实际需对接微信 OAuth）。"""
    # stub: 实际应调用微信 OAuth 获取 openid
    provider_uid = f"wx_stub_{req.code}"
    provider_name = f"微信用户_{req.code[:6]}"

    async with session_scope() as session, bypass_tenant_filter():
        # 检查是否已绑定
        existing = (
            await session.execute(
                select(UserBinding).where(
                    UserBinding.user_id == user["user_id"],
                    UserBinding.provider == "wechat",
                    UserBinding.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已绑定微信账号")

        binding = UserBinding(
            tenant_id=user["tenant_id"],
            user_id=user["user_id"],
            provider="wechat",
            provider_uid=provider_uid,
            provider_name=provider_name,
            binding_type="login",
            is_primary=False,
            is_active=True,
        )
        session.add(binding)
        await session.commit()
        await session.refresh(binding)
        return {
            "id": binding.id,
            "provider": binding.provider,
            "provider_uid": binding.provider_uid,
            "provider_name": binding.provider_name,
            "message": "微信绑定成功（stub）",
        }


@router.post("/bindings/dingtalk", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def bind_dingtalk(req: BindDingtalkReq, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    """绑定钉钉账号（stub：生成授权链接，实际需对接钉钉 OAuth）。"""
    provider_uid = f"dt_stub_{req.code}"
    provider_name = f"钉钉用户_{req.code[:6]}"

    async with session_scope() as session, bypass_tenant_filter():
        existing = (
            await session.execute(
                select(UserBinding).where(
                    UserBinding.user_id == user["user_id"],
                    UserBinding.provider == "dingtalk",
                    UserBinding.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已绑定钉钉账号")

        binding = UserBinding(
            tenant_id=user["tenant_id"],
            user_id=user["user_id"],
            provider="dingtalk",
            provider_uid=provider_uid,
            provider_name=provider_name,
            binding_type="login",
            is_primary=False,
            is_active=True,
        )
        session.add(binding)
        await session.commit()
        await session.refresh(binding)
        return {
            "id": binding.id,
            "provider": binding.provider,
            "provider_uid": binding.provider_uid,
            "provider_name": binding.provider_name,
            "message": "钉钉绑定成功（stub）",
        }


@router.delete("/bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unbind(binding_id: int, user: Dict[str, Any] = Depends(current_user)):
    """解绑第三方账号（软删除：is_active=False）。"""
    async with session_scope() as session, bypass_tenant_filter():
        binding = (
            await session.execute(
                select(UserBinding).where(
                    UserBinding.id == binding_id,
                    UserBinding.user_id == user["user_id"],
                )
            )
        ).scalar_one_or_none()
        if binding is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="绑定不存在")
        binding.is_active = False
        await session.commit()


__all__ = ["router"]
