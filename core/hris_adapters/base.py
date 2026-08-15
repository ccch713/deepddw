"""HRIS 适配器基类（DDW AI Hub v5.4 — 模块 C1）。

对接企业人事系统（HRIS）的标准接口。每个实现负责：
- 鉴权 / Token 缓存
- 员工数据同步
- 培训记录与考核结果回写
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class HRISError(Exception):
    """HRIS 业务异常。"""


class HRISAuthError(HRISError):
    """鉴权失败。"""


class BaseHRISAdapter(ABC):
    """所有 HRIS 适配器继承此类。"""

    #: 子类需定义的元信息
    name: str = "base"
    display_name: str = "Base HRIS"
    default_base_url: str = ""
    config_schema: Dict[str, Any] = {
        "fields": [],  # 子类覆盖
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None, tenant_id: Optional[int] = None) -> None:
        self.config: Dict[str, Any] = dict(config or {})
        self.tenant_id = tenant_id
        self._client: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = None

    # ------------------------------------------------------------------ #
    # 子类必须实现
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def authenticate(self, config: Dict[str, Any]) -> bool: ...

    @abstractmethod
    async def sync_employees(self, since: Optional[str] = None) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def push_training_record(self, record: Dict[str, Any]) -> bool: ...

    @abstractmethod
    async def push_assessment_result(self, result: Dict[str, Any]) -> bool: ...

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.get("base_url", self.default_base_url) or self.default_base_url,
                timeout=self.config.get("timeout", 30),
                headers={"User-Agent": "DDW-AI-Hub/5.4"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def is_configured(self) -> bool:
        """检查必填配置是否已填。"""
        for f in self.config_schema.get("fields", []):
            if f.get("required", False) and not self.config.get(f["name"]):
                return False
        return True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} tenant={self.tenant_id} configured={self.is_configured()}>"


__all__ = ["BaseHRISAdapter", "HRISAuthError", "HRISError"]
