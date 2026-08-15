"""API routes for the ESG chatbot plugin.

Endpoints:
  POST   /chat                          — Send message, get AI reply
  POST   /chat/stream                   — SSE streaming version (stub)
  POST   /sessions                      — Create session
  GET    /sessions/{session_id}         — Session detail
  GET    /sessions                      — List user sessions
  PUT    /sessions/{session_id}/close   — Close session
  GET    /sessions/{session_id}/messages — Message history
  GET    /history/search                — Search chat history
  POST   /escalate                      — Request human handoff
  GET    /escalate/{escalation_id}      — Escalation status
  PUT    /escalate/{escalation_id}/resolve — Resolve escalation
  POST   /knowledge/reindex             — Trigger reindex (stub)
  GET    /knowledge/stats               — Knowledge base stats
  GET    /health                        — Health check
"""

from conversation import ConversationManager
from escalation import EscalationManager
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from llm_client import LLMClient
from models import (
    ChatRequest,
    ChatResponse,
    EscalationRequest,
    EscalationResponse,
    HealthResponse,
    KnowledgeStats,
    MessageResponse,
    SessionCreate,
    SessionResponse,
)
from rag_pipeline import RAGPipeline

router = APIRouter()

# ------------------------------------------------------------------
# Singletons (module-level; replaced in tests)
# ------------------------------------------------------------------
_conversation = ConversationManager()
_escalation = EscalationManager()
_rag = RAGPipeline()
_llm = LLMClient()

# ------------------------------------------------------------------
# Chat
# ------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def send_message(req: ChatRequest):
    """Send a user message and receive an AI-generated reply via RAG."""
    # Ensure session exists
    session = _conversation.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {req.session_id} not found")

    # Store user message
    _conversation.add_message(req.session_id, "user", req.message)

    # RAG pipeline: retrieve → generate
    history = _conversation.get_history(req.session_id, limit=6)
    context = await _rag.retrieve(req.message, customer_id=req.user_id)
    result = await _rag.generate(req.message, context, conversation_history=history)

    # Store assistant message
    msg = _conversation.add_message(
        req.session_id,
        "assistant",
        result["reply"],
        confidence=result["confidence"],
        sources=context,
        tokens_prompt=result["tokens_used"].get("prompt"),
        tokens_completion=result["tokens_used"].get("completion"),
        model=result["tokens_used"].get("model"),
    )

    # Check escalation
    should_esc = await _rag.should_escalate(result["confidence"], req.message)

    return ChatResponse(
        session_id=req.session_id,
        message_id=msg["id"],
        reply=result["reply"],
        confidence=result["confidence"],
        sources=context,
        tokens_used=result["tokens_used"],
        should_escalate=should_esc,
    )


@router.post("/chat/stream")
async def send_message_stream(req: ChatRequest):
    """Simplified SSE streaming endpoint (stub)."""
    session = _conversation.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {req.session_id} not found")

    _conversation.add_message(req.session_id, "user", req.message)

    history = _conversation.get_history(req.session_id, limit=6)
    context = await _rag.retrieve(req.message, customer_id=req.user_id)
    result = await _rag.generate(req.message, context, conversation_history=history)

    _conversation.add_message(
        req.session_id, "assistant", result["reply"],
        confidence=result["confidence"], sources=context,
        tokens_prompt=result["tokens_used"].get("prompt"),
        tokens_completion=result["tokens_used"].get("completion"),
        model=result["tokens_used"].get("model"),
    )

    async def event_stream():
        yield f'data: {{"reply": "{result["reply"]}", "done": true}}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ------------------------------------------------------------------
# Sessions
# ------------------------------------------------------------------


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(req: SessionCreate):
    """Create a new chat session."""
    session = _conversation.create_session(
        user_id=req.user_id,
        topic=req.topic,
        metadata=req.metadata,
        company_id=req.company_id,
    )
    return SessionResponse(**session)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session details."""
    session = _conversation.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return SessionResponse(**session)


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    user_id: str = Query(default=None),
    status: str = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List sessions, optionally filtered by user_id and status."""
    return [
        SessionResponse(**s)
        for s in _conversation.list_sessions(user_id=user_id, status=status, limit=limit)
    ]


@router.put("/sessions/{session_id}/close", response_model=SessionResponse)
async def close_session(session_id: str):
    """Close a chat session."""
    session = _conversation.close_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return SessionResponse(**session)


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[MessageResponse],
)
async def get_messages(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=500),
):
    """Get message history for a session."""
    session = _conversation.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    msgs = _conversation.get_history(session_id, limit=limit)
    return [MessageResponse(**m) for m in msgs]


# ------------------------------------------------------------------
# History search
# ------------------------------------------------------------------


@router.get("/history/search", response_model=list[MessageResponse])
async def search_history(
    user_id: str = Query(default=None),
    keyword: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=200),
):
    """Search chat history across sessions."""
    msgs = _conversation.search_history(user_id=user_id, keyword=keyword, limit=limit)
    return [MessageResponse(**m) for m in msgs]


# ------------------------------------------------------------------
# Escalation
# ------------------------------------------------------------------


@router.post("/escalate", response_model=EscalationResponse, status_code=201)
async def create_escalation(req: EscalationRequest):
    """Request human handoff for a chat session."""
    session = _conversation.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {req.session_id} not found")

    context_summary = _conversation.get_context_summary(req.session_id)

    # Mark session as escalated
    _conversation.sessions[req.session_id]["status"] = "escalated"

    esc = _escalation.create_escalation(
        session_id=req.session_id,
        reason=req.reason,
        priority=req.priority,
        contact_info=req.contact_info,
        context_summary=context_summary,
    )
    return EscalationResponse(**esc)


@router.get("/escalate/{escalation_id}", response_model=EscalationResponse)
async def get_escalation(escalation_id: str):
    """Get escalation status."""
    esc = _escalation.get_escalation(escalation_id)
    if not esc:
        raise HTTPException(status_code=404, detail=f"Escalation {escalation_id} not found")
    return EscalationResponse(**esc)


@router.put("/escalate/{escalation_id}/resolve", response_model=EscalationResponse)
async def resolve_escalation(escalation_id: str):
    """Resolve an escalation."""
    esc = _escalation.resolve(escalation_id)
    if not esc:
        raise HTTPException(status_code=404, detail=f"Escalation {escalation_id} not found")
    return EscalationResponse(**esc)


# ------------------------------------------------------------------
# Knowledge base
# ------------------------------------------------------------------


@router.post("/knowledge/reindex")
async def knowledge_reindex():
    """Trigger a knowledge base reindex (stub)."""
    return {"status": "ok", "message": "Reindex queued (stub)"}


@router.get("/knowledge/stats", response_model=KnowledgeStats)
async def knowledge_stats():
    """Get knowledge base statistics."""
    return KnowledgeStats(
        total_documents=0,
        total_chunks=0,
        last_indexed=None,
    )


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    llm_ok = await _llm.health_check()
    return HealthResponse(
        status="ok" if llm_ok else "degraded",
        llm_gateway=llm_ok,
        knowledge_base=True,
        version="1.0.0",
    )
