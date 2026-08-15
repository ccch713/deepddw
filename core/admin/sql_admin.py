"""DDW AI Hub · Admin 后台 (sqladmin 集成)

设计原则 (FDE 友好):
1. **作用域隔离**: 只暴露管理类 Model (用户/权限/插件/系统配置),
   不暴露业务数据 (patient/medical_records 等) -- 业务数据走 plugin API
2. **权限模型**: 默认只读 + 可选 CRUD 显式标注
3. **审计可追溯**: 所有 admin 操作走 v1.0 §7.3 数字错误 ID 体系
4. **资源占用低**: sqladmin 仅 0.x 依赖, lazy 加载

使用:
    from core.admin.sql_admin import init_admin
    init_admin(app)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI
from sqladmin import Admin

from core.admin.views import register_admin_views
from core.database.factory import get_engine_factory
from core.error_id import E_PLUGIN_LOAD_FAILED  # v1.0 §7.3
from core.security.unicode_sanitizer import sanitize_unicode  # v1.0 §2.1

logger = logging.getLogger(__name__)


# 管理员后台路径前缀 (与 plugin API 隔离)
ADMIN_PATH = "/admin"
# 默认 admin 用户 (生产应该用真实认证, 这里是骨架)
ADMIN_USER = "admin"


def init_admin(app: FastAPI, base_url: str = ADMIN_PATH) -> Optional[Admin]:
    """初始化 sqladmin 并挂载到 FastAPI app.

    Args:
        app: FastAPI 应用实例
        base_url: admin 路径前缀 (默认 /admin)

    Returns:
        Admin 实例 (失败时返回 None)
    """
    try:
        # 暖机 sanitize_unicode 防止 v1.0 §2.1 冷启动失败
        _ = sanitize_unicode("warmup")

        # 获取 engine (复用 DDW 现有 EngineFactory)
        engine_factory = get_engine_factory()
        # 拿到主数据库的 engine (用于 admin)
        # 注意: deployment.yaml 中 url 字段可能是 env 占位符
        # 这里直接用 path 构造 sqlite URL (Standalone 模式兜底)
        from sqlalchemy.ext.asyncio import create_async_engine as _cae

        from core.config import get_deployment
        deploy = get_deployment()
        main_db = deploy.databases["main"]
        if main_db.engine == "sqlite":
            # 主动构造 sqlite URL
            sqlite_path = main_db.path or "./data/ddw_main.db"
            os.makedirs(os.path.dirname(os.path.abspath(sqlite_path)), exist_ok=True)
            engine = _cae(f"sqlite+aiosqlite:///{sqlite_path}")
        else:
            engine = engine_factory.create_engine("main")

        # 构造 Admin 实例
        admin = Admin(
            app=app,
            engine=engine,
            title="DDW AI Hub Admin",
            base_url=base_url,
        )

        # 注册所有 ModelView
        register_admin_views(admin)

        logger.info("✅ Admin mounted at %s (sqladmin 0.x)", base_url)
        logger.info("   访问: http://localhost:8500%s", base_url)
        logger.info("   文档: README.md §Admin 后台")
        return admin

    except Exception as exc:  # noqa: BLE001
        # 用 v1.0 §7.3 数字错误 ID
        logger.error(
            "Admin init failed (error_id=%d): %s",
            E_PLUGIN_LOAD_FAILED, exc,
        )
        return None


def get_admin_url() -> str:
    """返回 admin 访问 URL (FDE 用)."""
    return f"http://localhost:8500{ADMIN_PATH}"
