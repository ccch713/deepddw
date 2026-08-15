"""Oracle HCM Cloud HRIS 适配器（DDW AI Hub v5.4 — 模块 C1）。

API 风格：Oracle HCM Cloud REST API（OAuth2 Client Credentials）。
- 鉴权：``POST /hcmRestApi/resources/latest/security/password``（简化 OAuth2 流程）
- 员工：``GET /hcmRestApi/resources/latest/workers``
- 培训记录：``POST /hcmRestApi/resources/latest/trainingRecords``
- 考核：``POST /hcmRestApi/resources/latest/performanceReviews``

参考：Oracle HCM Cloud REST API 文档（2026-07 恢复重写版）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.hris_adapters.base import BaseHRISAdapter, HRISAuthError, HRISError

logger = logging.getLogger(__name__)


class OracleHCMAdapter(BaseHRISAdapter):
    name = "oracle"
    display_name = "Oracle HCM Cloud"
    default_base_url = "https://hcm.oraclecloud.com"

    config_schema = {
        "fields": [
            {"name": "base_url", "label": "服务器地址", "required": False, "type": "url"},
            {"name": "client_id", "label": "Client ID", "required": True, "type": "text"},
            {"name": "client_secret", "label": "Client Secret", "required": True, "type": "password"},
            {"name": "username", "label": "用户名", "required": False, "type": "text"},
            {"name": "password", "label": "密码", "required": False, "type": "password"},
        ],
    }

    async def authenticate(self, config: Dict[str, Any]) -> bool:
        client = await self._get_client()
        try:
            r = await client.post(
                "/hcmRestApi/resources/latest/security/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": config.get("client_id"),
                    "client_secret": config.get("client_secret"),
                },
            )
            if r.status_code != 200:
                raise HRISAuthError(f"oracle auth failed: {r.status_code} {r.text[:200]}")
            data = r.json()
            self._access_token = data.get("access_token")
            if not self._access_token:
                raise HRISAuthError("oracle auth: missing access_token in response")
            client.headers["Authorization"] = f"Bearer {self._access_token}"
            logger.info("oracle auth ok client=%s", config.get("client_id"))
            return True
        except HRISAuthError:
            raise
        except Exception as e:  # noqa: BLE001
            raise HRISAuthError(f"oracle auth error: {e}") from e

    async def sync_employees(self, since: Optional[str] = None) -> List[Dict[str, Any]]:
        client = await self._get_client()
        params: Dict[str, Any] = {
            "limit": 100,
            "offset": 0,
            "fields": "WorkerId,DisplayName,Email,Department,JobTitle,Status",
        }
        if since:
            params["lastModifiedDate"] = since
        r = await client.get("/hcmRestApi/resources/latest/workers", params=params)
        if r.status_code != 200:
            raise HRISError(f"sync_employees failed: {r.status_code} {r.text[:200]}")
        items = r.json().get("items", [])
        return [
            {
                "external_id": str(w.get("WorkerId") or w.get("Id")),
                "name": w.get("DisplayName") or w.get("WorkerName"),
                "phone": w.get("MobilePhone") or w.get("PhoneNumber"),
                "email": w.get("Email") or w.get("WorkEmail"),
                "department": w.get("Department") or w.get("DepartmentName"),
                "title": w.get("JobTitle"),
                "status": "active" if w.get("Status") in (None, "ACTIVE", "Active") else "inactive",
                "raw": w,
            }
            for w in items
        ]

    async def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        client = await self._get_client()
        r = await client.get(f"/hcmRestApi/resources/latest/workers/{employee_id}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise HRISError(f"get_employee failed: {r.status_code} {r.text[:200]}")
        w = r.json().get("items", [{}])[0]
        return {
            "external_id": str(w.get("WorkerId") or w.get("Id")),
            "name": w.get("DisplayName") or w.get("WorkerName"),
            "phone": w.get("MobilePhone") or w.get("PhoneNumber"),
            "email": w.get("Email") or w.get("WorkEmail"),
            "department": w.get("Department") or w.get("DepartmentName"),
            "title": w.get("JobTitle"),
            "status": "active" if w.get("Status") in (None, "ACTIVE", "Active") else "inactive",
            "raw": w,
        }

    async def push_training_record(self, record: Dict[str, Any]) -> bool:
        client = await self._get_client()
        payload = {
            "WorkerId": record.get("employee_external_id"),
            "CourseName": record.get("course_name"),
            "CompletedOn": record.get("completed_on"),
            "Score": record.get("score"),
        }
        r = await client.post("/hcmRestApi/resources/latest/trainingRecords", json=payload)
        if r.status_code not in (200, 201, 204):
            raise HRISError(f"push_training_record failed: {r.status_code} {r.text[:200]}")
        return True

    async def push_assessment_result(self, result: Dict[str, Any]) -> bool:
        client = await self._get_client()
        payload = {
            "WorkerId": result.get("employee_external_id"),
            "ReviewTitle": result.get("title"),
            "Score": result.get("score"),
            "AssessedOn": result.get("assessed_on"),
        }
        r = await client.post("/hcmRestApi/resources/latest/performanceReviews", json=payload)
        if r.status_code not in (200, 201, 204):
            raise HRISError(f"push_assessment_result failed: {r.status_code} {r.text[:200]}")
        return True


__all__ = ["OracleHCMAdapter"]
