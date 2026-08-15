"""Tests for the ddw-esg-chatbot plugin.

Uses in-memory storage (ConversationManager / EscalationManager)
and the FastAPI TestClient for API-level tests.
"""

# Modules imported after conftest.py sets up sys.path
import models as _models  # noqa: F401, E402, E501
import pytest  # noqa: E402
from conversation import ConversationManager  # noqa: F401, E402
from escalation import EscalationManager  # noqa: F401, E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from rag_pipeline import RAGPipeline  # noqa: E402
from plugins.ddw_esg_chatbot.routes import _conversation, _escalation, router  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_state():
    """Reset in-memory managers before each test."""
    _conversation.sessions.clear()
    _conversation.messages.clear()
    _escalation.escalations.clear()
    yield
    _conversation.sessions.clear()
    _conversation.messages.clear()
    _escalation.escalations.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _create_session(client: TestClient, user_id: str = "u1") -> dict:
    resp = client.post("/sessions", json={"user_id": user_id, "topic": "test"})
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["llm_gateway"] is True
        assert data["version"] == "1.0.0"


class TestSessions:
    def test_create_session(self, client):
        data = _create_session(client)
        assert data["user_id"] == "u1"
        assert data["status"] == "active"
        assert data["message_count"] == 0
        assert "id" in data

    def test_get_session(self, client):
        s = _create_session(client)
        resp = client.get(f"/sessions/{s['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == s["id"]

    def test_get_session_not_found(self, client):
        resp = client.get("/sessions/nonexistent")
        assert resp.status_code == 404

    def test_list_sessions(self, client):
        _create_session(client, "u1")
        _create_session(client, "u2")
        resp = client.get("/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_sessions_filter_user(self, client):
        _create_session(client, "u1")
        _create_session(client, "u2")
        resp = client.get("/sessions?user_id=u1")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_close_session(self, client):
        s = _create_session(client)
        resp = client.put(f"/sessions/{s['id']}/close")
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"


class TestChat:
    def test_send_message(self, client):
        s = _create_session(client)
        resp = client.post(
            "/chat",
            json={
                "session_id": s["id"],
                "message": "什么是ESG?",
                "user_id": "u1",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == s["id"]
        assert len(data["reply"]) > 0
        assert data["confidence"] > 0
        assert "message_id" in data

    def test_chat_flow(self, client):
        """Multi-turn conversation test."""
        s = _create_session(client)

        # Turn 1
        r1 = client.post(
            "/chat",
            json={"session_id": s["id"], "message": "ESG是什么意思？", "user_id": "u1"},
        )
        assert r1.status_code == 200

        # Turn 2
        r2 = client.post(
            "/chat",
            json={"session_id": s["id"], "message": "有哪些评级机构？", "user_id": "u1"},
        )
        assert r2.status_code == 200

        # Verify history
        msgs = client.get(f"/sessions/{s['id']}/messages").json()
        # 2 user + 2 assistant = 4
        assert len(msgs) == 4

    def test_chat_session_not_found(self, client):
        resp = client.post(
            "/chat",
            json={"session_id": "nonexistent", "message": "hi"},
        )
        assert resp.status_code == 404


class TestMessages:
    def test_session_history(self, client):
        s = _create_session(client)
        client.post(
            "/chat",
            json={"session_id": s["id"], "message": "hello", "user_id": "u1"},
        )
        resp = client.get(f"/sessions/{s['id']}/messages")
        assert resp.status_code == 200
        msgs = resp.json()
        assert len(msgs) >= 2  # user + assistant

    def test_search_history(self, client):
        s = _create_session(client)
        client.post(
            "/chat",
            json={"session_id": s["id"], "message": "ESG评级标准", "user_id": "u1"},
        )
        resp = client.get("/history/search?keyword=ESG评级")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestEscalation:
    def test_escalation_flow(self, client):
        s = _create_session(client)
        # Create escalation
        resp = client.post(
            "/escalate",
            json={
                "session_id": s["id"],
                "reason": "Complex question about ESG compliance",
                "priority": "high",
                "contact_info": {"phone": "13800138000"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["priority"] == "high"
        assert "context_summary" in data

        # Session should be marked as escalated
        session_resp = client.get(f"/sessions/{s['id']}")
        assert session_resp.json()["status"] == "escalated"

    def test_escalation_resolve(self, client):
        s = _create_session(client)
        # Create
        r1 = client.post(
            "/escalate",
            json={"session_id": s["id"], "reason": "Need expert"},
        )
        esc_id = r1.json()["id"]

        # Resolve
        r2 = client.put(f"/escalate/{esc_id}/resolve")
        assert r2.status_code == 200
        assert r2.json()["status"] == "resolved"
        assert r2.json()["resolved_at"] is not None

    def test_escalation_not_found(self, client):
        resp = client.get("/escalate/nonexistent")
        assert resp.status_code == 404


class TestKnowledge:
    def test_knowledge_stats(self, client):
        resp = client.get("/knowledge/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_documents" in data
        assert "total_chunks" in data

    def test_knowledge_reindex(self, client):
        resp = client.post("/knowledge/reindex")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestRAGPipeline:
    @pytest.mark.asyncio
    async def test_retrieve(self):
        rag = RAGPipeline()
        chunks = await rag.retrieve("test question")
        assert len(chunks) > 0
        assert chunks[0]["score"] > 0

    @pytest.mark.asyncio
    async def test_generate(self):
        rag = RAGPipeline()
        context = [{"source": "test", "text": "context", "score": 0.9}]
        result = await rag.generate("test question", context)
        assert "reply" in result
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_should_escalate_low_confidence(self):
        rag = RAGPipeline()
        assert await rag.should_escalate(0.3, "random question") is True

    @pytest.mark.asyncio
    async def test_should_escalate_keyword(self):
        rag = RAGPipeline()
        assert await rag.should_escalate(0.9, "转人工客服") is True

    @pytest.mark.asyncio
    async def test_should_not_escalate(self):
        rag = RAGPipeline()
        assert await rag.should_escalate(0.9, "ESG是什么？") is False
