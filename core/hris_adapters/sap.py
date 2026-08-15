"""SAP SuccessFactors HRIS 适配器（DDW AI Hub v5.4 — 模块 C1）。

API 风格：SAP SuccessFactors OData V2 API（Basic Auth + API Key）。
- 鉴权：Basic Auth（username/password）+ API Key header
- 员工：``GET /odata/v2/User``
- 培训记录：``POST /odata/v2/CourseCompletion``
- 考核：``POST /odata/v2/FormTemplate``（简化）

参考：SAP SuccessFactors OData API 文档（2026-07 恢复重写版）。
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional

from core.hris_adapters.base import BaseHRISAdapter, HRISAuthError, HRISError

logger = logging.getLogger(__name__)


class SAPSFAdapter(BaseHRISAdapter):
    name = "sap"
    display_name = "SAP SuccessFactors"
    default_base_url = "https://api.successfactors.eu"

    config_schema = {
        "fields": [
            {"name": "base_url", "label": "服务器地址", "required": False, "type": "url"},
            {"name": "company_id", "label": "Company ID", "required": True, "type": "text"},
            {"name": "username", "label": "用户名", "required": True, "type": "text"},
            {"name": "password", "label": "密码", "required": True, "type": "password"},
            {"name": "api_key", "label": "API Key", "required": False, "type": "password"},
        ],
    }

    async def authenticate(self, config: Dict[str, Any]) -> bool:
        client = await self._get_client()
        try:
            auth = base64.b64encode(
                f"{config.get('username', '')}:{config.get('password', '')}".encode()
            ).decode()
            client.headers["Authorization"] = f"Basic {auth}"
            if config.get("api_key"):
                client.headers["APIKey"] = str(config["api_key"])
            # 探活：拉 1 条用户记录验证凭据
            r = await client.get("/odata/v2/User", params={"$top": 1})
            if r.status_code in (401, 403):
                raise HRISAuthError(f"sap auth failed: {r.status_code} {r.text[:200]}")
            if r.status_code != 200:
                raise HRISError(f"sap probe failed: {r.status_code} {r.text[:200]}")
            logger.info("sap auth ok company=%s", config.get("company_id"))
            return True
        except HRISAuthError:
            raise
        except Exception as e:  # noqa: BLE001
            raise HRISAuthError(f"sap auth error: {e}") from e

    async def sync_employees(self, since: Optional[str] = None) -> List[Dict[str, Any]]:
        client = await self._get_client()
        params: Dict[str, Any] = {
            "$select": "userId,username,email,displayName,department,title,status",
            "$top": 200,
        }
        if since:
            params["$filter"] = f"lastModifiedDateTime ge datetime'{since}'"
        r = await client.get("/odata/v2/User", params=params)
        if r.status_code != 200:
            raise HRISError(f"sync_employees failed: {r.status_code} {r.text[:200]}")
        users = r.json().get("d", {}).get("results", [])
        return [
            {
                "external_id": str(u.get("userId") or u.get("username")),
                "name": u.get("displayName") or u.get("username"),
                "phone": u.get("phoneNumber") or u.get("mobile"),
                "email": u.get("email"),
                "department": u.get("department"),
                "title": u.get("title"),
                "status": "active" if u.get("status") in (None, "Active", "active") else "inactive",
                "raw": u,
            }
            for u in users
        ]

    async def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        client = await self._get_client()
        r = await client.get(f"/odata/v2/User('{employee_id}')")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise HRISError(f"get_employee failed: {r.status_code} {r.text[:200]}")
        u = r.json().get("d", {})
        return {
            "external_id": str(u.get("userId") or u.get("username")),
            "name": u.get("displayName") or u.get("username"),
            "phone": u.get("phoneNumber") or u.get("mobile"),
            "email": u.get("email"),
            "department": u.get("department"),
            "title": u.get("title"),
            "status": "active" if u.get("status") in (None, "Active", "active") else "inactive",
            "raw": u,
        }

    async def push_training_record(self, record: Dict[str, Any]) -> bool:
        client = await self._get_client()
        payload = {
            "userId": record.get("employee_external_id"),
            "courseName": record.get("course_name"),
            "completedOn": record.get("completed_on"),
            "score": record.get("score"),
        }
        r = await client.post("/odata/v2/CourseCompletion", json=payload)
        if r.status_code not in (200, 201, 204):
            raise HRISError(f"push_training_record failed: {r.status_code} {r.text[:200]}")
        return True

    async def push_assessment_result(self, result: Dict[str, Any]) -> bool:
        client = await self._get_client()
        payload = {
            "userId": result.get("employee_external_id"),
            "formTitle": result.get("title"),
            "score": result.get("score"),
            "assessedOn": result.get("assessed_on"),
        }
        r = await client.post("/odata/v2/FormTemplate", json=payload)
        if r.status_code not in (200, 201, 204):
            raise HRISError(f"push_assessment_result failed: {r.status_code} {r.text[:200]}")
        return True


__all__ = ["SAPSFAdapter"]
