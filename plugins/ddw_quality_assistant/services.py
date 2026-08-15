"""Business logic for Quality Assistant plugin."""
from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy.orm import Session

from .models import FiveWhyAnalysis, QualityDocument, QualityTemplate


class QualityAssistantService:
    """Core service for quality document generation and management."""

    def __init__(self, db_session: Session, llm_client: Any = None):
        self.db = db_session
        self.llm = llm_client

    # === Document Generation ===

    def generate_8d_report(self, problem: str, product: str = "",
                           batch: str = "", severity: str = "major",
                           language: str = "zh-CN") -> QualityDocument:
        """Generate an 8D problem-solving report draft."""
        prompt = self._build_8d_prompt(problem, product, batch, severity, language)
        content = self._call_llm(prompt) if self.llm else self._mock_8d(problem, product, batch)

        doc = QualityDocument(
            doc_type="8d",
            title=f"8D Report: {problem[:80]}",
            content=content,
            input_data={"problem": problem, "product": product,
                        "batch": batch, "severity": severity},
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def generate_capa_draft(self, nonconformity: str, source: str = "internal_audit",
                            severity: str = "major",
                            language: str = "zh-CN") -> QualityDocument:
        """Generate a CAPA (Corrective and Preventive Action) draft."""
        prompt = self._build_capa_prompt(nonconformity, source, severity, language)
        content = self._call_llm(prompt) if self.llm else self._mock_capa(nonconformity, source)

        doc = QualityDocument(
            doc_type="capa",
            title=f"CAPA: {nonconformity[:80]}",
            content=content,
            input_data={"nonconformity": nonconformity, "source": source, "severity": severity},
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def generate_deviation_report(self, deviation_desc: str, product: str = "",
                                  batch: str = "", process_step: str = "",
                                  language: str = "zh-CN") -> QualityDocument:
        """Generate a deviation investigation report draft."""
        prompt = self._build_deviation_prompt(deviation_desc, product, batch, process_step, language)
        content = self._call_llm(prompt) if self.llm else self._mock_deviation(deviation_desc)

        doc = QualityDocument(
            doc_type="deviation",
            title=f"Deviation: {deviation_desc[:80]}",
            content=content,
            input_data={"description": deviation_desc, "product": product,
                        "batch": batch, "process_step": process_step},
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def generate_complaint_reply(self, complaint: str, customer: str = "",
                                 product: str = "", tone: str = "professional",
                                 language: str = "zh-CN") -> QualityDocument:
        """Generate a customer complaint reply draft."""
        prompt = self._build_complaint_prompt(complaint, customer, product, tone, language)
        content = self._call_llm(prompt) if self.llm else self._mock_complaint(complaint, customer)

        doc = QualityDocument(
            doc_type="complaint",
            title=f"Complaint Reply: {complaint[:80]}",
            content=content,
            input_data={"complaint": complaint, "customer": customer,
                        "product": product, "tone": tone},
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def perform_5why_analysis(self, problem: str, context: str = "",
                              language: str = "zh-CN") -> FiveWhyAnalysis:
        """Perform 5-Why root cause analysis."""
        prompt = self._build_5why_prompt(problem, context, language)
        result = self._call_llm(prompt) if self.llm else self._mock_5why(problem)

        analysis = FiveWhyAnalysis(
            problem_description=problem,
            why_chain=result.get("why_chain", []),
            root_cause=result.get("root_cause", "待确认"),
            corrective_action=result.get("corrective_action", ""),
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)
        return analysis

    # === CRUD ===

    def list_documents(self, doc_type: Optional[str] = None,
                       status: Optional[str] = None,
                       limit: int = 50) -> List[QualityDocument]:
        q = self.db.query(QualityDocument)
        if doc_type:
            q = q.filter(QualityDocument.doc_type == doc_type)
        if status:
            q = q.filter(QualityDocument.status == status)
        return q.order_by(QualityDocument.created_at.desc()).limit(limit).all()

    def get_document(self, doc_id: int) -> Optional[QualityDocument]:
        return self.db.query(QualityDocument).get(doc_id)

    def update_document_status(self, doc_id: int, status: str) -> Optional[QualityDocument]:
        doc = self.db.query(QualityDocument).get(doc_id)
        if doc:
            doc.status = status
            self.db.commit()
            self.db.refresh(doc)
        return doc

    def list_templates(self, doc_type: Optional[str] = None,
                       industry: Optional[str] = None) -> List[QualityTemplate]:
        q = self.db.query(QualityTemplate)
        if doc_type:
            q = q.filter(QualityTemplate.doc_type == doc_type)
        if industry:
            q = q.filter(QualityTemplate.industry == industry)
        return q.all()

    def list_5why_analyses(self, limit: int = 20) -> List[FiveWhyAnalysis]:
        return self.db.query(FiveWhyAnalysis).order_by(
            FiveWhyAnalysis.created_at.desc()
        ).limit(limit).all()

    # === LLM Prompt Builders ===

    def _build_8d_prompt(self, problem, product, batch, severity, lang) -> str:
        return f"""你是一名资深质量工程师。请根据以下信息生成一份完整的8D问题解决报告。

问题描述：{problem}
产品：{product or '未指定'}
批次：{batch or '未指定'}
严重程度：{severity}

请按8D标准格式输出：
D0: 准备/紧急响应
D1: 建立团队
D2: 问题描述（5W2H）
D3: 临时遏制措施
D4: 根本原因分析
D5: 永久纠正措施
D6: 验证纠正措施有效性
D7: 预防措施
D8: 团队祝贺与关闭

语言：{lang}
每个D步骤需要有具体内容，不能只写标题。"""

    def _build_capa_prompt(self, nonconformity, source, severity, lang) -> str:
        return f"""你是一名资深质量工程师。请根据以下信息生成一份CAPA（纠正与预防措施）草案。

不符合项描述：{nonconformity}
来源：{source}
严重程度：{severity}

请按以下格式输出：
1. 不符合项描述
2. 影响评估
3. 根本原因分析（使用鱼骨图/5Why方法）
4. 纠正措施（短期）
5. 预防措施（长期）
6. 验证方法
7. 责任人与时间计划
8. 关闭标准

语言：{lang}"""

    def _build_deviation_prompt(self, desc, product, batch, step, lang) -> str:
        return f"""你是一名资深质量工程师。请根据以下偏差信息生成偏差调查报告草案。

偏差描述：{desc}
产品：{product or '未指定'}
批次：{batch or '未指定'}
工艺步骤：{step or '未指定'}

请按以下格式输出：
1. 偏差概述
2. 偏差分类（关键/主要/次要）
3. 影响评估
4. 调查发现
5. 根本原因
6. 纠正与预防措施
7. 产品处置建议
8. 关闭条件

语言：{lang}"""

    def _build_complaint_prompt(self, complaint, customer, product, tone, lang) -> str:
        return f"""你是一名专业的客户服务经理。请根据以下客户投诉生成正式回复函。

客户投诉内容：{complaint}
客户名称：{customer or '未指定'}
涉及产品：{product or '未指定'}
语气：{tone}

请生成一份专业的客户投诉回复，包含：
1. 致歉与确认
2. 调查结果说明
3. 纠正措施
4. 预防措施
5. 补偿/后续跟进方案
6. 联系方式

语言：{lang}"""

    def _build_5why_prompt(self, problem, context, lang) -> str:
        return f"""你是一名质量工程师，擅长根本原因分析。请对以下问题执行5-Why分析。

问题：{problem}
背景信息：{context or '无'}

请以JSON格式输出：
{{
  "why_chain": [
    {{"why": "为什么1", "answer": "原因1"}},
    {{"why": "为什么2", "answer": "原因2"}},
    {{"why": "为什么3", "answer": "原因3"}},
    {{"why": "为什么4", "answer": "原因4"}},
    {{"why": "为什么5", "answer": "根本原因"}}
  ],
  "root_cause": "根本原因总结",
  "corrective_action": "建议的纠正措施"
}}

语言：{lang}"""

    def _call_llm(self, prompt: str) -> str:
        """Call LLM client. Override in production."""
        if hasattr(self.llm, 'generate'):
            return self.llm.generate(prompt)
        return str(self.llm(prompt))

    # === Mock responses for testing ===

    def _mock_8d(self, problem, product, batch):
        return f"""# 8D 问题解决报告

## D0: 准备/紧急响应
针对问题"{problem}"启动紧急响应流程。

## D1: 建立团队
质量部、生产部、研发部组成跨职能团队。

## D2: 问题描述
- 产品：{product or '待填写'}
- 批次：{batch or '待填写'}
- 问题：{problem}

## D3: 临时遏制措施
对该批次产品进行隔离检查，暂停相关批次出货。

## D4: 根本原因分析
通过5Why分析和鱼骨图分析确定根本原因。

## D5: 永久纠正措施
制定并实施永久性纠正措施。

## D6: 验证纠正措施有效性
跟踪验证30天，确认纠正措施有效。

## D7: 预防措施
更新FMEA和控制计划，纳入培训计划。

## D8: 团队祝贺与关闭
确认所有措施有效实施，正式关闭。"""

    def _mock_capa(self, nonconformity, source):
        return f"""# CAPA 纠正与预防措施报告

## 1. 不符合项描述
{nonconformity}
来源：{source}

## 2. 影响评估
评估不符合项对产品质量和食品安全的影响范围。

## 3. 根本原因分析
使用鱼骨图和5Why方法分析根本原因。

## 4. 纠正措施（短期）
- 立即隔离受影响产品
- 加强过程监控频率

## 5. 预防措施（长期）
- 更新SOP和作业指导书
- 增加过程控制点
- 开展员工培训

## 6. 验证方法
- 30天跟踪验证
- 过程能力指数确认

## 7. 责任人与时间计划
质量部负责跟踪，30天内完成验证。

## 8. 关闭标准
所有措施实施完毕且验证有效。"""

    def _mock_deviation(self, desc):
        return f"""# 偏差调查报告

## 1. 偏差概述
{desc}

## 2. 偏差分类
根据影响程度评估为【待评估】级偏差。

## 3. 影响评估
评估偏差对产品质量、食品安全的影响。

## 4. 调查发现
对偏差发生的过程进行详细调查。

## 5. 根本原因
通过调查确定偏差的根本原因。

## 6. 纠正与预防措施
制定针对性的纠正和预防措施。

## 7. 产品处置建议
根据评估结果决定产品处置方式。

## 8. 关闭条件
所有措施执行完毕，验证有效后关闭。"""

    def _mock_complaint(self, complaint, customer):
        return f"""# 客户投诉回复函

尊敬的{customer or '客户'}：

感谢您向我们反馈产品使用过程中遇到的问题。

## 确认与致歉
我们已收到并认真对待您的投诉：{complaint[:100]}...

## 调查结果
我们已对相关批次进行了详细调查。

## 纠正措施
已采取以下纠正措施确保问题不再发生。

## 预防措施
已更新相关SOP和控制计划。

## 后续跟进
我们将在7个工作日内提供详细的调查报告。

此致敬礼
质量保证部"""

    def _mock_5why(self, problem):
        return {
            "why_chain": [
                {"why": "为什么发生了这个问题？", "answer": f"因为{problem}的直接原因"},
                {"why": "为什么会有这个直接原因？", "answer": "因为过程控制不足"},
                {"why": "为什么过程控制不足？", "answer": "因为SOP未覆盖此场景"},
                {"why": "为什么SOP未覆盖？", "answer": "因为风险评估不充分"},
                {"why": "为什么风险评估不充分？", "answer": "因为缺乏系统性的FMEA分析流程"},
            ],
            "root_cause": "缺乏系统性的FMEA分析流程，导致风险评估覆盖不充分",
            "corrective_action": "建立FMEA定期评审机制，更新SOP，开展专项培训",
        }
