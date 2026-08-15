"""DDW 岗位设计器 API 路由（v1.0）。

API 端点（10 个）：
  POST   /positions                       新建岗位设计
  GET    /positions                       岗位列表（分页 + 筛选）
  GET    /positions/{id}                  岗位详情
  PUT    /positions/{id}                  更新岗位
  DELETE /positions/{id}                  归档岗位
  GET    /positions/{id}/export           导出 HTML 设计说明书
  POST   /positions/{id}/route-decision   5 因素决策路由（v2.0）
  GET    /positions/by-department/{dept}  按部门查询岗位（与 OPC 联动）
  GET    /agents/recommend?department=xx  按部门推荐 Agent
  GET    /config                          插件配置（决策类型枚举 + 默认 Agent + 部门列表）
  GET    /health                          健康检查
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from . import PLUGIN_NAME, VERSION
from .decision_router import (
    AGENT_RECOMMENDATIONS,
    DecisionRouter,
    recommend_agents,
    suggest_decision_type,
)
from .models import DECISION_TYPE_LABELS, STANDARD_DEPARTMENTS
from .schemas import (
    HealthResp,
    PluginConfigResp,
    PositionDesignCreateReq,
    PositionDesignListResp,
    PositionDesignUpdateReq,
)
from .services import PositionDesignService

logger = logging.getLogger(__name__)


class DecisionRoutingReq(BaseModel):
    scenario: str = Field(..., min_length=1, description="业务场景描述")
    factors: dict = Field(..., description="5 因素分值（0-1）")


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v1/plugins/{PLUGIN_NAME}",
        tags=[PLUGIN_NAME],
    )

    # -----------------------------------------------------------------------
    # Health
    # -----------------------------------------------------------------------
    @router.get("/health", response_model=HealthResp)
    async def health() -> HealthResp:
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = PositionDesignService(db)
                total = await svc.count(tenant_id=1)
                return HealthResp(
                    status="ok",
                    plugin=PLUGIN_NAME,
                    version=VERSION,
                    positions_count=total,
                )

    # -----------------------------------------------------------------------
    # Config
    # -----------------------------------------------------------------------
    @router.get("/config", response_model=PluginConfigResp)
    async def get_config() -> PluginConfigResp:
        decision_types = [
            {"value": k, "label": v}
            for k, v in DECISION_TYPE_LABELS.items()
        ]
        return PluginConfigResp(
            decision_types=decision_types,
            default_agents=[
                "数据分析 Agent", "知识库 Agent", "流程自动化 Agent",
                "CRM Agent", "客服 Agent",
            ],
            standard_departments=STANDARD_DEPARTMENTS,
            decision_routing_weights=DecisionRouter.WEIGHTS,
        )

    # -----------------------------------------------------------------------
    # Agent 推荐（无状态）
    # -----------------------------------------------------------------------
    @router.get("/agents/recommend", response_model=dict)
    async def recommend_agents_endpoint(
        department: Optional[str] = Query(None, description="部门名称"),
        limit: int = Query(5, ge=1, le=20, description="最多返回数量"),
    ) -> dict:
        agents = recommend_agents(department or "", limit=limit)
        return {
            "department": department,
            "agents": agents,
            "all_by_department": AGENT_RECOMMENDATIONS,
        }

    # -----------------------------------------------------------------------
    # 决策路由（无状态）
    # -----------------------------------------------------------------------
    @router.post("/decide", response_model=dict)
    async def decide_endpoint(body: DecisionRoutingReq = Body(...)) -> dict:
        """根据 5 因素分值返回决策类型建议。"""
        router_engine = DecisionRouter()
        result = router_engine.explain(body.factors)
        suggested = suggest_decision_type(body.scenario)
        result["scenario_keyword_suggestion"] = suggested
        return result

    # =======================================================================
    # Position CRUD
    # =======================================================================

    @router.post("/positions", response_model=dict, status_code=201)
    async def create_position(data: PositionDesignCreateReq) -> dict:
        """新建岗位设计。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = PositionDesignService(db)
                return await svc.create(data)

    @router.get("/positions", response_model=PositionDesignListResp)
    async def list_positions(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        department: Optional[str] = Query(None, description="按部门过滤"),
        status: Optional[str] = Query(None, description="按状态过滤"),
        search: Optional[str] = Query(None, description="模糊搜索（岗位名/部门/公司）"),
    ) -> PositionDesignListResp:
        """岗位列表（分页 + 筛选 + 搜索）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = PositionDesignService(db)
                items, total = await svc.list(
                    tenant_id=1, page=page, page_size=page_size,
                    department=department, search=search, status=status,
                )
                return PositionDesignListResp(
                    items=items, total=total, page=page, page_size=page_size,
                )

    @router.get("/positions/by-department/{dept}", response_model=list)
    async def list_by_department(dept: str) -> list:
        """按部门列出所有岗位（供 ddw_opc_departments 联动展示）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = PositionDesignService(db)
                return await svc.list_by_department(dept, tenant_id=1)

    @router.get("/positions/{position_id}", response_model=dict)
    async def get_position(position_id: int) -> dict:
        """岗位详情。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = PositionDesignService(db)
                result = await svc.get(position_id, tenant_id=1)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"position {position_id} not found",
                    )
                return result

    @router.put("/positions/{position_id}", response_model=dict)
    async def update_position(
        position_id: int, data: PositionDesignUpdateReq,
    ) -> dict:
        """更新岗位设计（自动 +1 版本号）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = PositionDesignService(db)
                result = await svc.update(position_id, data, tenant_id=1)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"position {position_id} not found",
                    )
                return result

    @router.delete("/positions/{position_id}", response_model=dict)
    async def archive_position(position_id: int) -> dict:
        """归档岗位（软删除）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = PositionDesignService(db)
                result = await svc.archive(position_id, tenant_id=1)
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"position {position_id} not found",
                    )
                return result

    @router.post("/positions/{position_id}/route-decision", response_model=dict)
    async def route_decision_endpoint(
        position_id: int,
        factors: dict = Body(..., description="5 因素分值"),
    ) -> dict:
        """对岗位的某个决策场景做 5 因素路由分析。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = PositionDesignService(db)
                position = await svc.get(position_id, tenant_id=1)
                if not position:
                    raise HTTPException(
                        status_code=404, detail=f"position {position_id} not found",
                    )
        engine = DecisionRouter()
        return {
            "position_id": position_id,
            "position_name": position["name"],
            "routing": engine.explain(factors),
        }

    @router.get("/positions/{position_id}/export", response_class=HTMLResponse)
    async def export_position(position_id: int) -> HTMLResponse:
        """导出岗位设计为 HTML 说明书（独立可打开 + 可打印）。"""
        async with session_scope() as db:
            async with bypass_tenant_filter():
                svc = PositionDesignService(db)
                data = await svc.get(position_id, tenant_id=1)
                if not data:
                    raise HTTPException(
                        status_code=404, detail=f"position {position_id} not found",
                    )
        html = _render_position_doc(data)
        return HTMLResponse(content=html, status_code=200)

    return router


