"""Tests for ddw-esg-knowledge plugin."""

import os
import sys
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure parent dir is on path for imports
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)  # noqa: E402

# Import using absolute module path (plugins is a package, pytest.ini sets pythonpath=.)
from plugins.ddw_esg_knowledge.importer import chunk_text, import_markdown  # noqa: E402
from plugins.ddw_esg_knowledge.routes import _reset_db, router  # noqa: E402
from plugins.ddw_esg_knowledge.search import compute_tsvector, cosine_similarity, keyword_search  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset():
    """Reset in-memory DB before each test."""
    _reset_db()
    yield
    _reset_db()


@pytest.fixture
def app():
    """Create a FastAPI app with the plugin router."""
    _app = FastAPI()
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health & Stats
# ---------------------------------------------------------------------------


def test_health_check(client):
    """Test health check endpoint."""
    resp = client.get("/api/v1/plugins/ddw-esg-knowledge/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["plugin"] == "ddw-esg-knowledge"


def test_stats_empty(client):
    """Test stats with empty DB."""
    resp = client.get("/api/v1/plugins/ddw-esg-knowledge/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_documents"] == 0
    assert data["total_chunks"] == 0
    assert data["total_customers"] == 0


# ---------------------------------------------------------------------------
# Document CRUD
# ---------------------------------------------------------------------------


def test_create_document(client):
    """Test creating a document with inline content."""
    resp = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={
            "title": "GRI Standards Overview",
            "framework": "GRI",
            "doc_type": "standard",
            "content": "Global Reporting Initiative (GRI) provides standards for sustainability reporting. "
            "GRI standards help organizations understand and communicate their impact.",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "GRI Standards Overview"
    assert data["framework"] == "GRI"
    assert data["status"] == "ready"
    assert data["chunk_count"] >= 1


def test_list_documents(client):
    """Test listing documents with pagination."""
    # Create 3 documents
    for i in range(3):
        client.post(
            "/api/v1/plugins/ddw-esg-knowledge/documents",
            json={"title": f"Doc {i}", "framework": "GRI" if i % 2 == 0 else "TCFD"},
        )
    resp = client.get("/api/v1/plugins/ddw-esg-knowledge/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3

    # Test pagination
    resp = client.get("/api/v1/plugins/ddw-esg-knowledge/documents?page_size=2")
    data = resp.json()
    assert len(data) == 2

    # Test framework filter
    resp = client.get("/api/v1/plugins/ddw-esg-knowledge/documents?framework=GRI")
    data = resp.json()
    assert len(data) == 2


def test_get_document(client):
    """Test getting a single document."""
    create_resp = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={"title": "TCFD Guide", "framework": "TCFD"},
    )
    doc_id = create_resp.json()["id"]
    resp = client.get(f"/api/v1/plugins/ddw-esg-knowledge/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "TCFD Guide"


def test_update_document(client):
    """Test updating document metadata."""
    create_resp = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={"title": "Old Title", "framework": "GRI"},
    )
    doc_id = create_resp.json()["id"]
    resp = client.put(
        f"/api/v1/plugins/ddw-esg-knowledge/documents/{doc_id}",
        json={"title": "New Title", "summary": "Updated summary"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "New Title"
    assert resp.json()["summary"] == "Updated summary"


def test_delete_document(client):
    """Test deleting a document and its chunks."""
    create_resp = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={"title": "To Delete", "content": "Some content to chunk."},
    )
    doc_id = create_resp.json()["id"]
    resp = client.delete(f"/api/v1/plugins/ddw-esg-knowledge/documents/{doc_id}")
    assert resp.status_code == 204
    # Verify deleted
    resp = client.get(f"/api/v1/plugins/ddw-esg-knowledge/documents/{doc_id}")
    assert resp.status_code == 404


def test_reindex_document(client):
    """Test reindexing a document."""
    create_resp = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={"title": "Reindex Me", "content": "Content for reindexing test."},
    )
    doc_id = create_resp.json()["id"]
    resp = client.post(f"/api/v1/plugins/ddw-esg-knowledge/documents/{doc_id}/reindex")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_list_document_chunks(client):
    """Test listing chunks for a document."""
    create_resp = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={"title": "Chunked Doc", "content": "This is chunk content for testing. " * 20},
    )
    doc_id = create_resp.json()["id"]
    resp = client.get(f"/api/v1/plugins/ddw-esg-knowledge/documents/{doc_id}/chunks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(c["doc_id"] == doc_id for c in data)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_keyword_search(client):
    """Test keyword search."""
    client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={
            "title": "ESG Disclosure Requirements",
            "content": "Environmental Social and Governance (ESG) disclosure requirements "
            "are becoming mandatory for listed companies worldwide.",
        },
    )
    resp = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/search/keyword",
        json={"query": "ESG disclosure requirements"},
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert results[0]["match_type"] == "keyword"
    assert results[0]["score"] > 0


def test_hybrid_search(client):
    """Test hybrid search combines keyword and semantic."""
    client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={
            "title": "Carbon Neutrality Guide",
            "content": "Carbon neutrality means achieving net-zero carbon emissions. "
            "Companies must reduce emissions and offset remaining output.",
        },
    )
    resp = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/search/hybrid",
        json={
            "query": "carbon neutrality",
            "query_embedding": [0.1] * 10,  # mock embedding
        },
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert results[0]["match_type"] == "hybrid"


