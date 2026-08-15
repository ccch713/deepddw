"""钉钉通讯录 + 智能人事适配器（DDW AI Hub v5.4 — 模块 C1）。

API 风格：钉钉 OpenAPI。
- 鉴权：``POST /gettoken`` → access_token（旧）或 OAuth2（新）
- 员工：``POST /topapi/user/list`` 或 ``/topapi/v2/user/list``
- 培训记录：写入审批 / 工作日志 / 智能人事
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.hris_adapters.base import BaseHRISAdapter, HRISAuthError, HRISError

logger = logging.getLogger(__name__)


class DingTalkAdapter(BaseHRISAdapter):
    name = "dingtalk"
    display_name = "钉钉智能人事"
    default_base_url = "https://oapi.dingtalk.com"

    config_schema = {
        "fields": [
            {"name": "app_key", "label": "AppKey", "required": True, "type": "text"},
            {"name": "app_secret", "label": "AppSecret", "required": True, "type": "password"},
            {"name": "agent_id", "label": "AgentId（可选）", "required": False, "type": "text"},
        ],
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None, tenant_id: Optional[int] = None) -> None:
        super().__init__(config, tenant_id)
        self._token_expires_at: float = 0.0

    async def authenticate(self, config: Dict[str, Any]) -> bool:
        client = await self._get_client()
        try:
            r = await client.post(
                "/gettoken",
                params={"appkey": config.get("app_key"), "appsecret": config.get("app_secret")},
            )
            data = r.json()
            if data.get("errcode", 0) != 0:
                raise HRISAuthError(f"dingtalk gettoken failed: {data}")
            self._access_token = data.get("access_token")
            # 钉钉 token 2 小时过期，提前 60s 续
            self._token_expires_at = time.time() + 7000
            client.params["access_token"] = self._access_token
            logger.info("dingtalk auth ok app=%s", config.get("app_key"))
            return True
        except HRISAuthError:
            raise
        except Exception as e:  # noqa: BLE001
            raise HRISAuthError(f"dingtalk auth error: {e}") from e

    async def _ensure_token(self):
        client = await self._get_client()
        if not self._access_token or time.time() >= self._token_expires_at:
            await self.authenticate(self.config)
        return client

    async def sync_employees(self, since: Optional[str] = None) -> List[Dict[str, Any]]:
        client = await self._ensure_token()
        body: Dict[str, Any] = {"dept_id": 1, "cursor": 0, "size": 100}
        if since:
            body["modified_start"] = since
        r = await client.post("/topapi/v2/user/list", json=body)
        if r.status_code != 200:
            raise HRISError(f"sync_employees failed: {r.status_code}")
        data = r.json()
        if data.get("errcode", 0) != 0:
            raise HRISError(f"sync_employees api error: {data}")
        users = (data.get("result") or {}).get("list", [])
        return [
            {
                "external_id": str(u.get("userid")),
                "name": u.get("name"),
                "phone": None,  # 列表接口不含手机号
                "email": None,
                "department": str(u.get("dept_id_list", [""])[0]) if u.get("dept_id_list") else "",
                "title": u.get("title"),
                "status": "active" if u.get("active", True) else "inactive",
                "raw": u,
            }
            for u in users
        ]

    async def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        client = await self._ensure_token()
        r = await client.post("/topapi/v2/user/get", json={"userid": employee_id, "language": "zh_CN"})
        data = r.json()
        if data.get("errcode") in (33013,):
            return None
        if data.get("errcode", 0) != 0:
            raise HRISError(f"get_employee api error: {data}")
        u = data.get("result") or {}
        return {
            "external_id": str(u.get("userid")),
            "name": u.get("name"),
            "phone": u.get("mobile"),
            "email": u.get("email"),
            "department": str(u.get("dept_id_list", [""])[0]) if u.get("dept_id_list") else "",
            "title": u.get("title"),
            "status": "active" if u.get("active", True) else "inactive",
            "raw": u,
        }

    async def push_training_record(self, record: Dict[str, Any]) -> bool:
        client = await self._ensure_token()
        # 通过工作通知发送
        body = {
            "agent_id": self.config.get("agent_id"),
            "userid_list": str(record.get("user_id", "")),
            "msg": {
                "msgtype": "markdown",
                "markdown": {
                    "title": "培训完成",
                    "text": f"### 培训完成\n- 课程: {record.get('course_id')}\n- 时长: {(record.get('duration') or 0) // 60} 分钟\n- 得分: {record.get('score', '-')}\n- 时间: {record.get('completed_at', '-')}",
                },
            },
        }
        r = await client.post("/topapi/message/corpconversation/asyncsend_v2", json=body)
        data = r.json()
        if data.get("errcode", 0) != 0:
            raise HRISError(f"push_training_record failed: {data}")
        return True

    async def push_assessment_result(self, result: Dict[str, Any]) -> bool:
        return await self.push_training_record({
            "user_id": result.get("user_id"),
            "course_id": f"评估-{result.get('assessment_id')}",
            "duration": 0,
            "score": f"{result.get('score')} ({result.get('grade')})",
            "completed_at": None,
        })


__all__ = ["DingTalkAdapter"]
