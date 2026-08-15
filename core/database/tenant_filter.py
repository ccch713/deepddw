"""SQLAlchemy 自动租户过滤层（DDW AI Hub v5.4 — 模块 A1）

设计目标：
1. 通过 ``contextvars.ContextVar`` 绑定当前请求的 tenant_id，避免显式传参
2. 监听 ``before_flush``：自动为 ``TenantMixin`` 新对象注入 tenant_id
3. 监听 ``do_orm_execute``：自动为 SELECT/UPDATE/DELETE 注入 ``WHERE tenant_id = ?``
4. 提供 ``bypass_tenant_filter()`` 上下文管理器（admin 全局操作用）
5. 与现有 v0.1 的 ``sdk/plugin_base.py`` / ``customer-service`` 等插件兼容

注意：
- 触发器仅对标记了 ``__tenant_aware__ = True`` 的 mapper 生效（白名单）
- 集成点：``core/main.py`` 的 ``lifespan`` 中调用 ``install_tenant_hooks(engine)``
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
from typing import Any, Iterator, Optional

from sqlalchemy import event, literal
from sqlalchemy.orm import ORMExecuteState, with_loader_criteria
from sqlalchemy.orm.session import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ContextVar：当前请求的 tenant_id
# ---------------------------------------------------------------------------

_tenant_id_var: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "ddw_tenant_id", default=None
)
_bypass_var: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "ddw_tenant_bypass", default=False
)


def get_tenant_context() -> Optional[int]:
    """返回当前请求上下文的 tenant_id；未设置时为 None。"""
    return _tenant_id_var.get()


def set_tenant_context(tenant_id: Optional[int]) -> contextvars.Token:
    """设置当前请求上下文的 tenant_id。返回一个 Token（用于 reset）。"""
    return _tenant_id_var.set(tenant_id)


def reset_tenant_context(token: contextvars.Token) -> None:
    """还原上下文。"""
    _tenant_id_var.reset(token)


@contextlib.contextmanager
def tenant_scope(tenant_id: int) -> Iterator[None]:
    """进入租户作用域（自动 reset）。"""
    token = set_tenant_context(tenant_id)
    try:
        yield
    finally:
        reset_tenant_context(token)


@contextlib.asynccontextmanager
async def bypass_tenant_filter() -> Iterator[None]:
    """跳过租户过滤（admin 全局操作 / 后台任务用）。

    用法::

        async with bypass_tenant_filter():
            ...
    """
    token = _bypass_var.set(True)
    try:
        yield
    finally:
        _bypass_var.reset(token)


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

# 仅对带此属性的 mapper 启用自动注入（白名单，避免影响系统表 / 审计表）
TENANT_AWARE_ATTR = "__tenant_aware__"


def _mapper_is_tenant_aware(mapper: Any) -> bool:
    """判断 mapper 是否启用了租户感知。"""
    return bool(getattr(mapper.class_, TENANT_AWARE_ATTR, False))


def _before_flush(session: Session, flush_context: Any, instances: Any) -> None:  # noqa: ANN401
    """自动为 TenantMixin 新对象注入 tenant_id。

    仅在以下条件同时满足时生效：
    - 当前未处于 bypass 模式
    - mapper 标记了 __tenant_aware__ = True
    - 对象尚未显式设置 tenant_id
    """
    if _bypass_var.get():
        return

    tenant_id = get_tenant_context()
    if tenant_id is None:
        return

    from sqlalchemy import inspect as sa_inspect

    for obj in session.new:
        try:
            mapper = sa_inspect(type(obj))
        except Exception:  # noqa: BLE001
            continue
        if not _mapper_is_tenant_aware(mapper):
            continue
        if getattr(obj, "tenant_id", None) is None:
            obj.tenant_id = tenant_id
            logger.debug("auto-injected tenant_id=%s on %s", tenant_id, type(obj).__name__)


def _do_orm_execute(state: ORMExecuteState) -> None:
    """为 SELECT/UPDATE/DELETE 自动注入 WHERE tenant_id = ?。"""
    if _bypass_var.get():
        return

    # 只对绑定到 Session 的语句生效；Session-less 走 system-level 路径
    if state.is_select or state.is_update or state.is_delete:
        tenant_id = get_tenant_context()
        if tenant_id is None:
            return

        # with_loader_criteria 的 entity 参数必须是**单个**实体类：
        # 传 lambda/function → root_entity=function → _all_mappers() 崩；
        # 传 tuple/list  → root_entity=tuple → 同样崩（500）。
        # 正确做法：对每个 tenant-aware 类单独建 option，叠加到 statement。
        # 从 declarative registry 动态收集（插件模型启动后注册也在内；跨 1.4/2.0）。
        from core.database.session import Base

        aware_classes = tuple(
            cls
            for cls in Base.registry._class_registry.values()
            if isinstance(cls, type) and getattr(cls, TENANT_AWARE_ATTR, False)
        )
        if not aware_classes:
            return

        # SQLAlchemy lambda 要求 closure var 是 SQL element；用 literal_column 包装
        tenant_id_sql = literal(tenant_id)

        def _safe_tenant_filter(cls: Any) -> Any:
            """仅对租户感知模型注入 tenant_id 条件；防御性处理 SQLAlchemy 传入非 mapper 的情况。"""
            try:
                return cls.tenant_id == tenant_id_sql
            except (AttributeError, TypeError):
                return None

        options = [
            with_loader_criteria(cls, _safe_tenant_filter, include_aliases=True)
            for cls in aware_classes
        ]
        state.statement = state.statement.options(*options)


def install_tenant_hooks(engine: Any) -> None:
    """在 FastAPI lifespan 启动时调用，绑定事件监听器。

    注意：
    - ``before_flush`` 是 Session 级事件，绑到 ``Session`` 类上
    - ``do_orm_execute`` 也是 Session 级事件（SQLAlchemy 2.x），绑到 ``Session`` 类上
    - Session 级事件对所有 Session 生效；通过 ``_mapper_is_tenant_aware`` 白名单过滤
    """
    from sqlalchemy.orm import Session as OrmSession

    # before_flush: 自动为新对象注入 tenant_id
    try:
        event.listen(OrmSession, "before_flush", _before_flush)
    except Exception:  # noqa: BLE001
        pass
    # do_orm_execute: 自动为 SELECT/UPDATE/DELETE 注入 WHERE tenant_id = ?
    try:
        event.listen(OrmSession, "do_orm_execute", _do_orm_execute)
    except Exception:  # noqa: BLE001
        pass
    logger.info("DDW tenant isolation hooks installed (Session.before_flush + Session.do_orm_execute)")


def remove_tenant_hooks(engine: Any) -> None:
    """测试或关闭时移除监听器。"""
    from sqlalchemy.orm import Session as OrmSession

    for target, ident, fn in (
        (OrmSession, "before_flush", _before_flush),
        (OrmSession, "do_orm_execute", _do_orm_execute),
    ):
        try:
            event.remove(target, ident, fn)
        except Exception:  # noqa: BLE001
            pass


__all__ = [
    "TENANT_AWARE_ATTR",
    "bypass_tenant_filter",
    "get_tenant_context",
    "install_tenant_hooks",
    "remove_tenant_hooks",
    "reset_tenant_context",
    "set_tenant_context",
    "tenant_scope",
]