# ---------------------------------------------------------------------------
# Customer CRUD & Isolation
# ---------------------------------------------------------------------------


def test_create_customer(client):
    """Test creating a customer."""
    resp = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/customers",
        json={
            "name": "Test Corp",
            "industry": "Manufacturing",
            "scale": "大型",
            "tags": ["esg", "manufacturing"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Corp"
    assert data["industry"] == "Manufacturing"
    assert data["tags"] == ["esg", "manufacturing"]


def test_customer_isolation(client):
    """Test multi-tenant isolation: search scoped by customer_id."""
    # Create two customers
    c1 = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/customers",
        json={"name": "Customer A"},
    ).json()
    c2 = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/customers",
        json={"name": "Customer B"},
    ).json()

    # Create docs for each customer
    client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={
            "title": "Doc A",
            "customer_id": c1["id"],
            "content": "This document belongs to customer A and discusses ESG governance.",
        },
    )
    client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={
            "title": "Doc B",
            "customer_id": c2["id"],
            "content": "This document belongs to customer B and discusses environmental standards.",
        },
    )

    # Search scoped to customer A
    resp = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/search/keyword",
        json={"query": "ESG governance", "customer_id": c1["id"]},
    )
    results = resp.json()
    # Should only find doc A
    for r in results:
        assert r["customer_id"] == c1["id"]


def test_customer_documents(client):
    """Test listing documents for a specific customer."""
    c = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/customers",
        json={"name": "My Customer"},
    ).json()
    client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={"title": "Cust Doc", "customer_id": c["id"], "content": "Customer specific content."},
    )
    resp = client.get(f"/api/v1/plugins/ddw-esg-knowledge/customers/{c['id']}/documents")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["customer_id"] == c["id"]


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------


def test_rag_retrieve(client):
    """Test RAG retrieval endpoint."""
    client.post(
        "/api/v1/plugins/ddw-esg-knowledge/documents",
        json={
            "title": "GRI Materiality Assessment",
            "content": "A materiality assessment identifies the most significant ESG issues "
            "for an organization and its stakeholders. It involves mapping environmental, "
            "social, and governance topics against business impact and stakeholder interest.",
        },
    )
    resp = client.post(
        "/api/v1/plugins/ddw-esg-knowledge/rag/retrieve",
        json={"question": "What is a materiality assessment?", "top_k": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "context" in data
    assert "total_tokens" in data
    assert len(data["context"]) >= 1


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def test_import_markdown():
    """Test markdown file import."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("# ESG Overview\n\n")
        f.write("ESG stands for Environmental, Social, and Governance.\n\n")
        f.write("## Environmental\n\n")
        f.write("Environmental factors include climate change, biodiversity, and pollution.\n\n")
        f.write("## Social\n\n")
        f.write("Social factors include labor practices, human rights, and community impact.\n")
        tmp_path = f.name

    try:
        result = import_markdown(tmp_path)
        assert result["title"] == os.path.basename(tmp_path).replace(".md", "")
        assert result["chunk_count"] >= 1
        assert len(result["text"]) > 0
    finally:
        os.unlink(tmp_path)


def test_chunk_text():
    """Test text chunking with overlap."""
    # Use paragraphs separated by \n\n for proper chunking
    para = "This is a test paragraph with enough words to create multiple chunks. "
    text = (para + "\n\n") * 10
    chunks = chunk_text(text, chunk_size=200, overlap=20)
    assert len(chunks) >= 2
    for c in chunks:
        assert "text" in c
        assert "token_count" in c
        assert c["token_count"] > 0


def test_chunk_text_short():
    """Test chunking short text produces single chunk."""
    text = "Short text."
    chunks = chunk_text(text, chunk_size=512, overlap=128)
    assert len(chunks) == 1
    assert chunks[0]["text"] == "Short text."


# ---------------------------------------------------------------------------
# Search utilities (unit tests)
# ---------------------------------------------------------------------------


def test_compute_tsvector():
    """Test tsvector computation with Chinese and English."""
    result = compute_tsvector("Hello World 你好世界")
    tokens = result.split()
    assert "hello" in tokens
    assert "world" in tokens
    # Chinese characters are grouped as single tokens by regex
    assert "你好世界" in tokens


def test_cosine_similarity():
    """Test cosine similarity calculation."""
    # Identical vectors
    assert cosine_similarity([1, 0, 0], [1, 0, 0]) == 1.0
    # Orthogonal vectors
    assert cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0
    # Empty vectors
    assert cosine_similarity([], []) == 0.0
    # Different lengths
    assert cosine_similarity([1, 0], [1, 0, 0]) == 0.0


def test_keyword_search_function():
    """Test keyword_search function directly."""
    chunks = [
        {"id": "1", "text": "ESG governance", "tsvector": "esg governance", "token_count": 2},
        {"id": "2", "text": "Financial reporting", "tsvector": "financial reporting", "token_count": 2},
        {"id": "3", "text": "ESG environmental", "tsvector": "esg environmental", "token_count": 2},
    ]
    results = keyword_search("ESG", chunks, top_k=10)
    assert len(results) == 2  # chunks 1 and 3 match
    assert all(r["score"] > 0 for r in results)
    assert results[0]["score"] >= results[1]["score"]