# ===========================================================================
# HTML 岗位说明书渲染
# ===========================================================================


def _render_position_doc(p: dict) -> str:
    """渲染岗位设计为独立 HTML。"""
    name = p.get("name", "")
    dept = p.get("department") or "—"
    report_to = p.get("report_to") or "—"
    company = p.get("company") or "—"
    description = p.get("description") or ""

    outcomes = p.get("outcomes") or []
    humans = p.get("human_responsibilities") or []
    agents = p.get("agent_stack") or []
    decisions = p.get("decision_rights") or []
    human_cap = p.get("human_capability") or ""
    agent_cap = p.get("agent_capability") or ""
    handoff = p.get("handoff_protocol") or ""
    risks = p.get("risk_controls") or []

    version = p.get("version", 1)
    status = p.get("status", "draft")
    updated_at = p.get("updated_at")
    if hasattr(updated_at, "strftime"):
        updated_at = updated_at.strftime("%Y-%m-%d %H:%M")

    # 渲染 Outcome / Human / Agent
    def _ul(items):
        if not items:
            return '<li style="color:#9CA3AF">（待填写）</li>'
        return "".join(f"<li>{x}</li>" for x in items)

    # 渲染决策权限表格
    decision_rows = []
    for d in decisions:
        if not isinstance(d, dict):
            continue
        scenario = d.get("scenario", "—")
        human_right = d.get("human_right", "—")
        agent_right = d.get("agent_right", "—")
        dtype = d.get("decision_type", "suggest")
        dtype_label = DECISION_TYPE_LABELS.get(dtype, dtype)
        color = {
            "auto": "#10B981", "suggest": "#3B82F6",
            "human": "#F59E0B", "escalate": "#EF4444",
        }.get(dtype, "#6B7280")
        decision_rows.append(f"""
        <tr>
          <td style="font-weight:600">{scenario}</td>
          <td>{human_right}</td>
          <td>{agent_right}</td>
          <td><span style="background:{color}20;color:{color};padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600">{dtype_label}</span></td>
        </tr>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name} - 岗位设计说明书 | DDW AI HUB</title>
<style>
:root{{--orange:#F47B20;--orange-light:#FFF3E8;--navy:#1a2332;--navy-light:#2d3a4d;--blue:#3B82F6;--blue-light:#EFF6FF;--green:#10B981;--green-light:#ECFDF5;--purple:#8B5CF6;--purple-light:#F5F3FF;--yellow:#F59E0B;--yellow-light:#FFFBEB;--red:#EF4444;--red-light:#FEF2F2;--pink:#EC4899;--pink-light:#FCE7F3;--gray-50:#F9FAFB;--gray-100:#F3F4F6;--gray-200:#E5E7EB;--gray-400:#9CA3AF;--gray-500:#6B7280;--gray-700:#374151;--gray-800:#1F2937;--radius:12px;--shadow:0 1px 3px rgba(0,0,0,.1)}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:#F9FAFB;color:#1F2937;line-height:1.6;padding:24px}}
.container{{max-width:960px;margin:0 auto}}
.header{{background:linear-gradient(135deg,#1a2332,#2d3a4d);color:#fff;border-radius:var(--radius);padding:40px;text-align:center;margin-bottom:24px}}
.header h1{{font-size:32px;color:#F47B20;margin-bottom:8px}}
.header .meta{{color:rgba(255,255,255,.6);font-size:13px;margin-top:12px}}
.header .meta span{{margin:0 8px}}
.header .pill{{display:inline-block;background:rgba(244,123,32,.2);color:#F47B20;padding:4px 12px;border-radius:10px;font-size:12px;font-weight:600;margin-top:8px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}}
@media(max-width:768px){{.grid{{grid-template-columns:1fr}}}}
.box{{background:#fff;border-radius:var(--radius);padding:24px;box-shadow:var(--shadow)}}
.box h3{{font-size:16px;color:#1a2332;margin-bottom:12px;display:flex;align-items:center;gap:8px}}
.box.outcome{{border-top:3px solid #F47B20}}
.box.human{{border-top:3px solid #3B82F6}}
.box.agent{{border-top:3px solid #8B5CF6}}
.box.decision{{border-top:3px solid #10B981;grid-column:1/-1}}
.box.capability{{border-top:3px solid #F59E0B}}
.box.risk{{border-top:3px solid #EC4899}}
.box ul{{list-style:none;font-size:14px;padding-left:0}}
.box li{{padding:4px 0;color:#374151;position:relative;padding-left:16px}}
.box li::before{{content:'•';position:absolute;left:0;font-weight:bold}}
.box.outcome li::before{{color:#F47B20}}
.box.human li::before{{color:#3B82F6}}
.box.agent li::before{{color:#8B5CF6}}
.box.capability li::before{{color:#F59E0B}}
.box.risk li::before{{color:#EC4899}}
table{{width:100%;border-collapse:collapse;margin-top:8px}}
th{{background:#F3F4F6;padding:10px;font-size:13px;font-weight:600;text-align:left;border-bottom:2px solid #E5E7EB}}
td{{padding:10px;border-bottom:1px solid #F3F4F6;font-size:14px}}
.formula{{background:linear-gradient(135deg,#FFF3E8,#FCE7F3);border:2px dashed #F47B20;border-radius:var(--radius);padding:24px;text-align:center;margin-top:24px}}
.formula-label{{font-size:12px;color:#9CA3AF;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}}
.formula-text{{font-size:18px;font-weight:700;color:#1a2332}}
.footer{{text-align:center;padding:24px;color:#9CA3AF;font-size:12px;margin-top:24px}}
@media print{{body{{background:#fff;padding:0}}.container{{max-width:100%}}.header{{page-break-after:avoid}}.box{{page-break-inside:avoid}}}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{name}</h1>
    <div style="font-size:14px;color:rgba(255,255,255,.7)">{company} · {dept}</div>
    <div class="meta">
      <span>📊 汇报对象：{report_to}</span>
      <span>·</span>
      <span>📅 版本 v{version}</span>
      <span>·</span>
      <span>更新时间：{updated_at or '-'}</span>
    </div>
    <div class="pill">状态：{status}</div>
  </div>

  {f'<div class="box" style="margin-bottom:24px"><h3>📝 岗位描述</h3><p style="color:#4B5563">{description}</p></div>' if description else ''}

  <div class="grid">
    <div class="box outcome">
      <h3>🎯 成果（Outcome）</h3>
      <ul>{_ul(outcomes)}</ul>
    </div>
    <div class="box human">
      <h3>👤 人的责任（Human Responsibility）</h3>
      <ul>{_ul(humans)}</ul>
    </div>
    <div class="box agent">
      <h3>🤖 Agent 组合（Agent Stack）</h3>
      <ul>{_ul(agents)}</ul>
    </div>
    <div class="box decision">
      <h3>⚖️ 决策权限矩阵（Decision Rights）</h3>
      {f'<table><thead><tr><th>业务场景</th><th>人类权限</th><th>Agent 权限</th><th>决策类型</th></tr></thead><tbody>{"".join(decision_rows)}</tbody></table>' if decision_rows else '<p style="color:#9CA3AF">（待填写）</p>'}
    </div>
    <div class="box capability">
      <h3>💪 能力标准（Capability Standards）</h3>
      <ul>
        {f'<li><strong>人类能力：</strong>{human_cap}</li>' if human_cap else ''}
        {f'<li><strong>Agent 能力：</strong>{agent_cap}</li>' if agent_cap else ''}
        {f'<li><strong>交接协议：</strong>{handoff}</li>' if handoff else ''}
        {(not human_cap and not agent_cap and not handoff) and '<li style="color:#9CA3AF">（待填写）</li>' or ''}
      </ul>
    </div>
    <div class="box risk">
      <h3>🛡️ 风险管控（Risk Management）</h3>
      <ul>{_ul(risks)}</ul>
    </div>
  </div>

  <div class="formula">
    <div class="formula-label">岗位设计公式</div>
    <div class="formula-text">
      {name} = {len(outcomes)} Outcomes × {len(humans)} Human × {len(agents)} Agents × {len(decisions)} Rights × {len(risks)} Risks
    </div>
  </div>

  <div class="footer">DDW AI HUB · 人机协同岗位设计说明书 v{version} · 由 DDW Position Designer 插件自动生成</div>
</div>
</body>
</html>"""


__all__ = ["build_router"]
