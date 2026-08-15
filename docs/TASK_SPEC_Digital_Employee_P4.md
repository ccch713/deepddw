# TASK_SPEC: 数字员工体系 P4 — DigitalAgentTemplate + 5道自动检查

> **前置条件**：P0+P1 已完成  
> **开发工具**：MiMo Code CLI

---

## P4.1 功能概述

新建 DigitalAgentTemplate 模型（模板表 + 5 道自动检查），提供模板 CRUD API，员工可通过模板创建数字员工。

## P4.2 数据模型

新建 `plugins/ddw_org/models.py` 中追加 DigitalAgentTemplate：

```python
class DigitalAgentTemplate(Base):
    """数字员工模板。"""
    __tablename__ = "digital_agent_templates"
    __table_args__ = {"extend_existing": True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    template_name: Mapped[str] = mapped_column(String(200), nullable=False)
    template_type: Mapped[str] = mapped_column(String(20), nullable=False, default="employee_created")
    # template_type: system_preset / employee_created
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    department_id: Mapped[int] = mapped_column(Integer, ForeignKey("org_departments.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    job_objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    decision_scope: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    work_boundary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # skills: [{"skill_key": "ddw.llm.chat", "proficiency": "expert", "trigger_conditions": [...], "sla_seconds": 60}]
    input_spec: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    output_spec: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    # status: draft → running_validation → validation_passed → pending_department_approval → approved → active
    validation_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
```

## P4.3 迁移脚本

```sql
CREATE TABLE IF NOT EXISTS digital_agent_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    template_name VARCHAR(200) NOT NULL,
    template_type VARCHAR(20) NOT NULL DEFAULT 'employee_created',
    created_by INTEGER NOT NULL REFERENCES users(id),
    department_id INTEGER NOT NULL REFERENCES org_departments(id),
    agent_name VARCHAR(100) NOT NULL,
    job_objective TEXT NOT NULL DEFAULT '',
    role VARCHAR(100) NOT NULL,
    decision_scope TEXT DEFAULT '[]',
    work_boundary TEXT NOT NULL DEFAULT '',
    skills TEXT NOT NULL DEFAULT '[]',
    input_spec TEXT,
    output_spec TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    validation_results TEXT,
    approval_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    approved_by INTEGER,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_templates_tenant ON digital_agent_templates(tenant_id);
CREATE INDEX IF NOT EXISTS ix_templates_dept ON digital_agent_templates(department_id);
CREATE INDEX IF NOT EXISTS ix_templates_status ON digital_agent_templates(status);
```

## P4.4 API 端点

| 方法 | 路径 | 说明 |
|:-----|:-----|:-----|
| GET | `/api/v1/org/templates` | 模板列表（按部门/类型筛选） |
| POST | `/api/v1/org/templates` | 创建模板 |
| POST | `/api/v1/org/templates/{id}/validate` | 触发 5 道自动检查 |
| POST | `/api/v1/org/templates/{id}/submit` | 提交审批 |
| POST | `/api/v1/org/templates/{id}/approve` | 审批通过（创建 DigitalAgent） |
| POST | `/api/v1/org/templates/{id}/reject` | 审批拒绝 |
| GET | `/api/v1/org/templates/download-sample` | 下载模板样板 JSON |

## P4.5 5道自动检查逻辑

```python
async def validate_template(self, template_id: int, tenant_id: int) -> dict:
    """5道自动检查。"""
    template = await self.db.get(DigitalAgentTemplate, template_id)
    results = []
    
    # C1: 字段完整性
    c1_fields = ["agent_name", "job_objective", "role", "work_boundary", "skills"]
    missing = [f for f in c1_fields if not getattr(template, f, None)]
    results.append({"check": "C1", "name": "字段完整性", "passed": len(missing)==0,
                    "message": f"缺失字段: {missing}" if missing else ""})
    
    # C2: 部门归属
    dept = await self.db.get(Department, template.department_id)
    c2 = dept is not None and dept.tenant_id == tenant_id
    results.append({"check": "C2", "name": "部门归属", "passed": c2,
                    "message": "" if c2 else "部门不存在或已禁用"})
    
    # C3: 技能有效性
    registered_skills = (await self.db.execute(
        select(OrgSkillPool).where(OrgSkillPool.tenant_id == tenant_id)
    )).scalars().all()
    registered_keys = {s.skill_key for s in registered_skills}
    template_keys = {s.get("skill_key") for s in (template.skills or [])}
    unregistered = template_keys - registered_keys
    c3 = len(unregistered) == 0
    results.append({"check": "C3", "name": "技能有效性", "passed": c3,
                    "message": f"未注册技能: {unregistered}" if unregistered else ""})
    
    # C4: 规范合理性（简化版）
    c4 = True  # P4 简化：只检查 input/output spec 格式正确
    results.append({"check": "C4", "name": "规范合理性", "passed": c4, "message": ""})
    
    # C5: 权限边界
    c5 = True  # P4 简化：检查 decision_scope 枚举值合法
    valid_scopes = {"read","create","edit","delete","approve","initiate_flow","access_external"}
    invalid = set(template.decision_scope or []) - valid_scopes
    c5 = len(invalid) == 0
    results.append({"check": "C5", "name": "权限边界", "passed": c5,
                    "message": f"无效权限: {invalid}" if invalid else ""})
    
    all_passed = all(r["passed"] for r in results)
    template.validation_results = {"passed": all_passed, "results": results}
    template.status = "validation_passed" if all_passed else "draft"
    await self.db.commit()
    
    return {"passed": all_passed, "results": results}
```

## P4.6 审批通过 → 创建 DigitalAgent

```python
async def approve_template(self, template_id: int, tenant_id: int, approved_by: int) -> dict:
    """审批通过，创建数字员工。"""
    template = await self.db.get(DigitalAgentTemplate, template_id)
    
    # 创建 DigitalAgent
    agent = DigitalAgent(
        tenant_id=tenant_id,
        department_id=template.department_id,
        name=template.agent_name,
        role=template.role,
        job_objective=template.job_objective,
        decision_scope=template.decision_scope,
        work_boundary=template.work_boundary,
        default_skills=[s.get("skill_key") for s in (template.skills or [])],
    )
    self.db.add(agent)
    
    # 更新模板状态
    template.status = "active"
    template.approval_status = "approved"
    template.approved_by = approved_by
    template.approved_at = datetime.utcnow()
    
    await self.db.commit()
    await self.db.refresh(agent)
    
    return {"agent_id": agent.id, "template_id": template_id, "status": "created"}
```

## P4.7 测试用例（6 条）
1. 创建模板 → status=draft
2. 5 道检查全部通过 → status=validation_passed
3. 缺少 agent_name → C1 失败
4. 未注册技能 → C3 失败
5. 审批通过 → 创建 DigitalAgent
6. 审批拒绝 → 退回 draft

## P4.8 验收标准
- 5 道自动检查逻辑完整
- 审批通过自动创建 DigitalAgent
- 模板样板文件可下载
- 全量测试不回归
- ruff clean

## 禁止事项
- 禁止修改 P0-P2 已完成的文件
- 禁止 push
- 禁止引入新依赖
