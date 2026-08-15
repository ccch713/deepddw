"""金蝶 HRIS 适配器（DDW AI Hub v5.4 — 模块 C1）。

API 风格：金蝶云·星空 OpenAPI（OAuth2 + REST）。
- 鉴权：``POST /auth/login`` → access_token
- 员工：``GET /hr/employees``
- 培训记录：``POST /hr/training/records``
- 考核：``POST /hr/assessment/records``

参考：金蝶云开发者文档（简化版）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.hris_adapters.base import BaseHRISAdapter, HRISAuthError, HRISError

logger = logging.getLogger(__name__)


class KingdeeAdapter(BaseHRISAdapter):
    name = "kingdee"
    display_name = "金蝶云·星空"
    default_base_url = "https://api.kingdee.com"

    config_schema = {
        "fields": [
            {"name": "base_url", "label": "服务器地址", "required": False, "type": "url"},
            {"name": "app_key", "label": "App Key", "required": True, "type": "text"},
            {"name": "app_secret", "label": "App Secret", "required": True, "type": "password"},
            {"name": "tenant_code", "label": "租户编码", "required": True, "type": "text"},
        ],
    }

    async def authenticate(self, config: Dict[str, Any]) -> bool:
        client = await self._get_client()
        try:
            r = await client.post(
                "/auth/login",
                json={
                    "app_key": config.get("app_key"),
                    "app_secret": config.get("app_secret"),
                    "tenant_code": config.get("tenant_code"),
                },
            )
            if r.status_code != 200:
                raise HRISAuthError(f"kingdee auth failed: {r.status_code} {r.text[:200]}")
            data = r.json()
            self._access_token = data.get("data", {}).get("access_token")
            if not self._access_token:
                raise HRISAuthError("kingdee auth: missing access_token in response")
            client.headers["Authorization"] = f"Bearer {self._access_token}"
            logger.info("kingdee auth ok tenant=%s", config.get("tenant_code"))
            return True
        except HRISAuthError:
            raise
        except Exception as e:  # noqa: BLE001
            raise HRISAuthError(f"kingdee auth error: {e}") from e

    async def sync_employees(self, since: Optional[str] = None) -> List[Dict[str, Any]]:
        client = await self._get_client()
        params: Dict[str, Any] = {"page_size": 200}
        if since:
            params["modified_after"] = since
        r = await client.get("/hr/employees", params=params)
        if r.status_code != 200:
            raise HRISError(f"sync_employees failed: {r.status_code} {r.text[:200]}")
        data = r.json().get("data", [])
        return [
            {
                "external_id": str(e.get("id")),
                "name": e.get("name"),
                "phone": e.get("mobile"),
                "email": e.get("email"),
                "department": (e.get("dept") or {}).get("name"),
                "title": e.get("position"),
                "status": "active" if e.get("enabled", True) else "inactive",
                "raw": e,
            }
            for e in data
        ]

    async def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        client = await self._get_client()
        r = await client.get(f"/hr/employees/{employee_id}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise HRISError(f"get_employee failed: {r.status_code}")
        e = r.json().get("data") or {}
        return {
            "external_id": str(e.get("id")),
            "name": e.get("name"),
            "phone": e.get("mobile"),
            "email": e.get("email"),
            "department": (e.get("dept") or {}).get("name"),
            "title": e.get("position"),
            "status": "active" if e.get("enabled", True) else "inactive",
            "raw": e,
        }

    async def push_training_record(self, record: Dict[str, Any]) -> bool:
        client = await self._get_client()
        body = {
            "employee_id": record.get("user_id"),
            "course_id": record.get("course_id"),
            "duration_minutes": int((record.get("duration") or 0) / 60),
            "score": record.get("score"),
            "completed_at": record.get("completed_at"),
        }
        r = await client.post("/hr/training/records", json=body)
        if r.status_code not in (200, 201):
            raise HRISError(f"push_training_record failed: {r.status_code} {r.text[:200]}")
        return True

    async def push_assessment_result(self, result: Dict[str, Any]) -> bool:
        client = await self._get_client()
        body = {
            "employee_id": result.get("user_id"),
            "assessment_id": result.get("assessment_id"),
            "score": result.get("score"),
            "grade": result.get("grade"),
            "details": result.get("details"),
        }
        r = await client.post("/hr/assessment/records", json=body)
        if r.status_code not in (200, 201):
            raise HRISError(f"push_assessment_result failed: {r.status_code} {r.text[:200]}")
        return True


__all__ = ["KingdeeAdapter"]
