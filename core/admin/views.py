"""DDW AI Hub · Admin ModelView 注册（基于真实 ORM 字段，动态生成）。

只暴露实际存在的管理类 Model（不同部署版本 models.py 有差异，缺失自动跳过）：
- Tenant: 租户管理
- User: 用户列表
- WhitelistEntry: 手机号白名单
- LoginAudit: 登录审计（只读）
- KnowledgeBase: 知识库
- ChannelPartner: 渠道商

不暴露业务数据（Patient / Visit / MedicalRecord 等）。
"""

from __future__ import annotations

import logging

from sqladmin import Admin, ModelView

from core.database.models import (
    ChannelPartner,
    KnowledgeBase,
    LoginAudit,
    Tenant,
    User,
    WhitelistEntry,
)

logger = logging.getLogger(__name__)


def _build_view(model, *, name_plural, icon, columns, search=None, filters=None, sortable=None,
                can_create=True, can_edit=True, can_delete=True, page_size=50):
    """按模型动态生成 ModelView 子类。"""
    attrs = {
        "name": model.__name__,
        "name_plural": name_plural,
        "icon": icon,
        "column_list": columns,
        "can_create": can_create,
        "can_edit": can_edit,
        "can_delete": can_delete,
        "can_view_details": True,
        "page_size": page_size,
    }
    if search:
        attrs["column_searchable_list"] = search
    if filters:
        attrs["column_filters"] = filters
    if sortable:
        attrs["column_sortable_list"] = sortable
    return type(model.__name__ + "Admin", (ModelView,), attrs)


def register_admin_views(admin: Admin) -> int:
    """注册所有可用的 admin views 到 Admin 实例。

    Returns:
        注册成功的 view 数量
    """
    specs = [
        _build_view(
            Tenant,
            name_plural="租户",
            icon="fa-solid fa-building",
            columns=[Tenant.id, Tenant.name, Tenant.plan, Tenant.status, Tenant.contact_phone, Tenant.created_at],
            search=[Tenant.name],
            filters=[Tenant.plan, Tenant.status],
            sortable=[Tenant.id, Tenant.created_at],
        ),
        _build_view(
            User,
            name_plural="用户",
            icon="fa-solid fa-user",
            columns=[User.id, User.phone, User.name, User.role, User.status, User.tenant_id, User.created_at],
            search=[User.phone, User.name],
            filters=[User.role, User.status],
            sortable=[User.id, User.created_at],
        ),
        _build_view(
            WhitelistEntry,
            name_plural="白名单",
            icon="fa-solid fa-list",
            columns=[WhitelistEntry.id, WhitelistEntry.phone, WhitelistEntry.note, WhitelistEntry.tenant_id, WhitelistEntry.created_at],
            search=[WhitelistEntry.phone],
            sortable=[WhitelistEntry.id],
        ),
        _build_view(
            LoginAudit,
            name_plural="登录审计",
            icon="fa-solid fa-shield-halved",
            columns=[LoginAudit.id, LoginAudit.phone, LoginAudit.ip, LoginAudit.method, LoginAudit.success, LoginAudit.fail_reason, LoginAudit.created_at],
            search=[LoginAudit.phone, LoginAudit.ip],
            filters=[LoginAudit.success, LoginAudit.method],
            sortable=[LoginAudit.id, LoginAudit.created_at],
            can_create=False,
            can_edit=False,
            can_delete=False,
            page_size=100,
        ),
        _build_view(
            KnowledgeBase,
            name_plural="知识库",
            icon="fa-solid fa-book",
            columns=[KnowledgeBase.id, KnowledgeBase.name, KnowledgeBase.category, KnowledgeBase.created_at],
            search=[KnowledgeBase.name],
            filters=[KnowledgeBase.category],
            sortable=[KnowledgeBase.id],
        ),
        _build_view(
            ChannelPartner,
            name_plural="渠道商",
            icon="fa-solid fa-handshake",
            columns=[ChannelPartner.id, ChannelPartner.name, ChannelPartner.level, ChannelPartner.contact, ChannelPartner.commission_balance_cny, ChannelPartner.created_at],
            search=[ChannelPartner.name],
            sortable=[ChannelPartner.id],
        ),
    ]

    registered = 0
    for view in specs:
        try:
            admin.add_view(view)
            registered += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("skip admin view %s: %s", getattr(view, "name", "?"), exc)
    return registered
