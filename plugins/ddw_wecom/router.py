"""DDW 企业微信插件 API 路由。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .models import MessageType, OAuthCallback, WeComDepartment
from .service import WeComService

logger = logging.getLogger(__name__)

_service = WeComService()


def get_service() -> WeComService:
    return _service


# ---- Request Schemas ----


class SyncDepartmentsReq(BaseModel):
    departments: list[WeComDepartment]


class BindIdentityReq(BaseModel):
    wecom_userid: str
    provider: str
    external_id: str


class SendMessageReq(BaseModel):
    template_id: str
    content: str
    msg_type: MessageType = MessageType.TEXT


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/plugins/ddw-wecom", tags=["ddw-wecom"])

    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-wecom", "version": "1.0.0", "status": "ok"}

    # ---- OAuth ----

    @router.get("/oauth/authorize")
    async def oauth_authorize(state: str = "") -> dict:
        """跳转企微授权页。"""
        svc = get_service()
        url = svc.get_authorize_url(state=state)
        return {"authorize_url": url, "state": state}

    @router.get("/oauth/callback")
    async def oauth_callback(code: str, state: str = "") -> dict:
        """企微 OAuth 回调：code 换 token → JIT 建号/登录。"""
        svc = get_service()
        try:
            callback = OAuthCallback(code=code, state=state)
            user = svc.handle_oauth_callback(callback)
            return {
                "wecom_userid": user.wecom_userid,
                "ddw_user_id": user.ddw_user_id,
                "name": user.name,
                "corp_id": user.corp_id,
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ---- 部门同步 ----

    @router.post("/departments/sync", status_code=201)
    async def sync_departments(data: SyncDepartmentsReq) -> dict:
        """同步企微部门到 DDW。"""
        svc = get_service()
        synced = svc.sync_departments(data.departments)
        return {"synced_count": len(synced), "departments": [d.model_dump() for d in synced]}

    @router.get("/departments")
    async def list_departments() -> list[dict]:
        svc = get_service()
        return [d.model_dump() for d in svc.list_departments()]

    # ---- 用户 ----

    @router.get("/users")
    async def list_users() -> list[dict]:
        svc = get_service()
        return [u.model_dump() for u in svc.list_users()]

    @router.get("/users/{wecom_userid}")
    async def get_user(wecom_userid: str) -> dict:
        svc = get_service()
        user = svc.get_user(wecom_userid)
        if not user:
            raise HTTPException(status_code=404, detail=f"user {wecom_userid} not found")
        return user.model_dump()

    # ---- External Identity ----

    @router.post("/users/bind-identity", status_code=201)
    async def bind_identity(data: BindIdentityReq) -> dict:
        svc = get_service()
        user = svc.bind_external_identity(data.wecom_userid, data.provider, data.external_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"user {data.wecom_userid} not found")
        return user.model_dump()

    # ---- 消息通道（占位） ----

    @router.post("/messages/send")
    async def send_message(data: SendMessageReq) -> dict:
        """发送消息（占位，不实际推送）。"""
        svc = get_service()
        msg = svc.send_message(data.template_id, data.content, data.msg_type)
        return msg.model_dump()

    @router.get("/messages")
    async def list_messages() -> list[dict]:
        svc = get_service()
        return [m.model_dump() for m in svc.list_messages()]

    return router


__all__ = ["build_router", "get_service"]
