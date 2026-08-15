"""种子数据：11 部门 + 11 数字员工 + Skill 池。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_org.models import (
    AgentSkill,
    Department,
    DigitalAgent,
    OrgSkillPool,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 色板（11 色轮转）
# ---------------------------------------------------------------------------
AVATAR_COLORS: List[str] = [
    "#1890FF", "#52C41A", "#FAAD14", "#F5222D", "#722ED1",
    "#13C2C2", "#EB2F96", "#FA541C", "#2F54EB", "#A0D911", "#BF5416",
]

# ---------------------------------------------------------------------------
# 默认 Skill 池
# ---------------------------------------------------------------------------
DEFAULT_SKILL_POOL: List[Dict[str, str]] = [
    {"skill_key": "ddw.llm.chat", "name": "LLM 对话", "description": "通用大模型对话", "category": "ai"},
    {"skill_key": "ddw.kb.search", "name": "知识库检索", "description": "在知识库中搜索文档", "category": "knowledge"},
    {"skill_key": "ddw.email.send", "name": "发送邮件", "description": "发送邮件", "category": "email"},
    {"skill_key": "ddw.email.classify", "name": "邮件分类", "description": "自动分类邮件", "category": "email"},
    {"skill_key": "ddw.reminder", "name": "提醒", "description": "定时提醒", "category": "productivity"},
    {"skill_key": "ddw.legal.check", "name": "合规检查", "description": "法律合规审查", "category": "compliance"},
    {"skill_key": "ddw.esg.assess", "name": "ESG 评估", "description": "ESG 风险评估", "category": "compliance"},
    {"skill_key": "ddw.ocr.invoice", "name": "发票 OCR", "description": "发票识别提取", "category": "ocr"},
    {"skill_key": "ddw.ocr.contract", "name": "合同 OCR", "description": "合同识别提取", "category": "ocr"},
    {"skill_key": "ddw.workflow.approve", "name": "流程审批", "description": "审批流程处理", "category": "workflow"},
    {"skill_key": "ddw.kb.rebuild", "name": "知识库重建", "description": "重建知识库索引", "category": "knowledge"},
    {"skill_key": "ddw.sales.copilot", "name": "销售助手", "description": "销售辅助工具", "category": "sales"},
    {"skill_key": "ddw.crm.search", "name": "CRM 查询", "description": "CRM 数据查询", "category": "sales"},
    {"skill_key": "ddw.online_cs.reply", "name": "在线客服", "description": "在线客服自动回复", "category": "service"},
    {"skill_key": "ddw.ticket.create", "name": "工单创建", "description": "创建工单", "category": "service"},
    {"skill_key": "ddw.finance.ocr", "name": "财务 OCR", "description": "财务单据识别", "category": "finance"},
    {"skill_key": "ddw.reconciliation", "name": "对账", "description": "财务对账", "category": "finance"},
    {"skill_key": "ddw.hris.sync", "name": "HR 同步", "description": "HR 系统数据同步", "category": "hr"},
    {"skill_key": "ddw.leave.approve", "name": "请假审批", "description": "请假审批处理", "category": "hr"},
    {"skill_key": "ddw.code.review", "name": "代码审查", "description": "代码审查辅助", "category": "dev"},
    {"skill_key": "ddw.tech.research", "name": "技术调研", "description": "技术方案调研", "category": "dev"},
]

# ---------------------------------------------------------------------------
# 默认 11 部门 + 数字员工
# ---------------------------------------------------------------------------
DEFAULT_DEPARTMENTS: List[Dict[str, Any]] = [
    {
        "preset_id": "dept_01",
        "name": "全能前台",
        "default_agent_name": "笑笑",
        "role": "AI 前台助手",
        "job_objective": "作为企业第一接触点，高效处理来访咨询、邮件分发、日程协调",
        "work_boundary": "不做财务审批、不做合同签署、不做技术开发",
        "decision_scope": ["read", "create", "edit"],
        "default_skills": [
            {"skill_key": "ddw.llm.chat", "proficiency": "expert"},
            {"skill_key": "ddw.kb.search", "proficiency": "senior"},
            {"skill_key": "ddw.email.send", "proficiency": "senior"},
        ],
        "sort_order": 1,
    },
    {
        "preset_id": "dept_02",
        "name": "合规岗",
        "default_agent_name": "法海",
        "role": "合规审查员",
        "job_objective": "执行法律合规审查，确保企业运营符合法规要求",
        "work_boundary": "不做业务决策、不做合同谈判、不直接接触客户",
        "decision_scope": ["read", "approve"],
        "default_skills": [
            {"skill_key": "ddw.legal.check", "proficiency": "expert"},
            {"skill_key": "ddw.kb.search", "proficiency": "senior"},
            {"skill_key": "ddw.esg.assess", "proficiency": "senior"},
        ],
        "sort_order": 2,
    },
    {
        "preset_id": "dept_03",
        "name": "行政",
        "default_agent_name": "邮友",
        "role": "邮件助理",
        "job_objective": "高效处理企业邮件收发、分类归档、定时提醒",
        "work_boundary": "不做财务审批、不做人事决策、不发送机密邮件",
        "decision_scope": ["read", "create", "edit"],
        "default_skills": [
            {"skill_key": "ddw.email.send", "proficiency": "expert"},
            {"skill_key": "ddw.email.classify", "proficiency": "expert"},
            {"skill_key": "ddw.reminder", "proficiency": "senior"},
        ],
        "sort_order": 3,
    },
    {
        "preset_id": "dept_04",
        "name": "数据录入",
        "default_agent_name": "数据录入小助手",
        "role": "数据录入员",
        "job_objective": "通过 OCR 技术自动识别并录入发票、合同等单据数据",
        "work_boundary": "不做数据审核、不做财务核算、不处理异常单据",
        "decision_scope": ["read", "create"],
        "default_skills": [
            {"skill_key": "ddw.ocr.invoice", "proficiency": "expert"},
            {"skill_key": "ddw.ocr.contract", "proficiency": "senior"},
        ],
        "sort_order": 4,
    },
    {
        "preset_id": "dept_05",
        "name": "流程审批",
        "default_agent_name": "流程审批小助手",
        "role": "流程审批",
        "job_objective": "自动化处理企业内部审批流程，提升审批效率",
        "work_boundary": "不做金额超限审批、不做人事任免审批、不做合同终审",
        "decision_scope": ["read", "create", "approve"],
        "default_skills": [
            {"skill_key": "ddw.workflow.approve", "proficiency": "expert"},
            {"skill_key": "ddw.email.send", "proficiency": "senior"},
        ],
        "sort_order": 5,
    },
    {
        "preset_id": "dept_06",
        "name": "知识管理",
        "default_agent_name": "知识管理小助手",
        "role": "知识管理员",
        "job_objective": "维护企业知识库，确保知识文档的准确性和可检索性",
        "work_boundary": "不做内容创作、不做对外发布、不处理涉密文档",
        "decision_scope": ["read", "create", "edit"],
        "default_skills": [
            {"skill_key": "ddw.kb.rebuild", "proficiency": "expert"},
            {"skill_key": "ddw.kb.search", "proficiency": "expert"},
        ],
        "sort_order": 6,
    },
    {
        "preset_id": "dept_07",
        "name": "销售部",
        "default_agent_name": "销售小助手",
        "role": "销售助理",
        "job_objective": "辅助销售团队进行客户跟进、商机管理和数据分析",
        "work_boundary": "不做价格谈判、不做合同签署、不直接收款",
        "decision_scope": ["read", "create", "edit"],
        "default_skills": [
            {"skill_key": "ddw.sales.copilot", "proficiency": "expert"},
            {"skill_key": "ddw.crm.search", "proficiency": "senior"},
        ],
        "sort_order": 7,
    },
    {
        "preset_id": "dept_08",
        "name": "客服部",
        "default_agent_name": "客服小助手",
        "role": "客服专员",
        "job_objective": "提供7x24小时在线客服支持，处理常见咨询和工单",
        "work_boundary": "不做退款审批、不做投诉升级决策、不处理法律纠纷",
        "decision_scope": ["read", "create"],
        "default_skills": [
            {"skill_key": "ddw.online_cs.reply", "proficiency": "expert"},
            {"skill_key": "ddw.ticket.create", "proficiency": "senior"},
        ],
        "sort_order": 8,
    },
    {
        "preset_id": "dept_09",
        "name": "财务部",
        "default_agent_name": "财务小助手",
        "role": "财务审核",
        "job_objective": "辅助财务团队进行单据识别、对账和基础财务处理",
        "work_boundary": "不做资金划转、不做税务申报、不做审计结论",
        "decision_scope": ["read", "create"],
        "default_skills": [
            {"skill_key": "ddw.finance.ocr", "proficiency": "expert"},
            {"skill_key": "ddw.reconciliation", "proficiency": "senior"},
        ],
        "sort_order": 9,
    },
    {
        "preset_id": "dept_10",
        "name": "人事部",
        "default_agent_name": "人事小助手",
        "role": "HR 助理",
        "job_objective": "辅助 HR 团队处理考勤、请假、入职等日常事务",
        "work_boundary": "不做薪酬决策、不做辞退处理、不接触薪资明细",
        "decision_scope": ["read", "create", "edit"],
        "default_skills": [
            {"skill_key": "ddw.hris.sync", "proficiency": "expert"},
            {"skill_key": "ddw.leave.approve", "proficiency": "senior"},
        ],
        "sort_order": 10,
    },
    {
        "preset_id": "dept_11",
        "name": "研发 IT",
        "default_agent_name": "研发小助手",
        "role": "研发助手",
        "job_objective": "辅助研发团队进行代码审查、技术调研和文档整理",
        "work_boundary": "不做代码合并决策、不做架构变更、不直接部署生产环境",
        "decision_scope": ["read", "create", "edit"],
        "default_skills": [
            {"skill_key": "ddw.code.review", "proficiency": "expert"},
            {"skill_key": "ddw.tech.research", "proficiency": "senior"},
        ],
        "sort_order": 11,
    },
]


async def seed_org_for_tenant(
    session: AsyncSession,
    tenant_id: int,
    force: bool = False,
) -> Dict[str, Any]:
    """为租户创建种子数据（幂等）。

    Args:
        session: 异步数据库 session
        tenant_id: 租户 ID
        force: True 时清空重建

    Returns:
        {"departments": int, "agents": int, "skills": int}
    """
    # 幂等检查
    count_stmt = select(func.count(Department.id)).where(
        Department.tenant_id == tenant_id
    )
    existing_count = (await session.execute(count_stmt)).scalar_one()

    if existing_count > 0 and not force:
        logger.info(
            "seed_org_for_tenant: tenant %d already has %d departments, skipping",
            tenant_id,
            existing_count,
        )
        return {"departments": existing_count, "agents": 0, "skills": 0, "skipped": True}

    if force and existing_count > 0:
        # 清空旧数据（按 FK 依赖顺序）
        # AgentSkill 没有 tenant_id，需通过 agent 关联删除
        agent_ids_subq = (
            select(DigitalAgent.id).where(DigitalAgent.tenant_id == tenant_id)
        )
        await session.execute(
            AgentSkill.__table__.delete().where(AgentSkill.agent_id.in_(agent_ids_subq))
        )
        await session.execute(
            DigitalAgent.__table__.delete().where(DigitalAgent.tenant_id == tenant_id)
        )
        await session.execute(
            Department.__table__.delete().where(Department.tenant_id == tenant_id)
        )
        await session.flush()

    # --- Skill 池（全局，只需 seed 一次） ---
    pool_count = (await session.execute(select(func.count(OrgSkillPool.id)))).scalar_one()
    if pool_count == 0:
        for sk in DEFAULT_SKILL_POOL:
            session.add(OrgSkillPool(**sk))
        await session.flush()
        logger.info("seed_org_for_tenant: seeded %d skills to pool", len(DEFAULT_SKILL_POOL))
    skill_pool = {
        sp.skill_key: sp.id
        for sp in (await session.execute(select(OrgSkillPool))).scalars().all()
    }

    # --- 部门 + 数字员工 ---
    for idx, dept_def in enumerate(DEFAULT_DEPARTMENTS):
        color = AVATAR_COLORS[idx % len(AVATAR_COLORS)]
        dept = Department(
            tenant_id=tenant_id,
            name=dept_def["name"],
            preset_id=dept_def["preset_id"],
            sort_order=dept_def["sort_order"],
        )
        session.add(dept)
        await session.flush()  # 拿到 dept.id

        agent = DigitalAgent(
            tenant_id=tenant_id,
            department_id=dept.id,
            name=dept_def["default_agent_name"],
            role=dept_def["role"],
            avatar_color=color,
            preset_id=dept_def["preset_id"],
            default_skills=[s["skill_key"] for s in dept_def["default_skills"]],
            job_objective=dept_def.get("job_objective", ""),
            work_boundary=dept_def.get("work_boundary", ""),
            decision_scope=dept_def.get("decision_scope", []),
        )
        session.add(agent)
        await session.flush()  # 拿到 agent.id

        # 分配默认 skill
        for skill_def in dept_def["default_skills"]:
            skill_key = skill_def["skill_key"]
            proficiency = skill_def.get("proficiency", "junior")
            skill_pool_id = skill_pool.get(skill_key)
            if skill_pool_id is not None:
                session.add(AgentSkill(
                    agent_id=agent.id,
                    skill_id=skill_pool_id,
                    proficiency=proficiency,
                ))

    await session.commit()
    logger.info(
        "seed_org_for_tenant: seeded %d departments + agents for tenant %d",
        len(DEFAULT_DEPARTMENTS),
        tenant_id,
    )
    return {
        "departments": len(DEFAULT_DEPARTMENTS),
        "agents": len(DEFAULT_DEPARTMENTS),
        "skills": len(DEFAULT_SKILL_POOL),
        "skipped": False,
    }


__all__ = [
    "DEFAULT_DEPARTMENTS",
    "DEFAULT_SKILL_POOL",
    "seed_org_for_tenant",
]
