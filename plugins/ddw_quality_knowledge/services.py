"""Business logic for Quality Knowledge plugin."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .models import KnowledgeDocument, SearchLog


class QualityKnowledgeService:
    """Core service for quality knowledge management and retrieval."""

    def __init__(self, db_session: Session, llm_client: Any = None):
        self.db = db_session
        self.llm = llm_client

    # === Knowledge CRUD ===

    def add_document(self, title: str, content: str, doc_type: str,
                     category: str = "general", tags: Optional[List[str]] = None,
                     source: str = "") -> KnowledgeDocument:
        doc = KnowledgeDocument(
            title=title, content=content, doc_type=doc_type,
            category=category, tags=tags or [], source=source
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def get_document(self, doc_id: int) -> Optional[KnowledgeDocument]:
        return self.db.query(KnowledgeDocument).get(doc_id)

    def update_document(self, doc_id: int, **kwargs) -> Optional[KnowledgeDocument]:
        doc = self.db.query(KnowledgeDocument).get(doc_id)
        if not doc:
            return None
        for k, v in kwargs.items():
            if hasattr(doc, k):
                setattr(doc, k, v)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def delete_document(self, doc_id: int) -> bool:
        doc = self.db.query(KnowledgeDocument).get(doc_id)
        if not doc:
            return False
        self.db.delete(doc)
        self.db.commit()
        return True

    def list_documents(self, doc_type: Optional[str] = None,
                       category: Optional[str] = None,
                       limit: int = 50, offset: int = 0) -> List[KnowledgeDocument]:
        q = self.db.query(KnowledgeDocument)
        if doc_type:
            q = q.filter(KnowledgeDocument.doc_type == doc_type)
        if category:
            q = q.filter(KnowledgeDocument.category == category)
        return q.order_by(KnowledgeDocument.updated_at.desc()).offset(offset).limit(limit).all()

    # === Search ===

    def search(self, query: str, doc_type: Optional[str] = None,
               category: Optional[str] = None,
               limit: int = 10) -> List[KnowledgeDocument]:
        """Keyword-based search across knowledge base."""
        q = self.db.query(KnowledgeDocument)
        search_term = f"%{query}%"
        q = q.filter(or_(
            KnowledgeDocument.title.ilike(search_term),
            KnowledgeDocument.content.ilike(search_term),
        ))
        if doc_type:
            q = q.filter(KnowledgeDocument.doc_type == doc_type)
        if category:
            q = q.filter(KnowledgeDocument.category == category)

        results = q.limit(limit).all()

        # Log search
        log = SearchLog(query=query, results_count=len(results))
        self.db.add(log)
        self.db.commit()

        return results

    def semantic_search(self, query: str, limit: int = 10) -> List[Dict]:
        """Semantic search using LLM-powered relevance ranking.
        Falls back to keyword search if no LLM available."""
        keyword_results = self.search(query, limit=limit * 2)

        if self.llm and keyword_results:
            return self._llm_rerank(query, keyword_results, limit)

        return [{"id": d.id, "title": d.title, "doc_type": d.doc_type,
                 "category": d.category, "snippet": d.content[:200],
                 "relevance": 0.5} for d in keyword_results[:limit]]

    def _llm_rerank(self, query: str, documents: List[KnowledgeDocument],
                    limit: int) -> List[Dict]:
        """Use LLM to re-rank search results by relevance."""
        docs_text = "\n".join([f"[{d.id}] {d.title}: {d.content[:100]}" for d in documents])
        prompt = f"""根据查询"{query}"，从以下文档中选出最相关的{limit}个，按相关性排序。
返回JSON数组：[{{"id": <文档ID>, "relevance": <0-1分数>}}]

