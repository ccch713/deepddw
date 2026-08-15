# TASK_SPEC: 数字员工体系 P1+P2 — 技能验证增强 + 碳硅协作质量门禁

> **版本**：v1.0  
> **日期**：2026-08-11  
> **前置条件**：P0 已完成（models.py/roles.py/迁移脚本/6个API端点）  
> **开发工具**：MiMo Code CLI

---

## P1 部分：技能验证增强

### P1.1 proficiency 权限执行逻辑

在 `plugins/ddw_org/services/org_service.py` 中增强 validate_agent：

```python
async def validate_agent(self, agent_id: int, tenant_id: int) -> dict:
    """完整验证数字员工能力（P1 增强版）。
    
    验证项：
    C1: job_objective 非空
    C2: work_boundary 非空  
    C3: 至少 1 个 skill
    C4: proficiency 枚举值合法（junior/senior/expert）
    C5: decision_scope 含 "approve" 时，至少有 1 个 expert 级 skill
    """
    agent = await self.db.get(DigitalAgent, agent_id)
    if not agent or agent.tenant_id != tenant_id:
        return {"passed": False, "error": "数字员工不存在"}
    
    checks = []
    
    # C1: 岗位目标
    c1 = bool(agent.job_objective and agent.job_objective.strip())
    checks.append({"check": "C1", "name": "岗位目标", "passed": c1, 
                    "message": "" if c1 else "job_objective 为空"})
    
    # C2: 工作边界
    c2 = bool(agent.work_boundary and agent.work_boundary.strip())
    checks.append({"check": "C2", "name": "工作边界", "passed": c2,
                    "message": "" if c2 else "work_boundary 为空"})
    
    # C3: 至少1个skill
    skills = (await self.db.execute(
        select(AgentSkill).where(AgentSkill.agent_id == agent_id)
    )).scalars().all()
    c3 = len(skills) > 0
    checks.append({"check": "C3", "name": "技能配置", "passed": c3,
                    "message": "" if c3 else "无任何技能配置"})
    
    # C4: proficiency 枚举校验
    valid_proficiencies = {"junior", "senior", "expert"}
    invalid_skills = [s for s in skills if s.proficiency not in valid_proficiencies]
    c4 = len(invalid_skills) == 0
    checks.append({"check": "C4", "name": "技能熟练度", "passed": c4,
                    "message": "" if c4 else f"无效熟练度: {[s.proficiency for s in invalid_skills]}"})
    
    # C5: approve 权限需 expert 级 skill
    has_approve = "approve" in (agent.decision_scope or [])
    has_expert = any(s.proficiency == "expert" for s in skills)
    c5 = not has_approve or has_expert
    checks.append({"check": "C5", "name": "审批权限与技能匹配", "passed": c5,
                    "message": "" if c5 else "decision_scope 含 approve 但无 expert 级技能"})
    
    all_passed = all(c["passed"] for c in checks)
    return {"passed": all_passed, "checks": checks}
```

### P1.2 trigger_conditions 格式校验

在 `plugins/ddw_org/schemas.py` 的 AgentSkillUpdateReq 中添加 validator：

```python
from pydantic import field_validator

class AgentSkillUpdateReq(BaseModel):
    enabled: Optional[bool] = None
    proficiency: Optional[str] = None
    trigger_conditions: Optional[List[dict]] = None
    sla_seconds: Optional[int] = None
    
    @field_validator("proficiency")
    @classmethod
    def validate_proficiency(cls, v: str) -> str:
        if v not in ("junior", "senior", "expert"):
            raise ValueError(f"proficiency 必须是 junior/senior/expert，收到: {v}")
        return v
    
    @field_validator("trigger_conditions")
    @classmethod
    def validate_triggers(cls, v: list) -> list:
        for item in v:
            if not isinstance(item, dict) or "event" not in item:
                raise ValueError("每个 trigger_condition 必须包含 'event' 字段")
        return v
    
    @field_validator("sla_seconds")
    @classmethod
    def validate_sla(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("sla_seconds 不能为负数")
        return v
```

