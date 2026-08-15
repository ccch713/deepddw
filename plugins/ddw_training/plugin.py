"""DDW 培训插件 Plugin 类（DDW AI Hub v5.4 — 培训插件 E1）。

复用平台 ``sdk.plugin_base.PluginBase``。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter

from plugins.ddw_training import PLUGIN_NAME, VERSION
from plugins.ddw_training.services import (
    AssessmentEngine,
    CoursewareManager,
    ProgressTracker,
    SessionState,
    SocraticEngine,
)
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        config_dir = Path(__file__).resolve().parent / "config"
        self.socratic = SocraticEngine(config_dir=config_dir)
        self.assessment = AssessmentEngine()
        self.progress = ProgressTracker()
        self.courseware = CoursewareManager(config_dir=config_dir)
        self._active_sessions: Dict[str, SessionState] = {}

        # 暴露 MCP tool：ddw.training.start_session / get_progress（覆盖 stub）
        try:
            from core.mcp.tools import Tool, ToolRegistry

            reg: ToolRegistry = self._get_mcp_registry()
            if reg is not None:
                async def start_session(args, ctx):
                    sid = self.start_training_session(
                        user_id=int(args["user_id"]),
                        tenant_id=int(ctx.get("tenant_id", 1)) if ctx else 1,
                        subject=args.get("subject") or self.config.get("default_subject", "physics"),
                        course_id=args.get("course_id", "default"),
                    )
                    return {"content": [{"type": "text", "text": f"已启动培训会话 {sid}"}], "session_id": sid}

                async def get_progress(args, ctx):
                    uid = int(args.get("user_id") or 0)
                    if not uid:
                        return {"content": [{"type": "text", "text": "缺少 user_id"}]}
                    s = self.progress.user_summary(uid)
                    return {"content": [{"type": "text", "text": str(s)}], "summary": s}

                reg.register(Tool(
                    name="ddw.training.start_session",
                    description="启动 DDW 培训会话（覆盖 stub）",
                    parameters={"properties": {"user_id": {"type": "string"}, "subject": {"type": "string"}, "course_id": {"type": "string"}}, "required": ["user_id"]},
                    handler=start_session,
                    plugin_name=PLUGIN_NAME,
                ), override=True)
                reg.register(Tool(
                    name="ddw.training.get_progress",
                    description="查询学习进度（覆盖 stub）",
                    parameters={"properties": {"user_id": {"type": "string"}, "session_id": {"type": "string"}}},
                    handler=get_progress,
                    plugin_name=PLUGIN_NAME,
                ), override=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("MCP tool override failed: %s", e)

        # 注册 router（直接挂到 app，prefix 由 build_router 设置）
        from plugins.ddw_training.router import build_router
        self._router: APIRouter = build_router(self)
        self.app.include_router(self._router)
        logger.info("ddw-training plugin %s initialized", VERSION)

    def _get_mcp_registry(self):
        try:
            from core.mcp.server import get_mcp_server
            return get_mcp_server().tools
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------ #
    # 业务接口（被 router 调用）
    # ------------------------------------------------------------------ #

    def start_training_session(
        self,
        user_id: int,
        tenant_id: int,
        subject: str,
        course_id: str,
        session_uuid: Optional[str] = None,
    ) -> str:
        """创建内存会话。session_uuid 由调用方（router）生成，以便与 DB 记录对齐。"""
        if not session_uuid:
            import uuid
            session_uuid = uuid.uuid4().hex[:16]
        session = SessionState(
            session_id=session_uuid, user_id=user_id, tenant_id=tenant_id,
            course_id=course_id, subject=subject,
        )
        self._active_sessions[session_uuid] = session
        self.socratic.start_session(session)
        return session_uuid

    async def chat(self, session_id: str, message: str) -> Dict[str, Any]:
        session = self._active_sessions.get(session_id)
        if session is None:
            return {"error": "session not found"}
        return await self.socratic.next_turn(session, message)

    def get_session(self, session_id: str):
        """读取内存会话（router 回写 DB 时用）。"""
        return self._active_sessions.get(session_id)

    def close_session(self, session_id: str) -> None:
        """会话结束（router 同步状态到 DB 后调用）。"""
        self._active_sessions.pop(session_id, None)


__all__ = ["Plugin"]
