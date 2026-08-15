"""DDW Admin module - sqladmin 集成入口。

- :func:`setup_admin` 在 FastAPI lifespan 中调用，挂载 SQLAdmin 到 /admin
- :class:`AdminAuth` 提供密码认证（DDW_SQLADMIN_PASSWORD 环境变量，未设置则禁用认证）
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

logger = logging.getLogger(__name__)

ADMIN_SESSION_KEY = "ddw_sql_admin"


class AdminAuth(AuthenticationBackend):
    """SQLAdmin 密码认证后端。

    密码来源：环境变量 ``DDW_SQLADMIN_PASSWORD``。
    未设置该变量时 authenticate 恒 False（拒绝访问）——安全默认。
    """

    async def login(self, request: Request) -> bool:
        form = await request.form()
        password = str(form.get("password", ""))
        expected = os.getenv("DDW_SQLADMIN_PASSWORD", "")
        if not expected:
            return False
        if password == expected:
            request.session.update({ADMIN_SESSION_KEY: True})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.pop(ADMIN_SESSION_KEY, None)
        return True

    async def authenticate(self, request: Request) -> bool:
        if not os.getenv("DDW_SQLADMIN_PASSWORD"):
            return False
        return bool(request.session.get(ADMIN_SESSION_KEY, False))


def setup_admin(app: Any, engine: Any, *, title: str = "DDW SQL Admin") -> Optional[Admin]:
    """创建并挂载 SQLAdmin 实例（路径 /admin）。

    Args:
        app: FastAPI 实例
        engine: SQLAlchemy AsyncEngine
        title: 后台标题

    Returns:
        Admin 实例；失败返回 None（不阻断服务启动）
    """
    try:
        from core.admin.views import register_admin_views

        auth = AdminAuth(secret_key=os.getenv("DDW_JWT_SECRET", "ddw-dev-secret"))
        admin = Admin(
            app,
            engine=engine,
            title=title,
            authentication_backend=auth,
        )
        registered = register_admin_views(admin)
        logger.info("SQLAdmin mounted at /admin, %d views registered", registered)
        return admin
    except Exception as exc:  # noqa: BLE001
        logger.warning("SQLAdmin setup skipped: %s", exc)
        return None


__all__ = ["AdminAuth", "setup_admin"]
