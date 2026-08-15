"""Workday HRIS 适配器（DDW AI Hub v5.4 — 模块 C1）。

API 风格：Workday REST API（OAuth2 Client Credentials + JSON）。
- 鉴权：``POST /ccx/oauth2/{tenant}/token`` → access_token
- 员工：``GET /ccx/api/v1/{tenant}/workers``
- 培训记录：``POST /ccx/api/v1/{tenant}/trainingRecords``
- 考核：``POST /ccx/api/v1/{tenant}/performanceReviews``

参考：Workday API 开发者文档（2026-07 恢复重写版）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.hris_adapters.base import BaseHRISAdapter, HRISAuthError, HRISError

logger = logging.getLogger(__name__)


class WorkdayAdapter(BaseHRISAdapter):
    name = "workday"
    display_name = "Workday"
    default_base_url = "https://wd2-impl-services1.workday.com"

    config_schema = {
        "fields": [
            {"name": "base_url", "label": "服务器地址", "required": False, "type": "url"},
            {"name": "tenant", "label": "租户名", "required": True, "type": "text"},
            {"name": "client_id", "label": "Client ID", "required": True, "type": "text"},
            {"name": "client_secret", "label": "Client Secret", "required": True, "type": "password"},
            {"name": "username", "label": "用户名", "required": False, "type": "text"},
            {"name": "password", "label": "密码", "required": False, "type": "password"},
        ],
    }

    async def authenticate(self, config: Dict[str, Any]) -> bool:
        client = await self._get_client()
        try:
            tenant = config.get("tenant", "")
            r = await client.post(
                f"/ccx/oauth2/{tenant}/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": config.get("client_id"),
                    "client_secret": config.get("client_secret"),
                },
            )
            if r.status_code != 200:
                raise HRISAuthError(f"workday auth failed: {r.status_code} {r.text[:200]}")
            data = r.json()
            self._access_token = data.get("access_token")
            if not self._access_token:
                raise HRISAuthError("workday auth: missing access_token in response")
            client.headers["Authorization"] = f"Bearer {self._access_token}"
            logger.info("workday auth ok tenant=%s", tenant)
            return True
        except HRISAuthError:
            raise
        except Exception as e:  # noqa: BLE001
            raise HRISAuthError(f"workday auth error: {e}") from e

    async def sync_employees(self, since: Optional[str] = None) -> List[Dict[str, Any]]:
        client = await self._get_client()
        tenant = self.config.get("tenant", "")
        params: Dict[str, Any] = {"limit": 100, "offset": 0}
        if since:
            params["last_modified_after"] = since
        r = await client.get(f"/ccx/api/v1/{tenant}/workers", params=params)
        if r.status_code != 200:
            raise HRISError(f"sync_employees failed: {r.status_code} {r.text[:200]}")
        data = r.json()
        workers = data.get("data", [])
        return [
            {
                "external_id": str(w.get("worker_id") or w.get("id")),
                "name": (w.get("name") or {}).get("full_name") or w.get("display_name"),
                "phone": (w.get("contact") or {}).get("phone"),
                "email": (w.get("contact") or {}).get("email"),
                "department": (w.get("organization") or {}).get("name"),
                "title": w.get("job_title"),
                "status": "active" if w.get("status") in (None, "Active") else "inactive",
                "raw": w,
            }
            for w in workers
        ]

    async def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        client = await self._get_client()
        tenant = self.config.get("tenant", "")
        r = await client.get(f"/ccx/api/v1/{tenant}/workers/{employee_id}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise HRISError(f"get_employee failed: {r.status_code} {r.text[:200]}")
        w = r.json().get("data", {})
        return {
            "external_id": str(w.get("worker_id") or w.get("id")),
            "name": (w.get("name") or {}).get("full_name") or w.get("display_name"),
            "phone": (w.get("contact") or {}).get("phone"),
            "email": (w.get("contact") or {}).get("email"),
            "department": (w.get("organization") or {}).get("name"),
            "title": w.get("job_title"),
            "status": "active" if w.get("status") in (None, "Active") else "inactive",
            "raw": w,
        }

    async def push_training_record(self, record: Dict[str, Any]) -> bool:
        client = await self._get_client()
        tenant = self.config.get("tenant", "")
        payload = {
            "worker_id": record.get("employee_external_id"),
            "course_name": record.get("course_name"),
            "completed_on": record.get("completed_on"),
            "score": record.get("score"),
        }
        r = await client.post(f"/ccx/api/v1/{tenant}/trainingRecords", json=payload)
        if r.status_code not in (200, 201):
            raise HRISError(f"push_training_record failed: {r.status_code} {r.text[:200]}")
        return True

    async def push_assessment_result(self, result: Dict[str, Any]) -> bool:
        client = await self._get_client()
        tenant = self.config.get("tenant", "")
        payload = {
            "worker_id": result.get("employee_external_id"),
            "review_title": result.get("title"),
            "score": result.get("score"),
            "assessed_on": result.get("assessed_on"),
        }
        r = await client.post(f"/ccx/api/v1/{tenant}/performanceReviews", json=payload)
        if r.status_code not in (200, 201):
            raise HRISError(f"push_assessment_result failed: {r.status_code} {r.text[:200]}")
        return True


__all__ = ["WorkdayAdapter"]