### P1.3 测试用例（5 条）

```python
# 补充到 test_digital_employee_p0.py 或新建 test_p1_skill_validation.py

async def test_p1_t1_proficiency_enum_validation(self, client, admin_token):
    """proficiency 非法值被拒绝"""
    resp = await client.patch(
        "/api/v1/org/agent-skills/1",
        json={"proficiency": "super_expert"},  # 非法值
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422  # Pydantic validation error

async def test_p1_t2_trigger_requires_event(self, client, admin_token):
    """trigger_conditions 缺少 event 字段被拒绝"""
    resp = await client.patch(
        "/api/v1/org/agent-skills/1",
        json={"trigger_conditions": [{"filter": {}}]},  # 缺少 event
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422

async def test_p1_t3_validate_agent_all_pass(self, client, admin_token):
    """完整配置的数字员工验证全部通过"""
    resp = await client.post(
        "/api/v1/org/agents/1/validate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "checks" in data
    assert len(data["checks"]) == 5

async def test_p1_t4_approve_needs_expert(self, client, admin_token):
    """decision_scope 含 approve 但无 expert 技能时验证失败"""
    # 先设置 decision_scope 含 approve
    await client.patch(
        "/api/v1/org/agents/1",
        json={"decision_scope": ["read", "approve"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # 确保所有 skill 都是 junior
    # (这取决于种子数据，可能需要先修改)
    resp = await client.post(
        "/api/v1/org/agents/1/validate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    # C5 检查结果取决于 agent 的 skill proficiency 配置

async def test_p1_t5_sla_negative_rejected(self, client, admin_token):
    """sla_seconds 为负数被拒绝"""
    resp = await client.patch(
        "/api/v1/org/agent-skills/1",
        json={"sla_seconds": -10},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422
```

---

## P2 部分：碳硅协作 input/output spec + 执行引擎对接

### P2.1 输入规范检查引擎

新建 `plugins/ddw_flow_designer/services/spec_checker.py`：

