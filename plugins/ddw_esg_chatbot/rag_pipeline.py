"""RAG pipeline for the ESG chatbot.

Retrieves relevant knowledge chunks from the ESG knowledge base plugin
and generates answers using the DDW Gateway LLM.
"""

from typing import Optional

from llm_client import LLMClient


class RAGPipeline:
    """RAG pipeline for ESG chatbot.

    1. Retrieve relevant chunks from esg-knowledge plugin.
    2. Build a prompt with system instructions + context + conversation history.
    3. Generate an answer via LLM.
    4. Determine if human escalation is needed.
    """

    ESCALATION_KEYWORDS = [
        "转人工",
        "找专家",
        "人工客服",
        "speak to human",
        "真人客服",
        "转接人工",
    ]

    def __init__(
        self,
        knowledge_base_url: str = (
            "http://localhost:8000/api/v1/plugins/ddw-esg-knowledge"
        ),
        llm_client: Optional[LLMClient] = None,
    ):
        self.kb_url = knowledge_base_url
        self.llm = llm_client or LLMClient()
        self.system_prompt = (
            "你是 ESG 专项 AI 客服，专注于帮助企业理解和改善 ESG（环境、社会、治理）表现。\n"
            "你拥有以下能力：\n"
            "1. ESG 基础概念解释\n"
            "2. 16 家评级机构的评级方式和指标解读\n"
            "3. ESG 政策法规跟踪和解读\n"
            "4. 评估结果分析和改进建议\n"
            "5. 行业最佳实践推荐\n\n"
            "回答要求：\n"
            "- 基于知识库中的权威来源回答\n"
            "- 引用具体标准或政策编号\n"
            "- 给出可操作的建议\n"
            "- 如果不确定，明确告知并建议人工咨询"
        )

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        question: str,
        customer_id: Optional[str] = None,
    ) -> list[dict]:
        """Retrieve relevant knowledge chunks from the ESG knowledge base.

        In production this calls the ddw-esg-knowledge plugin API.
        Returns a list of dicts with keys: chunk_id, doc_title, text, score, source.
        """
        # Stub: return mock retrieval results
        return [
            {
                "chunk_id": "mock_chunk_001",
                "doc_title": "ESG知识库",
                "text": f'关于 "{question}" 的相关知识...',
                "score": 0.85,
                "source": "ESG知识库",
            }
        ]

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    async def generate(
        self,
        question: str,
        context: list[dict],
        conversation_history: Optional[list[dict]] = None,
    ) -> dict:
        """Generate an answer using the LLM with RAG context.

        Returns dict with keys: reply, confidence, tokens_used.
        """
        context_text = "\n\n".join(
            f'[{c["source"]}] {c["text"]}' for c in context
        )

        history_text = ""
        if conversation_history:
            history_text = "\n".join(
                f'{m["role"]}: {m["content"]}'
                for m in conversation_history[-6:]
            )

        prompt = (
            f"{self.system_prompt}\n\n"
            f"参考资料：\n{context_text}\n\n"
            f"对话历史：\n{history_text}\n\n"
            f"用户问题：{question}\n\n"
            "请基于以上信息回答："
        )

        messages = [{"role": "user", "content": prompt}]
        result = await self.llm.chat(messages)

        # Compute confidence from retrieval scores
        confidence = (
            max(c.get("score", 0) for c in context) if context else 0.5
        )

        return {
            "reply": result["content"],
            "confidence": round(confidence, 2),
            "tokens_used": {
                "prompt": result["usage"].get("prompt_tokens", 0),
                "completion": result["usage"].get("completion_tokens", 0),
                "model": result.get("model", "unknown"),
            },
        }

    # ------------------------------------------------------------------
    # Escalation check
    # ------------------------------------------------------------------

    async def should_escalate(
        self,
        confidence: float,
        question: str,
    ) -> bool:
        """Determine if the query should be escalated to a human agent.

        Escalation is triggered when:
        1. Confidence is below the 0.6 threshold, OR
        2. The user explicitly requests a human agent.
        """
        if confidence < 0.6:
            return True
        lower = question.lower()
        return any(kw in lower for kw in self.ESCALATION_KEYWORDS)
