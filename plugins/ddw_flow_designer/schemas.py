"""碳硅协同 Pydantic schemas（ddw_flow_designer）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class FlowDefinitionUpdateReq(BaseModel):
    """更新流程定义请求。"""
    name: Optional[str] = None
    description: Optional[str] = None
    input_spec: Optional[Dict[str, Any]] = None
    output_spec: Optional[Dict[str, Any]] = None
    cross_dept_review_config: Optional[Dict[str, Any]] = None
    dag_json: Optional[str] = None
    is_enabled: Optional[bool] = None


class FlowRunReq(BaseModel):
    """执行流程请求。"""
    input_data: Dict[str, Any]


class FlowValidateResp(BaseModel):
    """流程验证响应。"""
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []
