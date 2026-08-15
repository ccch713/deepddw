"""DDW 权限审计插件测试用例（8 个，覆盖用户CRUD、部门树、RBAC、审计日志）。"""

from __future__ import annotations

import pytest

from plugins.ddw_authz.models import Permission, UserStatus
from plugins.ddw_authz.service import AuthService


@pytest.fixture
def svc() -> AuthService:
    return AuthService()


# ===========================================================================
# 1. 用户 CRUD — 创建 + 查询
# ===========================================================================


def test_user_create_and_get(svc: AuthService):
    user = svc.create_user(id="u1", name="张三", department_id="d1", roles=["admin"])
    assert user.id == "u1"
    assert user.name == "张三"
    assert user.status == UserStatus.ACTIVE

    fetched = svc.get_user("u1")
    assert fetched is not None
    assert fetched.name == "张三"


# ===========================================================================
# 2. 用户 CRUD — 更新 + 删除
# ===========================================================================


def test_user_update_and_delete(svc: AuthService):
    svc.create_user(id="u2", name="李四")

    updated = svc.update_user("u2", name="李四改", status=UserStatus.LOCKED)
    assert updated is not None
    assert updated.name == "李四改"
    assert updated.status == UserStatus.LOCKED

    assert svc.delete_user("u2") is True
    assert svc.get_user("u2") is None
    assert svc.delete_user("u2") is False


# ===========================================================================
# 3. 用户创建重复 ID 抛异常
# ===========================================================================


def test_user_create_duplicate_raises(svc: AuthService):
    svc.create_user(id="u3", name="王五")
    with pytest.raises(ValueError, match="已存在"):
        svc.create_user(id="u3", name="王五2")


# ===========================================================================
# 4. 部门树 — 多层级构建
# ===========================================================================


def test_department_tree(svc: AuthService):
    svc.create_department(id="d-root", name="总公司")
    svc.create_department(id="d-hr", name="人力资源部", parent_id="d-root")
    svc.create_department(id="d-eng", name="技术部", parent_id="d-root")
    svc.create_department(id="d-fe", name="前端组", parent_id="d-eng")

    tree = svc.get_department_tree()
    assert len(tree) == 1
    root = tree[0]
    assert root["id"] == "d-root"
    assert len(root["children"]) == 2

    eng_node = next(c for c in root["children"] if c["id"] == "d-eng")
    assert len(eng_node["children"]) == 1
    assert eng_node["children"][0]["id"] == "d-fe"


# ===========================================================================
# 5. 部门创建 — 上级不存在抛异常
# ===========================================================================


def test_department_parent_not_found(svc: AuthService):
    with pytest.raises(ValueError, match="上级部门.*不存在"):
        svc.create_department(id="d-orphan", name="孤儿部门", parent_id="d-ghost")


# ===========================================================================
# 6. RBAC 权限校验 — has_permission + check_permission
# ===========================================================================


def test_rbac_permission_check(svc: AuthService):
    # 创建角色并绑定权限
    svc.create_role(
        id="r-admin",
        name="管理员",
        permissions=[
            Permission(resource="order", action="read"),
            Permission(resource="order", action="write"),
            Permission(resource="user", action="delete"),
        ],
    )
    svc.create_role(
        id="r-viewer",
        name="查看者",
        permissions=[Permission(resource="order", action="read")],
    )

    # 创建用户并分配角色
    svc.create_user(id="u-admin", name="管理员A", roles=["r-admin"])
    svc.create_user(id="u-viewer", name="查看者B", roles=["r-viewer"])

    # 管理员有 order:read + order:write + user:delete
    assert svc.has_permission("u-admin", "order", "read") is True
    assert svc.has_permission("u-admin", "order", "write") is True
    assert svc.has_permission("u-admin", "user", "delete") is True

    # 查看者只有 order:read
    assert svc.has_permission("u-viewer", "order", "read") is True
    assert svc.has_permission("u-viewer", "order", "write") is False

    # check_permission 同时记录审计日志
    result = svc.check_permission("u-viewer", "order", "write")
    assert result is False

    # 未分配角色的用户无权限
    svc.create_user(id="u-nobody", name="无角色")
    assert svc.has_permission("u-nobody", "order", "read") is False

    # 非活跃用户无权限
    svc.update_user("u-admin", status=UserStatus.INACTIVE)
    assert svc.has_permission("u-admin", "order", "read") is False


# ===========================================================================
# 7. 审计日志 — 自动记录敏感操作
# ===========================================================================


def test_audit_logs_auto_recorded(svc: AuthService):
    svc.create_user(id="u-log", name="日志用户")
    svc.update_user("u-log", name="日志用户改", operator_id="u-log")
    svc.delete_user("u-log", operator_id="u-log")

    logs = svc.get_audit_logs(user_id="u-log")
    operations = [l.operation for l in logs]
    assert "create_user" in operations
    assert "update_user" in operations
    assert "delete_user" in operations


# ===========================================================================
# 8. 审计日志 — 按操作类型过滤
# ===========================================================================


def test_audit_logs_filter_by_operation(svc: AuthService):
    svc.create_user(id="u-f1", name="过滤1")
    svc.create_user(id="u-f2", name="过滤2")
    svc.create_department(id="d-f", name="过滤部门")
    svc.create_role(id="r-f", name="过滤角色")

    user_logs = svc.get_audit_logs(operation="create_user")
    assert all(l.operation == "create_user" for l in user_logs)
    assert len(user_logs) >= 2

    dept_logs = svc.get_audit_logs(operation="create_department")
    assert len(dept_logs) >= 1
    assert dept_logs[0].resource == "department:d-f"