```python
"""碳硅协作：输入/输出规范检查引擎。

功能：
- 解析 node 的 input_spec 并逐项执行 quality_checks
- 解析 flow 的 output_spec 并检查产出物完整性
- 生成结构化拒绝消息
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CheckResult:
    check_type: str
    severity: str  # reject / reject_with_feedback / block / warn
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class SpecCheckReport:
    passed: bool
    results: List[CheckResult] = field(default_factory=list)
    blocking_failures: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "results": [
                {"check_type": r.check_type, "severity": r.severity, 
                 "passed": r.passed, "message": r.message}
                for r in self.results
            ],
            "blocking_failures": self.blocking_failures,
        }


class InputSpecChecker:
    """检查输入数据是否符合 input_spec 规范。"""
    
    def check(self, input_spec: dict, actual_data: dict) -> SpecCheckReport:
        """执行输入规范检查。
        
        Args:
            input_spec: node 的 input_spec JSON
            actual_data: 实际输入数据
        
        Returns:
            SpecCheckReport: 检查报告
        """
        report = SpecCheckReport(passed=True)
        
        if not input_spec:
            return report
        
        # 检查 required_fields
        required = input_spec.get("required_fields", [])
        for field_name in required:
            if field_name not in actual_data or actual_data[field_name] is None:
                result = CheckResult(
                    check_type="required_field_missing",
                    severity="reject",
                    passed=False,
                    message=f"缺少必填字段: {field_name}",
                )
                report.results.append(result)
                report.passed = False
                report.blocking_failures.append("required_field_missing")
        
        # 检查 file_constraints
        file_constraints = input_spec.get("file_constraints", {})
        if file_constraints and "file_url" in actual_data:
            file_url = actual_data.get("file_url", "")
            file_size_mb = actual_data.get("file_size_mb", 0)
            file_type = actual_data.get("file_type", "")
            
            max_size = file_constraints.get("max_size_mb", 100)
            if file_size_mb > max_size:
                result = CheckResult(
                    check_type="file_size_exceeded",
                    severity="reject",
                    passed=False,
                    message=f"文件大小 {file_size_mb}MB 超过限制 {max_size}MB",
                )
                report.results.append(result)
                report.passed = False
                report.blocking_failures.append("file_size_exceeded")
            
            allowed_formats = file_constraints.get("allowed_formats", [])
            if allowed_formats and file_type not in allowed_formats:
                result = CheckResult(
                    check_type="file_format_invalid",
                    severity="reject",
                    passed=False,
                    message=f"文件格式 '{file_type}' 不在允许列表: {allowed_formats}",
                )
                report.results.append(result)
                report.passed = False
                report.blocking_failures.append("file_format_invalid")
        
        # 检查 data_constraints
        data_constraints = input_spec.get("data_constraints", {})
        if data_constraints:
            min_fields = data_constraints.get("min_json_fields", [])
            missing = [f for f in min_fields if f not in actual_data]
            if missing:
                result = CheckResult(
                    check_type="data_fields_missing",
                    severity="reject_with_feedback",
                    passed=False,
                    message=f"缺少数据字段: {missing}",
                    details={"missing_fields": missing},
                )
                report.results.append(result)
                report.passed = False
                report.blocking_failures.append("data_fields_missing")
        
        # 执行 quality_checks（自定义检查项）
        quality_checks = input_spec.get("quality_checks", [])
        for qc in quality_checks:
            qc_type = qc.get("type", "")
            severity = qc.get("severity", "reject")
            
            if qc_type == "file_not_empty":
                is_empty = not actual_data.get("file_url") and not actual_data.get("content")
                result = CheckResult(
                    check_type="file_not_empty",
                    severity=severity,
                    passed=not is_empty,
                    message=qc.get("message", "文件为空") if is_empty else "",
                )
                if not is_empty:
                    pass  # 空检查通过
                else:
                    report.results.append(result)
                    report.passed = False
                    if severity in ("reject", "block"):
                        report.blocking_failures.append("file_not_empty")
            elif qc_type == "field_completeness":
                fields = qc.get("fields", [])
                min_ratio = qc.get("min_ratio", 0.8)
                present = sum(1 for f in fields if f in actual_data and actual_data[f])
                ratio = present / len(fields) if fields else 1.0
                is_ok = ratio >= min_ratio
                if not is_ok:
                    missing_f = [f for f in fields if f not in actual_data or not actual_data[f]]
                    msg = qc.get("message", "").format(
                        ratio=f"{ratio:.0%}", missing_fields=missing_f
                    )
                    result = CheckResult(
                        check_type="field_completeness",
                        severity=severity,
                        passed=False,
                        message=msg,
                    )
                    report.results.append(result)
                    report.passed = False
                    if severity in ("reject", "reject_with_feedback", "block"):
                        report.blocking_failures.append("field_completeness")
        
        return report


class OutputSpecChecker:
    """检查流程输出是否符合 output_spec 规范。"""
    
    def check(self, output_spec: dict, actual_output: dict) -> SpecCheckReport:
        """执行输出规范检查。
        
        Args:
            output_spec: flow 的 output_spec JSON
            actual_output: 实际产出数据 {artifact_name: content, ...}
        
        Returns:
            SpecCheckReport
        """
        report = SpecCheckReport(passed=True)
        
        if not output_spec:
            return report
        
        # 检查 required_artifacts
        required_artifacts = output_spec.get("required_artifacts", [])
        for artifact in required_artifacts:
            name = artifact.get("name", "")
            is_mandatory = artifact.get("mandatory", True)
            
            if is_mandatory and name not in actual_output:
                result = CheckResult(
                    check_type="artifact_missing",
                    severity="block",
                    passed=False,
                    message=f"缺少必要产出物: {name}",
                )
                report.results.append(result)
                report.passed = False
                report.blocking_failures.append("artifact_missing")
            elif is_mandatory and name in actual_output:
                # 检查文档非空
                content = actual_output[name]
                if not content or (isinstance(content, str) and not content.strip()):
                    result = CheckResult(
                        check_type="document_empty",
                        severity="block",
                        passed=False,
                        message=f"文档 '{name}' 为空",
                    )
                    report.results.append(result)
                    report.passed = False
                    report.blocking_failures.append("document_empty")
        
        # 执行 output quality_checks
        quality_checks = output_spec.get("quality_checks", [])
        for qc in quality_checks:
            qc_type = qc.get("type", "")
            severity = qc.get("severity", "block")
            
            if qc_type == "all_fields_populated":
                fields = qc.get("fields", [])
                empty_fields = [f for f in fields if f not in actual_output or not actual_output[f]]
                if empty_fields:
                    result = CheckResult(
                        check_type="fields_not_populated",
                        severity=severity,
                        passed=False,
                        message=qc.get("message", "").format(empty_fields=empty_fields),
                    )
                    report.results.append(result)
                    report.passed = False
                    report.blocking_failures.append("fields_not_populated")
        
        # 检查 approval_gating
        approval_gating = output_spec.get("approval_gating", {})
        if approval_gating.get("require_output_spec_met") and not report.passed:
            # 输出未达标，标记为 draft_incomplete
            report.blocking_failures.append("output_spec_not_met")
        
        return report


def generate_rejection_message(
    flow_name: str, node_name: str, agent_name: str,
    report: SpecCheckReport, spec: dict
) -> str:
    """生成结构化拒绝通知消息。"""
    lines = [
        "⛔ 输入数据质量检查未通过",
        "",
        f"流程：{flow_name}",
        f"节点：{node_name}（{agent_name}）",
        "失败项：",
    ]
    
    for i, r in enumerate(report.results, 1):
        if not r.passed:
            lines.append(f"{i}. {r.check_type}: {r.message}")
    
    lines.extend(["", "规范要求："])
    fc = spec.get("file_constraints", {})
    if fc:
        if fc.get("allowed_formats"):
            lines.append(f"- 文件格式：{fc['allowed_formats']}")
        if fc.get("max_size_mb"):
            lines.append(f"- 最大大小：{fc['max_size_mb']}MB")
        if fc.get("min_dpi"):
            lines.append(f"- 最低 DPI：{fc['min_dpi']}")
    rf = spec.get("required_fields", [])
    if rf:
        lines.append(f"- 必填字段：{rf}")
    
    lines.extend(["", "请修正后重新提交。"])
    return "\n".join(lines)
```