文档列表：
{docs_text}"""

        try:
            result = self._call_llm(prompt)
            rankings = json.loads(result)
            id_to_doc = {d.id: d for d in documents}
            ranked = []
            for r in rankings[:limit]:
                doc = id_to_doc.get(r["id"])
                if doc:
                    ranked.append({"id": doc.id, "title": doc.title,
                                   "doc_type": doc.doc_type, "category": doc.category,
                                   "snippet": doc.content[:200], "relevance": r.get("relevance", 0.5)})
            return ranked
        except Exception:
            return [{"id": d.id, "title": d.title, "doc_type": d.doc_type,
                     "category": d.category, "snippet": d.content[:200],
                     "relevance": 0.5} for d in documents[:limit]]

    # === Pre-built Knowledge ===

    def seed_food_safety_standards(self):
        """Seed the knowledge base with core food safety standards info."""
        standards = [
            {"title": "ISO 22000:2018 食品安全管理体系", "doc_type": "standard",
             "category": "iso22000", "content": "ISO 22000:2018是国际标准化组织发布的食品安全管理体系标准，适用于食品链中所有组织。核心要素：1)交互沟通 2)体系管理 3)前提方案(PRP) 4)HACCP原理 5)持续改进。关键条款：4-组织环境、5-领导作用、6-策划、7-支持、8-运行、9-绩效评价、10-改进。",
             "tags": ["ISO", "食品安全", "管理体系"]},
            {"title": "HACCP 七大原理", "doc_type": "standard",
             "category": "haccp", "content": "HACCP（危害分析与关键控制点）七大原理：1)进行危害分析 2)确定关键控制点(CCP) 3)建立关键限值 4)建立CCP监控程序 5)建立纠偏措施 6)建立验证程序 7)建立文件和记录保存制度。适用于所有食品生产企业，是FSSC 22000和ISO 22000的核心组成部分。",
             "tags": ["HACCP", "食品安全", "关键控制点"]},
            {"title": "FSSC 22000 食品安全体系认证", "doc_type": "standard",
             "category": "fssc22000", "content": "FSSC 22000是GFSI（全球食品安全倡议）认可的食品安全认证方案。基于ISO 22000 + ISO/TS 22002-1（食品制造业PRP）+ FSSC附加要求。认证范围覆盖食品制造、动物饲料制造、食品包装材料制造等。被全球主要零售商和食品企业接受。",
             "tags": ["FSSC", "GFSI", "认证"]},
            {"title": "GMP 良好生产规范", "doc_type": "standard",
             "category": "gmp", "content": "GMP（Good Manufacturing Practice）是食品/药品生产的前提条件。食品GMP包括：厂房与设施要求、设备管理、人员卫生、原料管理、生产过程控制、成品管理、文件与记录、自检等。是HACCP体系建立的基础。",
             "tags": ["GMP", "良好生产规范", "前提方案"]},
            {"title": "EU Novel Food 法规 (EU) 2015/2283", "doc_type": "regulation",
             "category": "novel_food", "content": "欧盟新资源食品法规，规定了新资源食品的定义、授权程序和标签要求。新资源食品是指1997年5月15日前在欧盟未显著消费的食品。授权流程：申请→EFSA评估→欧盟委员会决定。嘉必优CABIO-A-2藻油DHA于2024年获得授权。",
             "tags": ["欧盟", "新资源食品", "Novel Food", "EFSA"]},
            {"title": "中国新食品原料审批流程", "doc_type": "regulation",
             "category": "nhc", "content": "国家卫健委负责新食品原料审批。流程：1)申请人提交安全性评估材料 2)卫评中心组织专家评审 3)向社会征求意见 4)公布审批结果。涉及合成生物学来源的新食品原料（如HMOs、燕窝酸等）需额外提供菌种安全性、生产工艺、毒理学试验等材料。",
             "tags": ["国家卫健委", "新食品原料", "审批"]},
            {"title": "偏差管理SOP模板", "doc_type": "sop",
             "category": "deviation", "content": "偏差管理标准操作流程：1)偏差发现与报告（24小时内）2)偏差分类（关键/主要/次要）3)影响评估 4)调查与根本原因分析 5)CAPA制定 6)产品处置决定 7)偏差关闭 8)趋势分析与回顾。关键控制点：偏差发现到关闭不超过30天。",
             "tags": ["SOP", "偏差", "偏差管理"]},
            {"title": "CAPA管理流程", "doc_type": "sop",
             "category": "capa", "content": "CAPA（纠正与预防措施）管理流程：1)识别来源（偏差/投诉/审计/OOS/OOT）2)问题描述与分类 3)根本原因分析（5Why/鱼骨图）4)纠正措施制定与实施 5)预防措施制定与实施 6)有效性验证 7)CAPA关闭 8)管理评审输入。CAPA有效性验证期通常为90天。",
             "tags": ["SOP", "CAPA", "纠正措施", "预防措施"]},
            {"title": "食品召回管理规范", "doc_type": "regulation",
             "category": "recall", "content": "《食品召回管理办法》规定了食品召回的分级管理：一级召回（可能导致严重健康损害）、二级召回（可能导致一般健康损害）、三级召回（标签标识问题等）。召回流程：停止生产→通知经营者和消费者→向监管部门报告→召回产品处置→提交召回总结。",
             "tags": ["召回", "食品安全", "法规"]},
            {"title": "供应商质量管理SOP", "doc_type": "sop",
             "category": "supplier", "content": "供应商质量管理流程：1)供应商资质审核（营业执照/生产许可/体系认证）2)样品检测与评估 3)现场审核 4)供应商评级（A/B/C/D）5)定期复审 6)变更管理 7)不合格供应商处置。关键原料供应商需每年至少一次现场审核。",
             "tags": ["SOP", "供应商管理", "供应商审核"]},
        ]
        for s in standards:
            existing = self.db.query(KnowledgeDocument).filter_by(title=s["title"]).first()
            if not existing:
                self.add_document(**s)
        return len(standards)

    # === Analytics ===

    def get_search_stats(self, days: int = 30) -> Dict:
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        logs = self.db.query(SearchLog).filter(SearchLog.created_at >= cutoff).all()
        queries = [l.query for l in logs]
        from collections import Counter
        top_queries = Counter(queries).most_common(10)
        return {"total_searches": len(logs), "top_queries": top_queries}

    def _call_llm(self, prompt: str) -> str:
        if hasattr(self.llm, "generate"):
            return self.llm.generate(prompt)
        return str(self.llm(prompt))
