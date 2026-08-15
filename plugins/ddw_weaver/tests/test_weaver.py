"""泛微E9组织架构集成插件 - 测试"""
from __future__ import annotations

import pytest

from plugins.ddw_weaver.models import (
    AuthMethod,
    ImportSource,
    PortalConfig,
    TaskStatus,
)
from plugins.ddw_weaver.service import WeaverService


@pytest.fixture
def svc() -> WeaverService:
    return WeaverService()


# ---- 1. CSV解析测试 ----

class TestCsvParsing:
    def test_parse_departments_csv(self, svc: WeaverService) -> None:
        csv_content = (
            "dept_id,name,code,parent_id\n"
            "D001,技术部,TECH,\n"
            "D002,前端组,FE,D001\n"
            "D003,后端组,BE,D001\n"
        )
        depts = svc.parse_csv_departments(csv_content)
        assert len(depts) == 3
        assert depts[0].dept_id == "D001"
        assert depts[0].name == "技术部"
        assert depts[1].parent_id == "D001"

    def test_parse_users_csv(self, svc: WeaverService) -> None:
        csv_content = (
            "user_id,name,employee_no,dept_id,position,status\n"
            "U001,张三,E1001,D001,工程师,active\n"
            "U002,李四,E1002,D002,前端开发,active\n"
        )
        users = svc.parse_csv_users(csv_content)
        assert len(users) == 2
        assert users[0].name == "张三"
        assert users[1].position == "前端开发"

    def test_parse_empty_rows_skipped(self, svc: WeaverService) -> None:
        csv_content = (
            "dept_id,name,code,parent_id\n"
            "D001,技术部,TECH,\n"
            ",,,,  \n"
            "D002,产品部,PROD,\n"
        )
        depts = svc.parse_csv_departments(csv_content)
        assert len(depts) == 2


# ---- 2. 部门映射测试 ----

class TestDepartmentMapping:
    def test_map_department_success(self, svc: WeaverService) -> None:
        csv_content = "dept_id,name,code,parent_id\nD001,技术部,TECH,\n"
        svc.import_departments_csv(csv_content)
        ok = svc.map_department("D001", "DDW-ORG-001")
        assert ok is True
        dept = svc.get_department_by_id("D001")
        assert dept is not None
        assert dept.ddw_org_id == "DDW-ORG-001"

    def test_map_department_not_found(self, svc: WeaverService) -> None:
        ok = svc.map_department("NONEXISTENT", "DDW-ORG-999")
        assert ok is False


# ---- 3. 用户导入测试 ----

class TestUserImport:
    def test_import_users_csv(self, svc: WeaverService) -> None:
        csv_content = (
            "user_id,name,employee_no,dept_id,position,status\n"
            "U001,张三,E1001,D001,工程师,active\n"
            "U002,李四,E1002,D002,前端开发,inactive\n"
        )
        task = svc.import_users_csv(csv_content)
        assert task.status == TaskStatus.COMPLETED
        assert task.imported_count == 2
        assert task.source == ImportSource.CSV
        users = svc.get_users()
        assert len(users) == 2
        assert users[0].user_id == "U001"

    def test_import_departments_csv(self, svc: WeaverService) -> None:
        csv_content = "dept_id,name,code,parent_id\nD001,技术部,TECH,\nD002,产品部,PROD,\n"
        task = svc.import_departments_csv(csv_content)
        assert task.status == TaskStatus.COMPLETED
        assert task.imported_count == 2
        depts = svc.get_departments()
        assert len(depts) == 2


# ---- 4. 导入任务管理测试 ----

class TestImportTaskManagement:
    def test_task_created_on_csv_import(self, svc: WeaverService) -> None:
        csv_content = "dept_id,name,code,parent_id\nD001,技术部,TECH,\n"
        task = svc.import_departments_csv(csv_content)
        assert task.task_id
        assert task.created_at

        tasks = svc.get_tasks()
        assert len(tasks) == 1
        assert tasks[0].task_id == task.task_id

    def test_api_import_creates_pending_task(self, svc: WeaverService) -> None:
        task = svc.import_from_api(base_url="https://weaver.example.com")
        assert task.status == TaskStatus.PENDING
        assert task.source == ImportSource.API
        assert task.task_id

    def test_get_task_by_id(self, svc: WeaverService) -> None:
        csv_content = "dept_id,name,code,parent_id\nD001,技术部,TECH,\n"
        created = svc.import_departments_csv(csv_content)
        fetched = svc.get_task(created.task_id)
        assert fetched is not None
        assert fetched.task_id == created.task_id

    def test_get_nonexistent_task(self, svc: WeaverService) -> None:
        assert svc.get_task("nonexistent") is None


# ---- 5. 门户配置测试 ----

class TestPortalConfig:
    def test_save_and_retrieve_portal_config(self, svc: WeaverService) -> None:
        config = PortalConfig(
            portal_id="P001",
            embed_url="https://weaver.example.com/portal",
            css_inject="body { font-size: 14px; }",
            js_inject="console.log('loaded');",
            auth_method=AuthMethod.SSO,
        )
        saved = svc.save_portal_config(config)
        assert saved.portal_id == "P001"

        retrieved = svc.get_portal_config("P001")
        assert retrieved is not None
        assert retrieved.embed_url == "https://weaver.example.com/portal"
        assert retrieved.css_inject == "body { font-size: 14px; }"
        assert retrieved.auth_method == AuthMethod.SSO

    def test_list_portal_configs(self, svc: WeaverService) -> None:
        svc.save_portal_config(PortalConfig(portal_id="P1", embed_url="https://a.com"))
        svc.save_portal_config(PortalConfig(portal_id="P2", embed_url="https://b.com"))
        configs = svc.list_portal_configs()
        assert len(configs) == 2

    def test_portal_config_auth_methods(self, svc: WeaverService) -> None:
        for method in [AuthMethod.SSO, AuthMethod.TOKEN, AuthMethod.NONE]:
            config = PortalConfig(
                portal_id=f"P-{method.value}",
                embed_url="https://example.com",
                auth_method=method,
            )
            svc.save_portal_config(config)
            retrieved = svc.get_portal_config(f"P-{method.value}")
            assert retrieved is not None
            assert retrieved.auth_method == method