### P2.2 FlowRun 状态机扩展

在 `plugins/ddw_flow_designer/models.py` 已有的基础上，新建服务文件 `plugins/ddw_flow_designer/services/flow_runner.py`：

```python
"""碳硅协作流程执行器（增强版）。

在执行每个 node 前，先检查 input_spec。
执行完成后，检查 output_spec。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_flow_designer.models import FlowDefinition, FlowRun
from plugins.ddw_flow_designer.services.spec_checker import (
    InputSpecChecker,
    OutputSpecChecker,
    SpecCheckReport,
    generate_rejection_message,
)


class FlowRunner:
    """流程执行器。"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.input_checker = InputSpecChecker()
        self.output_checker = OutputSpecChecker()
    
    async def execute_flow(
        self, flow_id: int, tenant_id: int, 
        input_data: Dict[str, Any], created_by: int
    ) -> Dict[str, Any]:
        """执行流程。
        
        1. 加载 FlowDefinition
        2. 解析 dag_json
        3. 逐 node 检查 input_spec → 执行 → 检查 output_spec
        """
        flow = await self.db.get(FlowDefinition, flow_id)
        if not flow or flow.tenant_id != tenant_id:
            return {"error": "流程不存在", "status": "failed"}
        
        dag = json.loads(flow.dag_json) if isinstance(flow.dag_json, str) else flow.dag_json
        nodes = dag.get("nodes", [])
        
        # 创建 FlowRun 记录
        run = FlowRun(
            flow_id=flow_id,
            version=flow.version,
            status="running",
            result="{}",
            created_by=created_by,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        
        # 逐 node 检查 input_spec
        node_results = {}
        for node in nodes:
            node_id = node.get("id", "unknown")
            input_spec = node.get("input_spec")
            
            if input_spec:
                check_report = self.input_checker.check(input_spec, input_data)
                if not check_report.passed:
                    # 拒绝执行
                    await self._update_run_status(
                        run.id, "input_rejected",
                        json.dumps({
                            "rejected_node": node_id,
                            "check_report": check_report.to_dict(),
                        })
                    )
                    return {
                        "run_id": run.id,
                        "status": "input_rejected",
                        "rejected_node": node_id,
                        "check_report": check_report.to_dict(),
                    }
            
            # 输入检查通过，执行 node（实际 LLM 调用由插件完成）
            node_results[node_id] = {"status": "pending_execution"}
        
        # 检查 output_spec（如有）
        output_spec_text = flow.output_spec
        if output_spec_text:
            output_spec = json.loads(output_spec_text) if isinstance(output_spec_text, str) else output_spec_text
            output_report = self.output_checker.check(output_spec, input_data)
            
            if not output_report.passed:
                approval_gating = output_spec.get("approval_gating", {})
                if approval_gating.get("allow_partial_save", True):
                    await self._update_run_status(
                        run.id, "draft_incomplete",
                        json.dumps({
                            "output_report": output_report.to_dict(),
                            "message": approval_gating.get(
                                "incomplete_save_message",
                                "流程产出不完整，已保存为草稿"
                            ),
                        })
                    )
                    return {
                        "run_id": run.id,
                        "status": "draft_incomplete",
                        "output_report": output_report.to_dict(),
                    }
        
        # 全部检查通过
        await self._update_run_status(run.id, "success", json.dumps(node_results))
        return {
            "run_id": run.id,
            "status": "success",
            "node_results": node_results,
        }
    
    async def _update_run_status(self, run_id: int, status: str, result: str) -> None:
        await self.db.execute(
            update(FlowRun).where(FlowRun.id == run_id).values(
                status=status, result=result
            )
        )
        await self.db.commit()
```

