"""飞书通讯录 + 多维表格适配器（DDW AI Hub v5.4 — 模块 C1）。

API 风格：飞书 OpenAPI。
- 鉴权：``POST /auth/v3/tenant_access_token/internal``
- 员工：``GET /contact/v3/users``
- 培训记录：写入多维表格（Bitable）``POST /bitable/v1/apps/{app_token}/tables/{table_id}/records``
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.hris_adapters.base import BaseHRISAdapter, HRISAuthError, HRISError

logger = logging.getLogger(__name__)


class FeishuAdapter(BaseHRISAdapter):
    name = "feishu"
    display_name = "飞书通讯录"
    default_base_url = "https://open.feishu.cn/open-apis"

    config_schema = {
        "fields": [
            {"name": "app_id", "label": "App ID", "required": True, "type": "text"},
            {"name": "app_secret", "label": "App Secret", "required": True, "type": "password"},
            {"name": "bitable_app_token", "label": "多维表格 App Token（培训记录用）", "required": False, "type": "text"},
            {"name": "bitable_table_id", "label": "多维表格 Table ID（培训记录用）", "required": False, "type": "text"},
        ],
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None, tenant_id: Optional[int] = None) -> None:
        super().__init__(config, tenant_id)
        self._token_expires_at: float = 0.0

    async def authenticate(self, config: Dict[str, Any]) -> bool:
        client = await self._get_client()
        try:
            r = await client.post(
                "/auth/v3/tenant_access_token/internal",
                json={"app_id": config.get("app_id"), "app_secret": config.get("app_secret")},
            )
            if r.status_code != 200:
                raise HRISAuthError(f"feishu auth failed: {r.status_code} {r.text[:200]}")
            data = r.json()
            if data.get("code", 0) != 0:
                raise HRISAuthError(f"feishu auth api error: {data}")
            self._access_token = data.get("tenant_access_token")
            expires_in = int(data.get("expire", 7200))
            self._token_expires_at = time.time() + expires_in - 60
            client.headers["Authorization"] = f"Bearer {self._access_token}"
            logger.info("feishu auth ok app=%s", config.get("app_id"))
            return True
        except HRISAuthError:
            raise
        except Exception as e:  # noqa: BLE001
            raise HRISAuthError(f"feishu auth error: {e}") from e

    async def _ensure_token(self) -> httpx.AsyncClient:  # type: ignore[name-defined]
        from httpx import AsyncClient  # noqa
        client = await self._get_client()
        if not self._access_token or time.time() >= self._token_expires_at:
            await self.authenticate(self.config)
        return client

    async def sync_employees(self, since: Optional[str] = None) -> List[Dict[str, Any]]:
        client = await self._ensure_token()
        params: Dict[str, Any] = {"page_size": 50, "department_id": "0"}
        r = await client.get("/contact/v3/users", params=params)
        if r.status_code != 200:
            raise HRISError(f"sync_employees failed: {r.status_code}")
        data = r.json().get("data", {}).get("items", [])
        return [
            {
                "external_id": str(u.get("user_id") or u.get("open_id")),
                "name": u.get("name"),
                "phone": u.get("mobile"),
                "email": u.get("email"),
                "department": (u.get("department_ids") or [""])[0],
                "title": u.get("job_title"),
                "status": "active" if not u.get("departure_time") else "inactive",
                "raw": u,
            }
            for u in data
        ]

    async def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        client = await self._ensure_token()
        r = await client.get(f"/contact/v3/users/{employee_id}")
        data = r.json()
        if data.get("code") in (230001, 230002):
            return None
        if data.get("code", 0) != 0:
            raise HRISError(f"get_employee api error: {data}")
        u = data.get("data", {}).get("user", {})
        return {
            "external_id": str(u.get("user_id") or u.get("open_id")),
            "name": u.get("name"),
            "phone": u.get("mobile"),
            "email": u.get("email"),
            "department": (u.get("department_ids") or [""])[0],
            "title": u.get("job_title"),
            "status": "active" if not u.get("departure_time") else "inactive",
            "raw": u,
        }

    async def push_training_record(self, record: Dict[str, Any]) -> bool:
        client = await self._ensure_token()
        app_token = self.config.get("bitable_app_token")
        table_id = self.config.get("bitable_table_id")
        if not (app_token and table_id):
            # 未配置 Bitable：降级为发消息
            logger.warning("feishu bitable not configured, skip record push")
            return False
        body = {
            "fields": {
                "员工ID": str(record.get("user_id", "")),
                "课程ID": str(record.get("course_id", "")),
                "时长(秒)": int(record.get("duration") or 0),
                "得分": record.get("score"),
                "完成时间": record.get("completed_at"),
            }
        }
        r = await client.post(
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            json=body,
        )
        if r.status_code not in (200, 201):
            raise HRISError(f"push_training_record failed: {r.status_code} {r.text[:200]}")
        return True

    async def push_assessment_result(self, result: Dict[str, Any]) -> bool:
        client = await self._ensure_token()
        app_token = self.config.get("bitable_app_token")
        table_id = self.config.get("bitable_table_id")
        if not (app_token and table_id):
            return False
        body = {
            "fields": {
                "员工ID": str(result.get("user_id", "")),
                "评估ID": str(result.get("assessment_id", "")),
                "总分": result.get("score"),
                "等级": result.get("grade"),
                "明细": str(result.get("details", ""))[:2000],
            }
        }
        r = await client.post(
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            json=body,
        )
        if r.status_code not in (200, 201):
            raise HRISError(f"push_assessment_result failed: {r.status_code} {r.text[:200]}")
        return True


__all__ = ["FeishuAdapter"]
