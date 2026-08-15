"""北森 HRIS 适配器（DDW AI Hub v5.4 — 模块 C1）。

API 风格：北森一体化 HR SaaS 开放平台（OAuth2）。
- 鉴权：``POST /oauth/token``
- 员工档案：``GET /api/hr/employee``
- 培训模块：``POST /api/training/record``
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from core.hris_adapters.base import BaseHRISAdapter, HRISAuthError, HRISError

logger = logging.getLogger(__name__)


class BeisenAdapter(BaseHRISAdapter):
    name = "beisen"
    display_name = "北森云 HR"
    default_base_url = "https://openapi.beisen.com"

    config_schema = {
        "fields": [
            {"name": "base_url", "label": "API 地址", "required": False, "type": "url"},
            {"name": "client_id", "label": "Client ID", "required": True, "type": "text"},
            {"name": "client_secret", "label": "Client Secret", "required": True, "type": "password"},
            {"name": "env", "label": "环境", "required": True, "type": "select", "options": ["prod", "sandbox"]},
        ],
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None, tenant_id: Optional[int] = None) -> None:
        super().__init__(config, tenant_id)
        self._token_expires_at: float = 0.0

    async def authenticate(self, config: Dict[str, Any]) -> bool:
        client = await self._get_client()
        try:
            r = await client.post(
                "/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": config.get("client_id"),
                    "client_secret": config.get("client_secret"),
                    "env": config.get("env", "prod"),
                },
            )
            if r.status_code != 200:
                raise HRISAuthError(f"beisen auth failed: {r.status_code} {r.text[:200]}")
            data = r.json()
            self._access_token = data.get("access_token")
            expires_in = int(data.get("expires_in", 7200))
            self._token_expires_at = time.time() + expires_in - 60
            client.headers["Authorization"] = f"Bearer {self._access_token}"
            logger.info("beisen auth ok env=%s", config.get("env"))
            return True
        except HRISAuthError:
            raise
        except Exception as e:  # noqa: BLE001
            raise HRISAuthError(f"beisen auth error: {e}") from e

    async def _ensure_token(self) -> httpx.AsyncClient:
        client = await self._get_client()
        if not self._access_token or time.time() >= self._token_expires_at:
            await self.authenticate(self.config)
        return client

    async def sync_employees(self, since: Optional[str] = None) -> List[Dict[str, Any]]:
        client = await self._ensure_token()
        params: Dict[str, Any] = {"pageSize": 200}
        if since:
            params["modifiedSince"] = since
        r = await client.get("/api/hr/employee/list", params=params)
        if r.status_code != 200:
            raise HRISError(f"sync_employees failed: {r.status_code}")
        data = r.json().get("result", {}).get("data", [])
        return [
            {
                "external_id": str(e.get("EmployeeId")),
                "name": e.get("Name"),
                "phone": e.get("Mobile"),
                "email": e.get("Email"),
                "department": (e.get("DeptInfo") or {}).get("DeptName"),
                "title": e.get("JobTitle"),
                "status": "active" if e.get("Status") == 1 else "inactive",
                "raw": e,
            }
            for e in data
        ]

    async def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        client = await self._ensure_token()
        r = await client.get(f"/api/hr/employee/{employee_id}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise HRISError(f"get_employee failed: {r.status_code}")
        e = r.json().get("result") or {}
        return {
            "external_id": str(e.get("EmployeeId")),
            "name": e.get("Name"),
            "phone": e.get("Mobile"),
            "email": e.get("Email"),
            "department": (e.get("DeptInfo") or {}).get("DeptName"),
            "title": e.get("JobTitle"),
            "status": "active" if e.get("Status") == 1 else "inactive",
            "raw": e,
        }

    async def push_training_record(self, record: Dict[str, Any]) -> bool:
        client = await self._ensure_token()
        body = {
            "employeeId": record.get("user_id"),
            "courseCode": record.get("course_id"),
            "durationMinutes": int((record.get("duration") or 0) / 60),
            "score": record.get("score"),
            "completedAt": record.get("completed_at"),
        }
        r = await client.post("/api/training/record", json=body)
        if r.status_code not in (200, 201):
            raise HRISError(f"push_training_record failed: {r.status_code} {r.text[:200]}")
        return True

    async def push_assessment_result(self, result: Dict[str, Any]) -> bool:
        client = await self._ensure_token()
        body = {
            "employeeId": result.get("user_id"),
            "assessmentCode": result.get("assessment_id"),
            "totalScore": result.get("score"),
            "grade": result.get("grade"),
            "details": result.get("details"),
        }
        r = await client.post("/api/training/assessment", json=body)
        if r.status_code not in (200, 201):
            raise HRISError(f"push_assessment_result failed: {r.status_code} {r.text[:200]}")
        return True


__all__ = ["BeisenAdapter"]
