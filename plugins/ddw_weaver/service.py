"""泛微E9组织架构集成 - 核心服务"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from plugins.ddw_weaver.models import (
    ImportSource,
    ImportTask,
    PortalConfig,
    TaskStatus,
    WeaverDepartment,
    WeaverUser,
)

logger = logging.getLogger(__name__)


class WeaverService:
    """泛微E9集成服务"""

    def __init__(self) -> None:
        self._departments: dict[str, WeaverDepartment] = {}
        self._users: dict[str, WeaverUser] = {}
        self._tasks: dict[str, ImportTask] = {}
        self._portal_configs: dict[str, PortalConfig] = {}
        self._dept_ddw_mapping: dict[str, str] = {}

    # ---- CSV导入 ----

    def parse_csv_departments(self, content: str) -> list[WeaverDepartment]:
        """解析CSV格式的部门数据

        CSV列: dept_id, name, code, parent_id
        """
        reader = csv.DictReader(io.StringIO(content))
        departments: list[WeaverDepartment] = []
        for row in reader:
            dept = WeaverDepartment(
                dept_id=row.get("dept_id", "").strip(),
                name=row.get("name", "").strip(),
                code=row.get("code", "").strip(),
                parent_id=row.get("parent_id", "").strip() or None,
            )
            if dept.dept_id and dept.name:
                departments.append(dept)
        return departments

    def parse_csv_users(self, content: str) -> list[WeaverUser]:
        """解析CSV格式的用户数据

        CSV列: user_id, name, employee_no, dept_id, position, status
        """
        reader = csv.DictReader(io.StringIO(content))
        users: list[WeaverUser] = []
        for row in reader:
            user = WeaverUser(
                user_id=row.get("user_id", "").strip(),
                name=row.get("name", "").strip(),
                employee_no=row.get("employee_no", "").strip(),
                dept_id=row.get("dept_id", "").strip(),
                position=row.get("position", "").strip(),
                status=row.get("status", "active").strip(),
            )
            if user.user_id and user.name:
                users.append(user)
        return users

    def import_departments_csv(self, content: str) -> ImportTask:
        """CSV导入部门"""
        task = ImportTask(
            task_id=uuid.uuid4().hex[:12],
            source=ImportSource.CSV,
            status=TaskStatus.RUNNING,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        try:
            departments = self.parse_csv_departments(content)
            for dept in departments:
                self._departments[dept.dept_id] = dept
            task.imported_count = len(departments)
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_count = 1
            task.errors.append(str(e))
        self._tasks[task.task_id] = task
        return task

    def import_users_csv(self, content: str) -> ImportTask:
        """CSV导入用户"""
        task = ImportTask(
            task_id=uuid.uuid4().hex[:12],
            source=ImportSource.CSV,
            status=TaskStatus.RUNNING,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        try:
            users = self.parse_csv_users(content)
            for user in users:
                self._users[user.user_id] = user
            task.imported_count = len(users)
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_count = 1
            task.errors.append(str(e))
        self._tasks[task.task_id] = task
        return task

    # ---- API导入占位 ----

    def import_from_api(
        self,
        base_url: str,
        app_id: str = "",
        app_secret: str = "",
    ) -> ImportTask:
        """API导入占位（预留泛微开放平台接口）

        实际对接时需调用泛微E9 REST API获取组织架构数据。
        """
        task = ImportTask(
            task_id=uuid.uuid4().hex[:12],
            source=ImportSource.API,
            status=TaskStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        # TODO: 实现泛微E9 API调用
        # 1. 认证: POST {base_url}/api/ec/dev/auth/getToken
        # 2. 部门: GET {base_url}/api/ec/dev/org/department/list
        # 3. 用户: GET {base_url}/api/ec/dev/org/user/list
        logger.info("API import placeholder: base_url=%s", base_url)
        self._tasks[task.task_id] = task
        return task

    # ---- 部门/用户映射 ----

    def map_department(self, dept_id: str, ddw_org_id: str) -> bool:
        """E9部门 → DDW组织映射"""
        if dept_id in self._departments:
            self._departments[dept_id].ddw_org_id = ddw_org_id
            self._dept_ddw_mapping[dept_id] = ddw_org_id
            return True
        return False

    def get_departments(self) -> list[WeaverDepartment]:
        """获取所有E9部门"""
        return list(self._departments.values())

    def get_users(self) -> list[WeaverUser]:
        """获取所有E9用户"""
        return list(self._users.values())

    def get_department_by_id(self, dept_id: str) -> Optional[WeaverDepartment]:
        return self._departments.get(dept_id)

    def get_user_by_id(self, user_id: str) -> Optional[WeaverUser]:
        return self._users.get(user_id)

    # ---- 导入任务管理 ----

    def get_tasks(self) -> list[ImportTask]:
        """获取所有导入任务"""
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> Optional[ImportTask]:
        return self._tasks.get(task_id)

    # ---- 门户嵌入配置 ----

    def save_portal_config(self, config: PortalConfig) -> PortalConfig:
        """保存门户嵌入配置"""
        self._portal_configs[config.portal_id] = config
        return config

    def get_portal_config(self, portal_id: str) -> Optional[PortalConfig]:
        return self._portal_configs.get(portal_id)

    def list_portal_configs(self) -> list[PortalConfig]:
        return list(self._portal_configs.values())
