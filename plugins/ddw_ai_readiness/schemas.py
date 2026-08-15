"""ddw_ai_readiness Pydantic 模型。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DataCat(BaseModel):
    """单个数据类别的三个回答（0-2 分）。"""
    a: Optional[int] = Field(None, ge=0, le=2)  # 有数据
    b: Optional[int] = Field(None, ge=0, le=2)  # 耗人工
    c: Optional[int] = Field(None, ge=0, le=2)  # 丢不起


class SubmissionIn(BaseModel):
    """测评提交请求。company/name/phone 选填（匿名也可提交）。"""
    company: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    q1: Optional[int] = Field(None, ge=0, le=3)
    q2: Optional[int] = Field(None, ge=0, le=3)
    q3: Optional[int] = Field(None, ge=0, le=2)
    q4: Optional[int] = Field(None, ge=0, le=3)
    q5: Optional[int] = Field(None, ge=0, le=3)
    q6: list[str] = Field(default_factory=list)
    q7: Optional[int] = Field(None, ge=0, le=3)
    d: dict[str, DataCat] = Field(default_factory=dict)
    scenes: list[str] = Field(default_factory=list)


class SubmissionOut(BaseModel):
    """提交响应：id + 服务端评分结果。"""
    id: int
    score1: int
    grade1: str        # A / B / C（就绪度）
    veto: bool         # 一票否决是否触发
    score2: int
    grade_points: int  # 3-9 商机总分
    grade: str         # A级 / B级 / C级（商机分级）
    created_at: str


class SubmissionDetail(SubmissionOut):
    """详情：含全部原始答案。"""
    company: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    q1: Optional[int] = None
    q2: Optional[int] = None
    q3: Optional[int] = None
    q4: Optional[int] = None
    q5: Optional[int] = None
    q6: list[str] = []
    q7: Optional[int] = None
    d: dict = {}
    scenes: list[str] = []


class StatsOut(BaseModel):
    total: int
    grade_a: int
    grade_b: int
    grade_c: int
    grade1_a: int
    grade1_b: int
    grade1_c: int
