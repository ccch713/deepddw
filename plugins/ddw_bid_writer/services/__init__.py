"""DDW 投标标书插件 services 包入口。

C+D+E+F 方案完整链路：
- C: outline_planner / section_writer / consistency_checker / polisher / fact_sheet
- D: knowledge_bootstrap / vector_store / embedding_service
- E: agent_orchestrator
- F: importance_detector
"""

from plugins.ddw_bid_writer.services.agent_orchestrator import (
    AgentOrchestrator,
    AgentRole,
    AgentStep,
)
from plugins.ddw_bid_writer.services.consistency_checker import ConsistencyChecker
from plugins.ddw_bid_writer.services.embedding_service import (
    EmbeddingService,
    SimpleEmbedding,
    get_default_embedding,
)
from plugins.ddw_bid_writer.services.fact_sheet import (
    DateFact,
    FactSheet,
    MetricFact,
    PersonnelFact,
    extract_dates,
    extract_metrics,
    extract_personnel,
    fact_sheet_from_dict,
)
from plugins.ddw_bid_writer.services.generate_service import GenerateService
from plugins.ddw_bid_writer.services.importance_detector import (
    ImportanceAssessment,
    ImportanceDetector,
    ImportanceLevel,
)
from plugins.ddw_bid_writer.services.knowledge_bootstrap import (
    KnowledgeBootstrap,
    chunk_text,
    parse_file,
)
from plugins.ddw_bid_writer.services.mcp_client import MCPClient, get_mcp_client
from plugins.ddw_bid_writer.services.outline_planner import OutlinePlanner
from plugins.ddw_bid_writer.services.polisher import Polisher
from plugins.ddw_bid_writer.services.review_service import ReviewService
from plugins.ddw_bid_writer.services.section_writer import SectionWriter
from plugins.ddw_bid_writer.services.style_service import StyleService
from plugins.ddw_bid_writer.services.template_service import TemplateService
from plugins.ddw_bid_writer.services.vector_store import (
    TenantKnowledgeStore,
    VectorStore,
)

__all__ = [
    "AgentOrchestrator",
    "AgentRole",
    "AgentStep",
    "ConsistencyChecker",
    "DateFact",
    "EmbeddingService",
    "FactSheet",
    "GenerateService",
    "ImportanceAssessment",
    "ImportanceDetector",
    "ImportanceLevel",
    "KnowledgeBootstrap",
    "MCPClient",
    "MetricFact",
    "OutlinePlanner",
    "PersonnelFact",
    "Polisher",
    "ReviewService",
    "SectionWriter",
    "SimpleEmbedding",
    "StyleService",
    "TemplateService",
    "TenantKnowledgeStore",
    "VectorStore",
    "chunk_text",
    "extract_dates",
    "extract_metrics",
    "extract_personnel",
    "fact_sheet_from_dict",
    "get_default_embedding",
    "get_mcp_client",
    "parse_file",
]
