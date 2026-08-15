"""Business logic for Regulatory Evidence plugin."""
from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .models import EvidenceChain, RegulatoryDocument


class RegulatoryEvidenceService:
    """Core service for regulatory document management and evidence chain tracking."""

    def __init__(self, db_session: Session, llm_client: Any = None):
        self.db = db_session
        self.llm = llm_client

    # === Regulatory Documents ===

    def add_document(self, title: str, content: str, jurisdiction: str,
                     authority: str, doc_type: str, category: str = "general",
                     reference_number: str = "", effective_date: str = "",
                     tags: Optional[List[str]] = None,
                     source_url: str = "") -> RegulatoryDocument:
        doc = RegulatoryDocument(
            title=title, content=content, jurisdiction=jurisdiction,
            authority=authority, doc_type=doc_type, category=category,
            reference_number=reference_number, effective_date=effective_date,
            tags=tags or [], source_url=source_url
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def get_document(self, doc_id: int) -> Optional[RegulatoryDocument]:
        return self.db.query(RegulatoryDocument).get(doc_id)

    def list_documents(self, jurisdiction: Optional[str] = None,
                       authority: Optional[str] = None,
                       doc_type: Optional[str] = None,
                       category: Optional[str] = None,
                       limit: int = 50) -> List[RegulatoryDocument]:
        q = self.db.query(RegulatoryDocument)
        if jurisdiction:
            q = q.filter(RegulatoryDocument.jurisdiction == jurisdiction)
        if authority:
            q = q.filter(RegulatoryDocument.authority == authority)
        if doc_type:
            q = q.filter(RegulatoryDocument.doc_type == doc_type)
        if category:
            q = q.filter(RegulatoryDocument.category == category)
        return q.order_by(RegulatoryDocument.updated_at.desc()).limit(limit).all()

    def search_documents(self, query: str, jurisdiction: Optional[str] = None,
                         limit: int = 10) -> List[RegulatoryDocument]:
        q = self.db.query(RegulatoryDocument)
        term = f"%{query}%"
        q = q.filter(or_(
            RegulatoryDocument.title.ilike(term),
            RegulatoryDocument.content.ilike(term),
            RegulatoryDocument.reference_number.ilike(term),
        ))
        if jurisdiction:
            q = q.filter(RegulatoryDocument.jurisdiction == jurisdiction)
        return q.limit(limit).all()

    # === Evidence Chains ===

    def create_evidence_chain(self, requirement: str, regulation_id: Optional[int] = None,
                               product_name: str = "",
                               compliance_status: str = "pending",
                               evidence_description: str = "",
                               evidence_documents: Optional[List[str]] = None,
                               gaps: str = "", action_plan: str = "",
                               responsible: str = "",
                               due_date: str = "") -> EvidenceChain:
        chain = EvidenceChain(
            requirement=requirement, regulation_id=regulation_id,
            product_name=product_name, compliance_status=compliance_status,
            evidence_description=evidence_description,
            evidence_documents=evidence_documents or [],
            gaps=gaps, action_plan=action_plan,
            responsible=responsible, due_date=due_date
        )
        self.db.add(chain)
        self.db.commit()
        self.db.refresh(chain)
        return chain

    def get_evidence_chain(self, chain_id: int) -> Optional[EvidenceChain]:
        return self.db.query(EvidenceChain).get(chain_id)

    def list_evidence_chains(self, product_name: Optional[str] = None,
                              compliance_status: Optional[str] = None,
                              limit: int = 50) -> List[EvidenceChain]:
        q = self.db.query(EvidenceChain)
        if product_name:
            q = q.filter(EvidenceChain.product_name == product_name)
        if compliance_status:
            q = q.filter(EvidenceChain.compliance_status == compliance_status)
        return q.order_by(EvidenceChain.updated_at.desc()).limit(limit).all()

    def update_evidence_chain(self, chain_id: int, **kwargs) -> Optional[EvidenceChain]:
        chain = self.db.query(EvidenceChain).get(chain_id)
        if not chain:
            return None
        for k, v in kwargs.items():
            if hasattr(chain, k):
                setattr(chain, k, v)
        self.db.commit()
        self.db.refresh(chain)
        return chain

    # === Pre-built Regulatory Data ===

    def seed_food_regulations(self):
        """Seed with core food safety regulatory documents."""
        regulations = [
            {"title": "中华人民共和国食品安全法（2021修正）", "content": "食品安全基本法。核心要求：食品生产经营者对其生产经营食品的安全负责。建立食品安全追溯体系。实施食品安全风险管理。关键条款：第34条（禁止生产经营的食品）、第63条（食品召回）、第67条（标签要求）、第81条（婴幼儿配方食品）。",
             "jurisdiction": "CN", "authority": "NHC", "doc_type": "regulation",
             "category": "food_safety", "reference_number": "主席令第21号",
             "tags": ["食品安全法", "基本法"]},
            {"title": "GB 14881-2013 食品安全国家标准 食品生产通用卫生规范", "content": "食品生产GMP国家标准。规定了食品生产过程中原料采购、加工、包装、贮存和运输等环节的场所、设施、人员的基本要求和管理准则。是食品生产企业必须达到的基础要求。",
             "jurisdiction": "CN", "authority": "NHC", "doc_type": "regulation",
             "category": "gmp", "reference_number": "GB 14881-2013",
             "tags": ["GMP", "卫生规范"]},
            {"title": "新食品原料安全性审查管理办法", "content": "规定新食品原料的申请、审查和管理。新食品原料是指在我国无传统食用习惯的物品，包括：动物、植物和微生物；从动物、植物和微生物中分离的成分；原有结构发生改变的食品成分；其他新研制的食品原料。申请材料需包括：成分分析、卫生学检验、毒理学评价、安全性评估。",
             "jurisdiction": "CN", "authority": "NHC", "doc_type": "regulation",
             "category": "novel_food", "reference_number": "国家卫计委令第1号",
             "tags": ["新食品原料", "审批"]},
            {"title": "Regulation (EU) 2015/2283 — Novel Food Regulation", "content": "EU Novel Food regulation. Defines novel food as food not significantly consumed in the EU before May 15, 1997. Authorization process: application → EFSA risk assessment → Commission decision. Required dossier: identity, production process, compositional data, specifications, intended use levels, toxicological data, allergenicity assessment.",
             "jurisdiction": "EU", "authority": "EU_Commission", "doc_type": "regulation",
             "category": "novel_food", "reference_number": "Regulation (EU) 2015/2283",
             "tags": ["Novel Food", "EU", "authorization"]},
            {"title": "EFSA Guidance on Novel Food Applications", "content": "EFSA scientific guidance for applicants preparing Novel Food applications. Covers: identity characterization, production process description, compositional analysis, specification, intended uses, absorption/metabolism/distribution, nutritional information, toxicological information, allergenicity.",
             "jurisdiction": "EU", "authority": "EFSA", "doc_type": "guidance",
             "category": "novel_food", "reference_number": "EFSA-Q-2016-00625",
             "tags": ["EFSA", "guidance", "application"]},
            {"title": "Codex Alimentarius — General Principles of Food Hygiene (CXC 1-1969)", "content": "International food hygiene standard. Foundation for HACCP. Covers: primary production, establishment design, control of operation, maintenance/sanitation, personal hygiene, transport, product information, training. HACCP annex provides 7 principles and implementation guidelines.",
             "jurisdiction": "INT", "authority": "Codex", "doc_type": "regulation",
             "category": "haccp", "reference_number": "CXC 1-1969",
             "tags": ["Codex", "HACCP", "food hygiene"]},
            {"title": "食品召回管理办法（2015）", "content": "食品召回分级管理。一级召回：可能导致严重健康损害甚至死亡。二级召回：可能导致一般健康损害。三级召回：标签标识等不会造成健康损害。召回流程：停止生产→通知经营者和消费者→向监管部门报告→召回产品处置→提交总结报告。",
             "jurisdiction": "CN", "authority": "CFSA", "doc_type": "regulation",
             "category": "recall", "reference_number": "国家食药监总局令第12号",
             "tags": ["召回", "食品安全"]},
            {"title": "Regulation (EC) No 178/2002 — General Food Law", "content": "EU General Food Law. Establishes EFSA. Key principles: precautionary principle, risk analysis, traceability. Article 14: food shall not be placed on market if unsafe. Article 18: traceability requirements. Article 19: food business operator obligations.",
             "jurisdiction": "EU", "authority": "EU_Commission", "doc_type": "regulation",
             "category": "food_safety", "reference_number": "Regulation (EC) No 178/2002",
             "tags": ["EU", "General Food Law", "EFSA"]},
        ]
        for r in regulations:
            existing = self.db.query(RegulatoryDocument).filter_by(title=r["title"]).first()
            if not existing:
                self.add_document(**r)
        return len(regulations)

    def seed_cabio_evidence_template(self):
        """Create a template evidence chain for Cabio Biotech."""
        template_chains = [
            {"requirement": "CABIO-A-2藻油DHA符合EU Novel Food授权条件",
             "product_name": "CABIO-A-2 DHA藻油", "compliance_status": "compliant",
             "evidence_description": "已获得EU Implementing Regulation (EU) 2024/2101授权",
             "gaps": "", "action_plan": "保持授权状态，监控续期要求"},
            {"requirement": "婴幼儿配方食品符合GB 10765要求",
             "product_name": "ARA粉剂/藻油DHA", "compliance_status": "pending",
             "evidence_description": "需确认产品规格符合最新国标",
             "gaps": "需确认最新国标版本要求", "action_plan": "法规部核查最新版GB 10765"},
            {"requirement": "HACCP体系有效运行并定期验证",
             "product_name": "全产品线", "compliance_status": "compliant",
             "evidence_description": "已建立HACCP体系",
             "gaps": "", "action_plan": "年度HACCP验证"},
            {"requirement": "食品安全追溯体系覆盖全链条",
             "product_name": "全产品线", "compliance_status": "partial",
             "evidence_description": "部分产品追溯已实现",
             "gaps": "原料批次到成品批次的正向追溯需强化",
             "action_plan": "完善ERP批次追溯模块"},
            {"requirement": "新食品原料申报材料完整归档",
             "product_name": "2-FL/HMOs", "compliance_status": "pending",
             "evidence_description": "2-FL已获批，需持续管理申报档案",
             "gaps": "申报档案管理分散",
             "action_plan": "建立集中的法规申报档案库"},
        ]
        for tc in template_chains:
            self.create_evidence_chain(**tc)
        return len(template_chains)