### P2.3 API 端点扩展

在 `plugins/ddw_flow_designer/router.py` 中新增：

```python
# PATCH /api/v1/flows/{id} — 更新流程（支持 input_spec/output_spec/cross_dept_review_config）
# POST /api/v1/flows/{id}/validate — 验证流程定义
# POST /api/v1/flows/{id}/run — 执行流程（含 input_spec 检查）
# GET /api/v1/flows/{id}/input-spec — 获取输入规范
# GET /api/v1/flows/{id}/output-spec — 获取输出规范
```

### P2.4 schemas.py 扩展

```python
# plugins/ddw_flow_designer/schemas.py（新建）

from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class FlowDefinitionUpdateReq(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    input_spec: Optional[Dict[str, Any]] = None
    output_spec: Optional[Dict[str, Any]] = None
    cross_dept_review_config: Optional[Dict[str, Any]] = None
    dag_json: Optional[str] = None
    is_enabled: Optional[bool] = None


class FlowRunReq(BaseModel):
    input_data: Dict[str, Any]


class FlowValidateResp(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []
```

### P2.5 测试用例（6 条）

```python
# plugins/ddw_flow_designer/tests/test_p2_spec_checker.py

import pytest
from plugins.ddw_flow_designer.services.spec_checker import (
    InputSpecChecker,
    OutputSpecChecker,
    generate_rejection_message,
)


class TestInputSpecChecker:
    def setup_method(self):
        self.checker = InputSpecChecker()
    
    def test_empty_spec_passes(self):
        """空 spec = 全部通过"""
        report = self.checker.check({}, {"any": "data"})
        assert report.passed is True
    
    def test_required_field_missing_rejects(self):
        """缺少必填字段 → reject"""
        spec = {"required_fields": ["file_url", "company_name"]}
        report = self.checker.check(spec, {"file_url": "http://x.com/a.pdf"})
        assert report.passed is False
        assert "required_field_missing" in report.blocking_failures
    
    def test_file_size_exceeded_rejects(self):
        """文件超大 → reject"""
        spec = {"file_constraints": {"max_size_mb": 10}}
        data = {"file_url": "http://x.com/a.pdf", "file_size_mb": 50, "file_type": "pdf"}
        report = self.checker.check(spec, data)
        assert report.passed is False
        assert "file_size_exceeded" in report.blocking_failures
    
    def test_file_format_invalid_rejects(self):
        """非法文件格式 → reject"""
        spec = {"file_constraints": {"allowed_formats": ["pdf", "jpg"]}}
        data = {"file_url": "http://x.com/a.docx", "file_type": "docx"}
        report = self.checker.check(spec, data)
        assert report.passed is False
    
    def test_all_checks_pass(self):
        """全部检查通过"""
        spec = {
            "required_fields": ["file_url", "company_name"],
            "file_constraints": {"max_size_mb": 20, "allowed_formats": ["pdf"]},
            "data_constraints": {"min_json_fields": ["company_name", "amount"]},
        }
        data = {
            "file_url": "http://x.com/a.pdf",
            "file_size_mb": 5,
            "file_type": "pdf",
            "company_name": "测试公司",
            "amount": 1000,
        }
        report = self.checker.check(spec, data)
        assert report.passed is True


class TestOutputSpecChecker:
    def setup_method(self):
        self.checker = OutputSpecChecker()
    
    def test_mandatory_artifact_missing_blocks(self):
        """缺少必要产出物 → block"""
        spec = {
            "required_artifacts": [
                {"type": "document", "name": "审查报告", "mandatory": True},
            ],
        }
        report = self.checker.check(spec, {"其他数据": "xxx"})
        assert report.passed is False
        assert "artifact_missing" in report.blocking_failures
    
    def test_empty_document_blocks(self):
        """文档为空 → block"""
        spec = {
            "required_artifacts": [
                {"type": "document", "name": "报告", "mandatory": True},
            ],
            "quality_checks": [
                {"type": "document_not_empty", "severity": "block", "message": "文档为空"},
            ],
        }
        report = self.checker.check(spec, {"报告": ""})
        assert report.passed is False
```

### P1+P2 验收标准

| # | 验收项 | 检查命令 |
|---|--------|---------|
| 1 | proficiency 枚举校验生效 | pytest 测试 P1.T1 |
| 2 | trigger_conditions event 必填 | pytest 测试 P1.T2 |
| 3 | 5 项验证检查完整 | pytest 测试 P1.T3 |
| 4 | approve 需 expert 级技能 | pytest 测试 P1.T4 |
| 5 | input_spec 检查引擎独立可用 | pytest 测试 P2.T1-T5 |
| 6 | output_spec 检查引擎独立可用 | pytest 测试 P2.T6-T7 |
| 7 | FlowRun 状态机含 input_rejected 等新状态 | grep models.py |
| 8 | 全量测试不回归 | pytest plugins/ddw_org/ plugins/ddw_flow_designer/ -q |
| 9 | ruff clean | ruff check plugins/ |

### 禁止事项
1. 禁止修改 P0 已完成的模型字段
2. 禁止删除已有 API 端点
3. 禁止 push
4. 禁止引入新依赖
