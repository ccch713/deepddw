"""碳硅协同 API 路由（ddw_flow_designer）。

端点（prefix=/api/v1/flows）：
- GET  /flows                    流程列表（status/scope 过滤）
- POST /flows                    创建草稿
- GET  /flows/stats              公司级看板（只读统计）
- GET  /flows/pending-reviews    待审核列表
- GET  /flows/{id}               详情
- PUT  /flows/{id}               修改草稿
- DELETE /flows/{id}             删除（仅 owner + 停用≥12个月）
- POST /flows/{id}/publish       发布（版本自动递增；跨部门→pending_review）
- GET  /flows/{id}/versions      版本历史
- PUT  /flows/{id}/enable        启用
- PUT  /flows/{id}/disable       停用
- POST /flows/{id}/reviews/{review_id}  审核（approve/reject）
- POST /flows/{id}/run           执行（串行 LLM）
- GET  /flows/{id}/runs          执行历史

权限（SPEC §8 简化版）：
- 所有已登录用户：创建/编辑自己的草稿、发布、执行
- owner/公司管理员：审核、启用停用、删除（停用≥12月）、看板
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.auth.jwt import current_user
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .models import FlowDefinition, FlowReview, FlowRun, FlowVersion

logger = logging.getLogger(__name__)



# ------------------------------------------------------------------ #
# Schemas（模块级——闭包内定义 + from __future__ annotations 会让
# FastAPI 注解解析失败，body 被误判为 query）
# ------------------------------------------------------------------ #


class FlowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    department_id: Optional[int] = None
    scope: str = "department"          # department / cross_department
    dag_json: Dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})


class FlowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    dag_json: Optional[Dict[str, Any]] = None
    scope: Optional[str] = None


class FlowPatch(BaseModel):
    """PATCH 更新流程（支持 input_spec/output_spec/cross_dept_review_config）。"""
    name: Optional[str] = None
    description: Optional[str] = None
    input_spec: Optional[Dict[str, Any]] = None
    output_spec: Optional[Dict[str, Any]] = None
    cross_dept_review_config: Optional[Dict[str, Any]] = None
    dag_json: Optional[str] = None
    is_enabled: Optional[bool] = None


class PublishReq(BaseModel):
    changelog: str = ""
    department_ids: Optional[List[int]] = None   # 跨部门审核：需审核的部门列表（缺省=[0]=公司级单审）


class ReviewReq(BaseModel):
    action: str = Field(..., description="approve / reject")
    comment: str = ""


class RunReq(BaseModel):
    inputs: Dict[str, str] = Field(default_factory=dict)   # {start_node_id: 输入文本}


class DeptReviewReq(BaseModel):
    """部门审核结果请求（含 checklist）。"""
    action: str = Field(..., description="approve / reject")
    checklist_results: List[Dict[str, Any]] = Field(default_factory=list)
    comment: str = ""


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/flows", tags=["ddw-flow-designer"])

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    async def _get_flow(session, flow_id: int) -> FlowDefinition:
        row = (await session.execute(select(FlowDefinition).where(FlowDefinition.id == flow_id))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="流程不存在")
        return row

    def _next_version(current: str, major: bool = False) -> str:
        if not current or current == "0.0.0":
            return "2.0.0" if major else "1.0.0"
        try:
            parts = [int(x) for x in current.split(".")]
        except Exception:
            parts = [1, 0, 0]
        while len(parts) < 3:
            parts.append(0)
        if major:
            return f"{parts[0] + 1}.0.0"
        return f"{parts[0]}.{parts[1] + 1}.0"

    def _dag_to_flow(f: FlowDefinition) -> Dict[str, Any]:
        try:
            dag = json.loads(f.dag_json) if isinstance(f.dag_json, str) else (f.dag_json or {})
        except Exception:
            dag = {"nodes": [], "edges": []}
        return {
            "id": f.id,
            "name": f.name,
            "description": f.description,
            "department_id": f.department_id,
            "scope": f.scope,
            "status": f.status,
            "version": f.version,
            "is_enabled": bool(f.is_enabled),
            "total_runs": f.total_runs or 0,
            "monthly_runs": f.monthly_runs or 0,
            "avg_duration_ms": f.avg_duration_ms or 0,
            "last_run_at": f.last_run_at.isoformat() if f.last_run_at else None,
            "dag": dag,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        }

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    @router.get("")
    async def list_flows(
        status: Optional[str] = None,
        scope: Optional[str] = None,
        claims: dict = Depends(current_user),
    ) -> List[Dict[str, Any]]:
        tenant_id = claims.get("tenant_id")
        async with session_scope() as session, bypass_tenant_filter():
            stmt = select(FlowDefinition).where(FlowDefinition.tenant_id == tenant_id)
            if status:
                stmt = stmt.where(FlowDefinition.status == status)
            if scope:
                stmt = stmt.where(FlowDefinition.scope == scope)
            stmt = stmt.order_by(FlowDefinition.updated_at.desc()).limit(200)
            rows = (await session.execute(stmt)).scalars().all()
        return [_dag_to_flow(f) for f in rows]

    @router.post("")
    async def create_flow(payload: FlowCreate, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        tenant_id = claims.get("tenant_id")
        now = datetime.utcnow()
        async with session_scope() as session, bypass_tenant_filter():
            max_id = (await session.execute(select(FlowDefinition.id).order_by(FlowDefinition.id.desc()).limit(1))).scalar() or 0
            f = FlowDefinition(
                id=max_id + 1,
                tenant_id=tenant_id,
                name=payload.name,
                description=payload.description,
                department_id=payload.department_id,
                created_by=claims.get("user_id"),
                scope=payload.scope if payload.scope in ("department", "cross_department") else "department",
                status="draft",
                version="0.0.0",
                dag_json=json.dumps(payload.dag_json, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
            session.add(f)
            await session.commit()
            await session.refresh(f)
        return _dag_to_flow(f)

    @router.get("/stats")
    async def flow_stats(claims: dict = Depends(current_user)) -> Dict[str, Any]:
        tenant_id = claims.get("tenant_id")
        async with session_scope() as session, bypass_tenant_filter():
            rows = (await session.execute(
                select(FlowDefinition).where(FlowDefinition.tenant_id == tenant_id)
            )).scalars().all()
        total = len(rows)
        enabled = sum(1 for r in rows if r.is_enabled)
        published = sum(1 for r in rows if r.status == "published")
        total_runs = sum(r.total_runs or 0 for r in rows)
        month_runs = sum(r.monthly_runs or 0 for r in rows)
        items = [
            {
                "id": f.id,
                "name": f.name,
                "status": f.status,
                "version": f.version,
                "is_enabled": bool(f.is_enabled),
                "total_runs": f.total_runs or 0,
                "monthly_runs": f.monthly_runs or 0,
                "avg_duration_ms": f.avg_duration_ms or 0,
                "last_run_at": f.last_run_at.isoformat() if f.last_run_at else None,
            }
            for f in rows
        ]
        return {"total": total, "enabled": enabled, "published": published,
                "total_runs": total_runs, "monthly_runs": month_runs, "items": items}

    @router.get("/pending-reviews")
    async def pending_reviews(claims: dict = Depends(current_user)) -> List[Dict[str, Any]]:
        async with session_scope() as session, bypass_tenant_filter():
            stmt = (
                select(FlowReview, FlowDefinition)
                .join(FlowDefinition, FlowDefinition.id == FlowReview.flow_id)
                .where(FlowReview.status == "pending")
                .order_by(FlowReview.id)
            )
            rows = (await session.execute(stmt)).all()
        out = []
        for rv, fd in rows:
            out.append({
                "review_id": rv.id,
                "flow_id": fd.id,
                "flow_name": fd.name,
                "version": fd.version,
                "department_id": rv.department_id,
                "created_at": rv.created_at.isoformat() if hasattr(rv, "created_at") and rv.created_at else None,
            })
        return out

    @router.get("/{flow_id}")
    async def get_flow(flow_id: int, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            return _dag_to_flow(f)

    @router.put("/{flow_id}")
    async def update_flow(flow_id: int, payload: FlowUpdate, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            if f.status not in ("draft", "pending_review"):
                raise HTTPException(status_code=400, detail="仅草稿/待审核状态可修改，请先停用")
            if payload.name is not None:
                f.name = payload.name
            if payload.description is not None:
                f.description = payload.description
            if payload.scope is not None and payload.scope in ("department", "cross_department"):
                f.scope = payload.scope
            if payload.dag_json is not None:
                f.dag_json = json.dumps(payload.dag_json, ensure_ascii=False)
            f.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(f)
        return _dag_to_flow(f)

    @router.delete("/{flow_id}")
    async def delete_flow(flow_id: int, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            if claims.get("role") not in ("owner", "superadmin", "admin"):
                raise HTTPException(status_code=403, detail="仅公司管理员可删除流程")
            if f.is_enabled or f.status == "published":
                raise HTTPException(status_code=400, detail="仅可删除已停用流程（停用≥12个月）")
            if f.deprecated_at and datetime.utcnow() - f.deprecated_at < timedelta(days=365):
                raise HTTPException(status_code=400, detail="流程停用未满 12 个月，不可删除")
            await session.execute(FlowVersion.__table__.delete().where(FlowVersion.flow_id == flow_id))
            await session.execute(FlowReview.__table__.delete().where(FlowReview.flow_id == flow_id))
            await session.execute(FlowRun.__table__.delete().where(FlowRun.flow_id == flow_id))
            await session.execute(FlowDefinition.__table__.delete().where(FlowDefinition.id == flow_id))
            await session.commit()
        return {"deleted": True}

    # ------------------------------------------------------------------ #
    # P2: PATCH / validate / input-spec / output-spec
    # ------------------------------------------------------------------ #

    @router.patch("/{flow_id}")
    async def patch_flow(flow_id: int, payload: FlowPatch, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        """更新流程（支持 input_spec/output_spec/cross_dept_review_config）。"""
        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            if payload.name is not None:
                f.name = payload.name
            if payload.description is not None:
                f.description = payload.description
            if payload.input_spec is not None:
                f.input_spec = json.dumps(payload.input_spec, ensure_ascii=False)
            if payload.output_spec is not None:
                f.output_spec = json.dumps(payload.output_spec, ensure_ascii=False)
            if payload.cross_dept_review_config is not None:
                f.cross_dept_review_config = json.dumps(payload.cross_dept_review_config, ensure_ascii=False)
            if payload.dag_json is not None:
                f.dag_json = payload.dag_json
            if payload.is_enabled is not None:
                f.is_enabled = payload.is_enabled
            f.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(f)
        return _dag_to_flow(f)

    @router.post("/{flow_id}/validate")
    async def validate_flow(flow_id: int, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        """验证流程定义。"""
        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            errors = []
            warnings = []
            # 检查 dag_json 有效性
            try:
                dag = json.loads(f.dag_json) if isinstance(f.dag_json, str) else (f.dag_json or {})
            except Exception:
                dag = {}
                errors.append("dag_json 格式无效")
            nodes = dag.get("nodes", [])
            if not nodes:
                warnings.append("流程无节点")
            # 检查 input_spec 有效性
            if f.input_spec:
                try:
                    spec = json.loads(f.input_spec) if isinstance(f.input_spec, str) else f.input_spec
                    if not isinstance(spec, dict):
                        errors.append("input_spec 必须是 JSON 对象")
                except Exception:
                    errors.append("input_spec 格式无效")
            # 检查 output_spec 有效性
            if f.output_spec:
                try:
                    spec = json.loads(f.output_spec) if isinstance(f.output_spec, str) else f.output_spec
                    if not isinstance(spec, dict):
                        errors.append("output_spec 必须是 JSON 对象")
                except Exception:
                    errors.append("output_spec 格式无效")
        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    @router.get("/{flow_id}/input-spec")
    async def get_input_spec(flow_id: int, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        """获取输入规范。"""
        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            if not f.input_spec:
                return {"input_spec": None}
            spec = json.loads(f.input_spec) if isinstance(f.input_spec, str) else f.input_spec
            return {"input_spec": spec}

    @router.get("/{flow_id}/output-spec")
    async def get_output_spec(flow_id: int, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        """获取输出规范。"""
        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            if not f.output_spec:
                return {"output_spec": None}
            spec = json.loads(f.output_spec) if isinstance(f.output_spec, str) else f.output_spec
            return {"output_spec": spec}

    # ------------------------------------------------------------------ #
    # Publish / versions / enable / disable
    # ------------------------------------------------------------------ #

    @router.post("/{flow_id}/publish")
    async def publish_flow(flow_id: int, payload: PublishReq, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            if f.status == "published":
                raise HTTPException(status_code=400, detail="流程已发布，请先停用后修改再发布")
            # 版本递增
            new_version = _next_version(f.version)
            max_id = (await session.execute(select(FlowVersion.id).order_by(FlowVersion.id.desc()).limit(1))).scalar() or 0
            session.add(FlowVersion(
                id=max_id + 1, flow_id=flow_id, version=new_version,
                dag_json=f.dag_json, changelog=payload.changelog,
                published_by=claims.get("user_id"),
            ))
            f.version = new_version
            f.deprecated_at = None
            if f.scope == "cross_department":
                f.status = "pending_review"
                # 多部门顺序审核：每个需审核部门一条 review（v1.1：owner/superadmin/admin 均可审，
                # 部门级管理员绑定待 org 员工体系接通后细化）
                dept_ids = payload.department_ids or [0]
                for dept_id in dept_ids:
                    rmax = (await session.execute(select(FlowReview.id).order_by(FlowReview.id.desc()).limit(1))).scalar() or 0
                    session.add(FlowReview(
                        id=rmax + 1, flow_id=flow_id,
                        department_id=dept_id,
                        status="pending",
                    ))
            else:
                f.status = "published"
                f.is_enabled = True
            f.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(f)
        return _dag_to_flow(f)

    @router.get("/{flow_id}/versions")
    async def list_versions(flow_id: int, claims: dict = Depends(current_user)) -> List[Dict[str, Any]]:
        async with session_scope() as session, bypass_tenant_filter():
            rows = (await session.execute(
                select(FlowVersion).where(FlowVersion.flow_id == flow_id).order_by(FlowVersion.id.desc()).limit(50)
            )).scalars().all()
        return [
            {
                "version": v.version,
                "changelog": v.changelog,
                "published_by": v.published_by,
                "published_at": v.published_at.isoformat() if v.published_at else None,
                "dag": json.loads(v.dag_json) if isinstance(v.dag_json, str) else (v.dag_json or {}),
            }
            for v in rows
        ]

    @router.put("/{flow_id}/enable")
    async def enable_flow(flow_id: int, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            if f.status not in ("published", "pending_review"):
                raise HTTPException(status_code=400, detail="仅已发布/待审核流程可启用")
            f.is_enabled = True
            f.updated_at = datetime.utcnow()
            await session.commit()
        return {"enabled": True}

    @router.put("/{flow_id}/disable")
    async def disable_flow(flow_id: int, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            f.is_enabled = False
            f.status = "deprecated"
            f.deprecated_at = datetime.utcnow()
            f.updated_at = datetime.utcnow()
            await session.commit()
        return {"disabled": True}

    # ------------------------------------------------------------------ #
    # Reviews
    # ------------------------------------------------------------------ #

    @router.post("/{flow_id}/reviews/{review_id}")
    async def review_flow(flow_id: int, review_id: int, payload: ReviewReq, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        if payload.action not in ("approve", "reject"):
            raise HTTPException(status_code=400, detail="action 必须为 approve/reject")
        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            rv = (await session.execute(select(FlowReview).where(FlowReview.id == review_id, FlowReview.flow_id == flow_id))).scalar_one_or_none()
            if rv is None:
                raise HTTPException(status_code=404, detail="审核记录不存在")
            if rv.status != "pending":
                raise HTTPException(status_code=400, detail="该审核已处理")
            rv.status = "approved" if payload.action == "approve" else "rejected"
            rv.reviewer_id = claims.get("user_id")
            rv.comment = payload.comment
            rv.reviewed_at = datetime.utcnow()
            if payload.action == "approve":
                # 多部门顺序审核：全部部门通过才发布
                remaining = (await session.execute(
                    select(FlowReview).where(FlowReview.flow_id == flow_id, FlowReview.status == "pending")
                )).scalars().all()
                if not remaining:
                    f.status = "published"
                    f.is_enabled = True
            else:
                f.status = "draft"
            f.updated_at = datetime.utcnow()
            await session.commit()
        return {"status": rv.status}

    # ------------------------------------------------------------------ #
    # Execution（串行 LLM）
    # ------------------------------------------------------------------ #

    @router.post("/{flow_id}/run")
    async def run_flow(flow_id: int, payload: RunReq, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        from core.llm_gateway.base import ChatMessage
        from core.llm_gateway.gateway import chat as llm_chat
        from core.llm_gateway.router import RouteContext

        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            if not f.is_enabled or f.status not in ("published", "pending_review"):
                raise HTTPException(status_code=400, detail="流程未启用，无法执行")
            try:
                dag = json.loads(f.dag_json) if isinstance(f.dag_json, str) else (f.dag_json or {})
            except Exception:
                dag = {"nodes": [], "edges": []}

        nodes = dag.get("nodes", []) or []
        edges = dag.get("edges", []) or []
        if not nodes:
            raise HTTPException(status_code=400, detail="流程为空，无法执行")

        # 拓扑序：edges 的 source 必须在 target 前
        order: List[Dict[str, Any]] = []
        done: set[str] = set()
        node_map = {n.get("id"): n for n in nodes}
        for _ in range(len(nodes) + 5):
            progressed = False
            for n in nodes:
                nid = str(n.get("id"))
                if nid in done:
                    continue
                deps = [e.get("source") for e in edges if str(e.get("target")) == nid]
                if all(str(d) in done for d in deps):
                    order.append(n)
                    done.add(nid)
                    progressed = True
            if not progressed:
                break
        # 兜底：未入序的节点追加
        for n in nodes:
            if str(n.get("id")) not in done:
                order.append(n)

        user_id = claims.get("user_id")
        tenant_id = claims.get("tenant_id")
        ctx = RouteContext(user_id=user_id, tenant_id=tenant_id)
        results: Dict[str, str] = {}
        started = time.time()
        import asyncio as _asyncio

        async def run_node(n: Dict[str, Any]) -> str:
            """执行单个节点，返回输出（并写入 results 供下游消费）。"""
            nid = str(n.get("id"))
            ntype = n.get("type", "")
            data = n.get("data", {}) or {}
            if ntype == "start":
                out = payload.inputs.get(nid, "")
                results[nid] = out
                return out
            if ntype == "end":
                results[nid] = "流程结束"
                return "流程结束"
            if ntype == "merge":
                # 等待所有入边完成（并行分支汇聚），上限 120s
                for _ in range(600):
                    ins = [results[str(e.get("source"))] for e in edges
                           if str(e.get("target")) == nid and str(e.get("source")) in results]
                    need = [e for e in edges if str(e.get("target")) == nid]
                    if len(ins) >= len(need) and need:
                        break
                    await _asyncio.sleep(0.2)
                ins = [results[str(e.get("source"))] for e in edges
                       if str(e.get("target")) == nid and str(e.get("source")) in results]
                merged = "\n\n".join(f"【分支 {i + 1}】\n{v}" for i, v in enumerate(ins)) if ins else "（无输入）"
                results[nid] = merged
                return merged
            prompt = data.get("prompt") or data.get("content") or data.get("name") or n.get("label") or "请处理当前任务"
            upstream = []
            for e in edges:
                if str(e.get("target")) == nid and str(e.get("source")) in results:
                    upstream.append(results[str(e.get("source"))])
            context_in = "\n".join(upstream) if upstream else payload.inputs.get(nid, "")
            if ntype == "condition":
                # 条件判断：支持 contains:关键词 / not contains:关键词（v1.1 语义，零 LLM 成本）
                cond = data.get("condition") or ""
                if cond.startswith("contains:"):
                    kw = cond[len("contains:"):].strip()
                    verdict = kw in context_in
                elif cond.startswith("not contains:"):
                    kw = cond[len("not contains:"):].strip()
                    verdict = kw not in context_in
                else:
                    verdict = bool(context_in.strip())
                results[nid] = f"条件判断：{cond or '非空'} → {'成立' if verdict else '不成立'}"
                return "yes" if verdict else "no"
            messages = [ChatMessage(role="user", content=f"【流程节点：{data.get('name') or n.get('label') or nid}】\n{prompt}\n\n输入：{context_in or '（无）'}\n请直接给出处理结果。")]
            resp = await llm_chat(messages, ctx=ctx)
            out = resp.content or ""
            results[nid] = out
            return out

        async def exec_node(nid: str) -> None:
            """递归执行节点及下游（结果缓存防重复执行）。"""
            if nid in results:
                return
            n = node_map.get(nid)
            if n is None:
                return
            await run_node(n)   # run_node 内部写入 results[nid]
            out_edges = [e for e in edges if str(e.get("source")) == nid]
            ntype = n.get("type", "")
            if ntype == "condition":
                # 按判断结果选路：优先匹配 label=yes/no 的边，无 label 边兜底；
                # 同分支多条出边并行执行（yes 多分支场景）
                verdict = str(results.get(nid, "")).startswith("条件判断：") and ("→ 成立" in results.get(nid, ""))
                branch = "yes" if verdict else "no"
                branch_edges = [e for e in out_edges if str(e.get("label", "")).lower() == branch]
                if not branch_edges:
                    branch_edges = [e for e in out_edges if not e.get("label")]
                tasks = [_asyncio.create_task(exec_node(str(e.get("target")))) for e in branch_edges]
                if tasks:
                    await _asyncio.gather(*tasks)
            elif ntype == "parallel":
                # 并行执行所有分支
                tasks = [_asyncio.create_task(exec_node(str(e.get("target")))) for e in out_edges]
                if tasks:
                    await _asyncio.gather(*tasks)
            else:
                for e in out_edges:
                    await exec_node(str(e.get("target")))

        # 从所有入度为 0 的节点启动
        targets = {str(e.get("target")) for e in edges}
        starts = [n for n in order if str(n.get("id")) not in targets] or order[:1]
        try:
            for s in starts:
                await exec_node(str(s.get("id")))
            status = "success"
            error = ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("flow run failed: %s", exc)
            status = "failed"
            error = str(exc)
        duration_ms = int((time.time() - started) * 1000)

        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            f.total_runs = (f.total_runs or 0) + 1
            f.monthly_runs = (f.monthly_runs or 0) + 1
            f.avg_duration_ms = int(((f.avg_duration_ms or 0) + duration_ms) / 2)
            f.last_run_at = datetime.utcnow()
            rmax = (await session.execute(select(FlowRun.id).order_by(FlowRun.id.desc()).limit(1))).scalar() or 0
            session.add(FlowRun(
                id=rmax + 1, flow_id=flow_id, version=f.version, status=status,
                result=json.dumps(results, ensure_ascii=False), error=error,
                created_by=user_id, started_at=datetime.utcnow() - timedelta(milliseconds=duration_ms),
                finished_at=datetime.utcnow(),
            ))
            await session.commit()
        return {"status": status, "results": results, "duration_ms": duration_ms, "error": error or None}

    @router.get("/{flow_id}/runs")
    async def list_runs(flow_id: int, claims: dict = Depends(current_user)) -> List[Dict[str, Any]]:
        async with session_scope() as session, bypass_tenant_filter():
            rows = (await session.execute(
                select(FlowRun).where(FlowRun.flow_id == flow_id).order_by(FlowRun.id.desc()).limit(50)
            )).scalars().all()
        return [
            {
                "id": r.id,
                "version": r.version,
                "status": r.status,
                "result": json.loads(r.result) if isinstance(r.result, str) and r.result else {},
                "error": r.error,
                "created_by": r.created_by,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    # P3: Cross-department review
    # ------------------------------------------------------------------ #

    @router.post("/{flow_id}/submit-review")
    async def submit_review(flow_id: int, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        """提交跨部门审核。"""
        from .services.cross_dept_review import CrossDeptReviewService

        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            try:
                service = CrossDeptReviewService(session)
                reviews = await service.submit_review(f, claims.get("user_id"))
                await session.commit()
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        return {"status": "pending_review", "reviews": reviews}

    @router.post("/{flow_id}/dept-reviews/{dept_id}")
    async def dept_review(
        flow_id: int, dept_id: int, payload: DeptReviewReq,
        claims: dict = Depends(current_user),
    ) -> Dict[str, Any]:
        """提交部门审核结果（含 checklist）。"""
        from .services.cross_dept_review import CrossDeptReviewService

        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            try:
                service = CrossDeptReviewService(session)
                result = await service.submit_dept_review(
                    flow=f,
                    dept_id=dept_id,
                    user_id=claims.get("user_id"),
                    checklist_results=payload.checklist_results,
                    action=payload.action,
                    comment=payload.comment,
                )
                await session.commit()
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
        return result

    @router.get("/{flow_id}/review-status")
    async def review_status(flow_id: int, claims: dict = Depends(current_user)) -> Dict[str, Any]:
        """查看联审进度。"""
        from .services.cross_dept_review import CrossDeptReviewService

        async with session_scope() as session, bypass_tenant_filter():
            f = await _get_flow(session, flow_id)
            if f.tenant_id != claims.get("tenant_id"):
                raise HTTPException(status_code=403, detail="无权访问")
            service = CrossDeptReviewService(session)
            return await service.get_review_status(flow_id)

    return router
