"""企业微信通讯录适配器（DDW AI Hub v5.4 — 模块 C1）。

API 风格：企业微信 OpenAPI。
- 鉴权：``GET /cgi-bin/gettoken`` → access_token
- 员工：``GET /cgi-bin/user/list`` (递归部门)、``GET /cgi-bin/user/get``
- 培训记录：通过应用消息推送到员工（或写入「汇报」/「日程」）
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.hris_adapters.base import BaseHRISAdapter, HRISAuthError, HRISError

logger = logging.getLogger(__name__)


class WeComAdapter(BaseHRISAdapter):
    name = "wecom"
    display_name = "企业微信通讯录"
    default_base_url = "https://qyapi.weixin.qq.com"

    config_schema = {
        "fields": [
            {"name": "corp_id", "label": "CorpID", "required": True, "type": "text"},
            {"name": "agent_id", "label": "AgentID", "required": True, "type": "text"},
            {"name": "secret", "label": "应用 Secret", "required": True, "type": "password"},
        ],
    }

    async def authenticate(self, config: Dict[str, Any]) -> bool:
        client = await self._get_client()
        try:
            r = await client.get(
                "/cgi-bin/gettoken",
                params={"corpid": config.get("corp_id"), "corpsecret": config.get("secret")},
            )
            data = r.json()
            if data.get("errcode", 0) != 0:
                raise HRISAuthError(f"wecom gettoken failed: {data}")
            self._access_token = data.get("access_token")
            client.params = {"access_token": self._access_token}
            logger.info("wecom auth ok corp=%s", config.get("corp_id"))
            return True
        except HRISAuthError:
            raise
        except Exception as e:  # noqa: BLE001
            raise HRISAuthError(f"wecom auth error: {e}") from e

    async def sync_employees(self, since: Optional[str] = None) -> List[Dict[str, Any]]:
        client = await self._get_client()
        # 简化：仅获取根部门用户；生产应递归 department/list
        r = await client.get("/cgi-bin/user/simplelist", params={"department_id": 1, "fetch_child": 1})
        if r.status_code != 200:
            raise HRISError(f"sync_employees failed: {r.status_code}")
        data = r.json()
        if data.get("errcode", 0) != 0:
            raise HRISError(f"sync_employees api error: {data}")
        users = data.get("userlist", [])
        return [
            {
                "external_id": str(u.get("userid")),
                "name": u.get("name"),
                "phone": None,  # 通讯录简化列表不含手机号
                "email": None,
                "department": ",".join(str(d) for d in u.get("department", [])),
                "title": u.get("position"),
                "status": "active" if u.get("status", 1) == 1 else "inactive",
                "raw": u,
            }
            for u in users
        ]

    async def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        client = await self._get_client()
        r = await client.get("/cgi-bin/user/get", params={"userid": employee_id})
        data = r.json()
        if data.get("errcode") == 60011:
            return None
        if data.get("errcode", 0) != 0:
            raise HRISError(f"get_employee api error: {data}")
        u = data
        return {
            "external_id": str(u.get("userid")),
            "name": u.get("name"),
            "phone": u.get("mobile"),
            "email": u.get("email"),
            "department": ",".join(str(d) for d in u.get("department", [])),
            "title": u.get("position"),
            "status": "active" if u.get("status", 1) == 1 else "inactive",
            "raw": u,
        }

    async def push_training_record(self, record: Dict[str, Any]) -> bool:
        client = await self._get_client()
        body = {
            "touser": str(record.get("user_id")),
            "msgtype": "textcard",
            "agentid": self.config.get("agent_id"),
            "textcard": {
                "title": "培训完成",
                "description": f"课程 {record.get('course_id')} 已完成，得分 {record.get('score', '-')}",
                "url": "https://example.com/training",
                "btntxt": "查看详情",
            },
        }
        r = await client.post("/cgi-bin/message/send", json=body)
        data = r.json()
        if data.get("errcode", 0) != 0:
            raise HRISError(f"push_training_record failed: {data}")
        return True

    async def push_assessment_result(self, result: Dict[str, Any]) -> bool:
        return await self.push_training_record({
            "user_id": result.get("user_id"),
            "course_id": f"评估-{result.get('assessment_id')}",
            "score": f"{result.get('score')} ({result.get('grade')})",
        })


__all__ = ["WeComAdapter"]
