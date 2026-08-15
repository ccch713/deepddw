"""License status routes（P1 客户水印 / P2 换码广播 / P4 跨机 Broker）。

- ``GET /api/v1/license/info``：返回当前部署 license 状态
  （licensed / customer / license_code / valid_to / days_left /
  in_grace_period / warning_level + P2 新增 supersede 换码状态 + P4 附带
  broker 健康摘要），供管理后台前端水印条与到期警告使用；同时作为新码激活
  检测点（license_cache.json 的 license_key 变化 → 记录旧码 7 天倒计时广播）。
- ``GET /api/v1/license/broker/state``：授权权威端点（P4）——业务节点拉取
  权威 license_state；令牌 + HMAC 签名 + 时间戳校验（非 JWT，节点程序使用）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from core.api_response import ok
from core.auth.jwt import current_user
from core.utils.license_broker import (
    broker_health,
    get_authoritative_state,
    state_version,
    sync_from_broker,
    verify_broker_request,
)
from core.utils.license_state import get_supersede_status, sync_license_state
from core.utils.license_validator import evaluate_license

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/license", tags=["license"])


@router.get("/info")
async def license_info(user: Dict[str, Any] = Depends(current_user)) -> Any:
    """返回当前部署的 license 状态（前端水印/提前警告/换码广播数据源）。"""
    # P4：懒拉取 Broker 权威 state 覆盖本机（TTL 内不重复拉取；不可达回退）
    sync_from_broker()

    status = evaluate_license()
    # P2：新码激活检测（cache 的 license_key 变化 → 旧码 superseded + 7 天倒计时）
    sync_license_state(status.get("license_code"))

    supersede = get_supersede_status()
    status["supersede"] = supersede
    # P4：附带 broker 健康摘要
    status["broker"] = broker_health()
    # P2：旧码超 7 天倒计时 → 信息层失效（fail-closed，复用 P0 判定语义）
    if supersede.get("superseded") and supersede.get("grace_expired"):
        status["licensed"] = False
        status["warning_level"] = "superseded"

    logger.info(
        "license info customer=%s license_code=%s valid_to=%s days_left=%s "
        "in_grace_period=%s warning_level=%s superseded=%s superseded_by=%s "
        "broker_enabled=%s by_user=%s",
        status.get("customer"),
        status.get("license_code"),
        status.get("valid_to"),
        status.get("days_left"),
        status.get("in_grace_period"),
        status.get("warning_level"),
        supersede.get("superseded"),
        supersede.get("superseded_by"),
        status.get("broker", {}).get("enabled"),
        user.get("user_id"),
    )
    return ok(status)


@router.get("/broker/state")
async def broker_state(request: Request, response: Response) -> Any:
    """授权权威端点（P4）：业务节点拉取权威 license_state。

    鉴权：X-DDW-Broker-Token + X-DDW-Broker-Ts + X-DDW-Broker-Sig
    （HMAC-SHA256(token, f"{ts}:{path}")，时间戳 ±300s 防重放）。
    未启用 Broker（license.broker.enabled=false 或未配置令牌）→ 404。
    """
    from core.utils.license_broker import HEADER_SIG, HEADER_TOKEN, HEADER_TS

    if not broker_health().get("enabled"):
        raise HTTPException(
            status_code=404, detail="Broker 未启用（license.broker.enabled=false）"
        )
    token = request.headers.get(HEADER_TOKEN, "")
    ts = request.headers.get(HEADER_TS, "")
    sig = request.headers.get(HEADER_SIG, "")
    if not verify_broker_request(token, ts, sig, request.url.path):
        raise HTTPException(status_code=401, detail="Broker 令牌或签名校验失败")

    state = get_authoritative_state()
    # 响应头捎带权威 state 版本（数据同步捎带通道：任何调用方/未来同步通道
    # 可从响应头直接感知授权状态是否已更新，无需解析 body）
    response.headers["X-DDW-License-State-Version"] = state_version(state)
    response.headers["X-DDW-License-Superseded"] = str(
        bool(state.get("superseded_by"))
    ).lower()
    return ok({"state": state, "version": state_version(state)})


__all__ = ["router"]
