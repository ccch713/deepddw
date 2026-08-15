"""FastAPI APIRouter —— 社会化登录全部端点。"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from core.auth.jwt import current_admin, current_user

from .config_manager import ConfigManager, mask_secret
from .schemas import (
    ChannelConfig,
    ChannelConfigSave,
    ChannelStatus,
    ErrorResponse,
)
from .services import (
    bind_provider,
    build_auth_redirect,
    handle_callback,
    list_bindings,
    unbind_provider,
)


def build_router(config_manager: ConfigManager) -> APIRouter:
    """构建社会化登录路由。"""

    router = APIRouter(
        prefix="/api/v1/plugins/ddw-social-login",
        tags=["ddw-social-login"],
    )

    # ================================================================
    # GET /auth/{provider} —— 生成授权 URL 并 302 跳转
    # ================================================================

    @router.get(
        "/auth/{provider}",
        summary="第三方授权跳转",
        responses={302: {"description": "重定向到第三方授权页"}, 400: {"model": ErrorResponse}},
    )
    async def auth_redirect(
        provider: str,
        request: Request,
        next: str = Query(default="/pal.html", description="登录后跳转页"),
    ) -> RedirectResponse:
        base_url = str(request.base_url).rstrip("/")
        # 安全校验：next 必须是相对路径，防止开放重定向
        if not next.startswith("/") or "://" in next:
            next = "/pal.html"
        auth_url = await build_auth_redirect(provider, config_manager, base_url, next=next)
        return RedirectResponse(url=auth_url, status_code=302)

    # ================================================================
    # GET /callback/{provider} —— 第三方回调
    # ================================================================

    @router.get(
        "/callback/{provider}",
        summary="第三方 OAuth 回调",
        responses={302: {"description": "重定向到前端并携带 token"}, 401: {"model": ErrorResponse}},
    )
    async def callback(
        provider: str,
        request: Request,
        code: str = Query(..., description="授权码"),
        state: str = Query(..., description="CSRF state"),
    ) -> RedirectResponse:
        result = await handle_callback(provider, code, state, request, config_manager)

        # 从 state 缓存读取 next 参数（build_auth_redirect 里存的）
        from .services import _state_cache
        cached = _state_cache.get(state, {})
        redirect_uri = cached.get("next", "/pal.html")

        # 安全校验：next 必须是相对路径，防止开放重定向
        if not redirect_uri.startswith("/") or "://" in redirect_uri:
            redirect_uri = "/pal.html"

        token_data = json.dumps(result["user"], ensure_ascii=False)
        url = f"{redirect_uri}#access_token={result['access_token']}&user={token_data}"
        return RedirectResponse(url=url, status_code=302)

    # ================================================================
    # GET /channels —— 返回已启用通道列表
    # ================================================================

    @router.get(
        "/channels",
        response_model=List[ChannelStatus],
        summary="返回全部通道状态（前端渲染按钮用）",
    )
    async def get_channels() -> List[ChannelStatus]:
        return config_manager.get_channel_status_list()

    # ================================================================
    # POST /config —— 管理员保存通道配置
    # ================================================================

    @router.post(
        "/config",
        summary="管理员保存通道配置",
        responses={200: {"description": "保存成功"}, 403: {"model": ErrorResponse}},
    )
    async def save_config(
        body: ChannelConfigSave,
        user: Dict[str, Any] = Depends(current_admin),
    ) -> Dict[str, Any]:
        config_manager.save_channels(body.channels)
        return {"ok": True}

    # ================================================================
    # GET /config —— 管理员查看当前配置（secret 脱敏）
    # ================================================================

    @router.get(
        "/config",
        response_model=List[ChannelConfig],
        summary="管理员查看当前配置（secret 脱敏）",
    )
    async def get_config(
        user: Dict[str, Any] = Depends(current_admin),
    ) -> List[ChannelConfig]:
        configs = config_manager.get_channel_list()
        # 脱敏
        for ch in configs:
            ch.app_secret = mask_secret(ch.app_secret)
        return configs

    # ================================================================
    # POST /bind/{provider} —— 已登录用户绑定第三方
    # ================================================================

    @router.post(
        "/bind/{provider}",
        summary="已登录用户绑定第三方账号",
        responses={200: {"description": "绑定成功"}, 401: {"model": ErrorResponse}},
    )
    async def bind_social(
        provider: str,
        request: Request,
        code: str = Query(..., description="授权码"),
        state: str = Query(..., description="CSRF state"),
        user: Dict[str, Any] = Depends(current_user),
    ) -> Dict[str, Any]:
        result = await bind_provider(
            user_id=user["user_id"],
            tenant_id=user["tenant_id"],
            provider=provider,
            code=code,
            state=state,
            config_manager=config_manager,
        )
        return result

    # ================================================================
    # DELETE /bind/{provider} —— 已登录用户解绑
    # ================================================================

    @router.delete(
        "/bind/{provider}",
        summary="已登录用户解绑第三方账号",
        responses={200: {"description": "解绑成功"}, 404: {"model": ErrorResponse}},
    )
    async def unbind_social(
        provider: str,
        user: Dict[str, Any] = Depends(current_user),
    ) -> Dict[str, Any]:
        result = await unbind_provider(
            user_id=user["user_id"],
            provider=provider,
        )
        return result

    # ================================================================
    # GET /bindings —— 查看当前用户的绑定列表
    # ================================================================

    @router.get(
        "/bindings",
        response_model=List[Dict[str, Any]],
        summary="查看当前用户的绑定列表",
    )
    async def get_bindings(
        user: Dict[str, Any] = Depends(current_user),
    ) -> List[Dict[str, Any]]:
        return await list_bindings(user["user_id"])

    return router
