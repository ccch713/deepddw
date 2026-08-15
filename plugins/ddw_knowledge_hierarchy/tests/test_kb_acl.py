"""Tests for Knowledge Base three-layer ACL (company / department / personal).

Covers:
  1. test_company_kb_visible_to_all — owner/dept_admin/member can see company KB
  2. test_department_kb_isolation — dept A members can't see dept B KB
  3. test_personal_kb_only_owner — personal KB visible only to creator
  4. test_kb_create_and_visibility_filter — list endpoint filters by ACL
  5. test_document_upload_and_delete_with_acl — manage permission enforced
  6. test_cross_scope_search_filter — search scopes return correct results
  7. test_member_cannot_manage_company_kb — member 403 on upload to company KB
  8. test_kb_delete_owner_only — delete permission enforced
"""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("DDW_JWT_SECRET", "test-secret-key-for-testing-32bytes-ok")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.ddw_knowledge_hierarchy import models as kh_models
from plugins.ddw_knowledge_hierarchy.acl import Principal
from plugins.ddw_knowledge_hierarchy.kb_router import router as kb_router


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Set up isolated SQLite + test principal context."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    db_file = tmp_path / "kb_test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        poolclass=NullPool,
    )

    async def _create_all():
        async with engine.begin() as conn:
            await conn.run_sync(kh_models.Base.metadata.create_all)

    asyncio.run(_create_all())

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def _fake_scope():
        async with maker() as s:
            try:
                yield s
            except Exception:
                await s.rollback()
                raise

    import plugins.ddw_knowledge_hierarchy.kb_router as kb_router_module

    monkeypatch.setattr(kb_router_module, "session_scope", _fake_scope)

    app = FastAPI()
    app.include_router(kb_router)
    with TestClient(app) as c:
        yield c

    asyncio.run(engine.dispose())


def _set_principal(monkeypatch, principal: Principal):
    """Set the principal context for the current test via ContextVar."""
    from plugins.ddw_knowledge_hierarchy.deps import set_principal_context

    set_principal_context(principal)


# --- Principals ---

OWNER = Principal(user_id=1, tenant_id=1, role="owner", department_id=10)
DEPT_ADMIN_A = Principal(user_id=2, tenant_id=1, role="dept_admin", department_id=10)
MEMBER_A = Principal(user_id=3, tenant_id=1, role="member", department_id=10)
MEMBER_B = Principal(user_id=4, tenant_id=1, role="member", department_id=20)
OTHER_TENANT = Principal(user_id=5, tenant_id=2, role="owner", department_id=10)


def _create_kb(client, name, scope, **kwargs):
    """Helper: create a KB and return the response JSON."""
    resp = client.post(
        "/kb",
        json={"name": name, "scope": scope, **kwargs},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_pdf(text: str = "test content") -> bytes:
    """生成合法的最小 PDF（PyMuPDF 可解析），避免假 PDF 字节导致解析失败。"""
    import fitz  # PyMuPDF

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


# ---------------------------------------------------------------------------
# Test 1: company KB visible to all
# ---------------------------------------------------------------------------


def test_company_kb_visible_to_all(client, monkeypatch):
    """owner, dept_admin, and member in the same tenant can all see a company KB."""
    _set_principal(monkeypatch, OWNER)
    kb = _create_kb(client, "公司公共库", "company")
    kb_id = kb["id"]

    for p in [OWNER, DEPT_ADMIN_A, MEMBER_A, MEMBER_B]:
        _set_principal(monkeypatch, p)
        resp = client.get(f"/kb/{kb_id}")
        assert resp.status_code == 200, f"{p.role} should see company KB"


# ---------------------------------------------------------------------------
# Test 2: department KB isolation
# ---------------------------------------------------------------------------


def test_department_kb_isolation(client, monkeypatch):
    """Members of dept A cannot see dept B KB, and vice versa."""
    _set_principal(monkeypatch, DEPT_ADMIN_A)
    kb_a = _create_kb(client, "A部门库", "department", department_id=10)
    kb_a_id = kb_a["id"]

    _set_principal(monkeypatch, MEMBER_B)
    kb_b = _create_kb(client, "B部门库", "department", department_id=20)
    kb_b_id = kb_b["id"]

    # MEMBER_A (dept 10) can see A's KB but not B's
    _set_principal(monkeypatch, MEMBER_A)
    assert client.get(f"/kb/{kb_a_id}").status_code == 200
    assert client.get(f"/kb/{kb_b_id}").status_code == 403

    # MEMBER_B (dept 20) can see B's KB but not A's
    _set_principal(monkeypatch, MEMBER_B)
    assert client.get(f"/kb/{kb_b_id}").status_code == 200
    assert client.get(f"/kb/{kb_a_id}").status_code == 403


# ---------------------------------------------------------------------------
# Test 3: personal KB only owner
# ---------------------------------------------------------------------------


def test_personal_kb_only_owner(client, monkeypatch):
    """Personal KB is visible only to the creator."""
    _set_principal(monkeypatch, MEMBER_A)
    kb = _create_kb(client, "我的笔记", "personal", scope_id=MEMBER_A.user_id)
    kb_id = kb["id"]

    # Owner can see
    _set_principal(monkeypatch, MEMBER_A)
    assert client.get(f"/kb/{kb_id}").status_code == 200

    # Other member cannot
    _set_principal(monkeypatch, MEMBER_B)
    assert client.get(f"/kb/{kb_id}").status_code == 403

    # Different tenant cannot
    _set_principal(monkeypatch, OTHER_TENANT)
    assert client.get(f"/kb/{kb_id}").status_code == 403


# ---------------------------------------------------------------------------
# Test 4: create + list visibility filter
# ---------------------------------------------------------------------------


def test_kb_create_and_visibility_filter(client, monkeypatch):
    """List endpoint returns only KBs the principal can view."""
    # Create one of each scope
    _set_principal(monkeypatch, OWNER)
    _create_kb(client, "公司库", "company")
    _create_kb(client, "A部门库", "department", department_id=10)
    _create_kb(client, "个人库", "personal", scope_id=OWNER.user_id)

    # MEMBER_A sees company + dept A (2)
    _set_principal(monkeypatch, MEMBER_A)
    resp = client.get("/kb")
    assert resp.status_code == 200
    names = {kb["name"] for kb in resp.json()}
    assert "公司库" in names
    assert "A部门库" in names
    assert "个人库" not in names

    # MEMBER_B sees only company (1)
    _set_principal(monkeypatch, MEMBER_B)
    resp = client.get("/kb")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "公司库"


# ---------------------------------------------------------------------------
# Test 5: document upload / delete with ACL
# ---------------------------------------------------------------------------


def test_document_upload_and_delete_with_acl(client, monkeypatch):
    """Uploading a document requires manage permission; non-managers get 403."""
    _set_principal(monkeypatch, OWNER)
    kb = _create_kb(client, "公司库", "company")
    kb_id = kb["id"]

    # Owner can upload
    _set_principal(monkeypatch, OWNER)
    resp = client.post(
        f"/kb/{kb_id}/documents",
        files={"file": ("test.pdf", _make_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    # Member cannot upload to company KB
    _set_principal(monkeypatch, MEMBER_A)
    resp = client.post(
        f"/kb/{kb_id}/documents",
        files={"file": ("bad.pdf", _make_pdf("nope"), "application/pdf")},
    )
    assert resp.status_code == 403

    # Owner can delete
    _set_principal(monkeypatch, OWNER)
    resp = client.delete(f"/kb/{kb_id}/documents/{doc_id}")
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Test 6: cross-scope search filter
# ---------------------------------------------------------------------------


def test_cross_scope_search_filter(client, monkeypatch):
    """Search respects ACL scopes — returns only results from visible KBs."""
    _set_principal(monkeypatch, OWNER)
    _create_kb(client, "公司库", "company")
    kb_dept = _create_kb(client, "A部门库", "department", department_id=10)
    kb_personal = _create_kb(client, "个人库", "personal", scope_id=OWNER.user_id)

    # Upload a doc to each
    client.post(
        f"/kb/{kb_dept['id']}/documents",
        files={"file": ("dept_doc.pdf", _make_pdf("dept"), "application/pdf")},
    )
    client.post(
        f"/kb/{kb_personal['id']}/documents",
        files={"file": ("personal_doc.pdf", _make_pdf("personal"), "application/pdf")},
    )

    # MEMBER_A sees company + dept scopes
    _set_principal(monkeypatch, MEMBER_A)
    resp = client.post(
        "/kb/search",
        json={"query": "test", "scopes": ["company", "department"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    kb_ids_in_results = {r["kb_id"] for r in data["results"]}
    assert kb_personal["id"] not in kb_ids_in_results

    # OWNER sees all scopes
    _set_principal(monkeypatch, OWNER)
    resp = client.post(
        "/kb/search",
        json={"query": "test", "scopes": ["company", "department", "personal"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2


# ---------------------------------------------------------------------------
# Test 7: member cannot manage company KB
# ---------------------------------------------------------------------------


def test_member_cannot_manage_company_kb(client, monkeypatch):
    """A regular member gets 403 when trying to upload to a company KB."""
    _set_principal(monkeypatch, OWNER)
    kb = _create_kb(client, "公司公共库", "company")
    kb_id = kb["id"]

    _set_principal(monkeypatch, MEMBER_A)
    resp = client.post(
        f"/kb/{kb_id}/documents",
        files={"file": ("member_doc.pdf", _make_pdf("content"), "application/pdf")},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test 8: KB delete — owner only (dept_admin for department KB)
# ---------------------------------------------------------------------------


def test_kb_delete_owner_only(client, monkeypatch):
    """Only owner can delete company KB; dept_admin can delete department KB."""
    _set_principal(monkeypatch, OWNER)
    company_kb = _create_kb(client, "公司库", "company")
    company_kb_id = company_kb["id"]

    _set_principal(monkeypatch, DEPT_ADMIN_A)
    dept_kb = _create_kb(client, "A部门库", "department", department_id=10)
    dept_kb_id = dept_kb["id"]

    # Member cannot delete company KB
    _set_principal(monkeypatch, MEMBER_A)
    resp = client.delete(f"/kb/{company_kb_id}")
    assert resp.status_code == 403

    # Owner can delete company KB
    _set_principal(monkeypatch, OWNER)
    resp = client.delete(f"/kb/{company_kb_id}")
    assert resp.status_code == 204

    # Member cannot delete department KB
    _set_principal(monkeypatch, MEMBER_A)
    resp = client.delete(f"/kb/{dept_kb_id}")
    assert resp.status_code == 403

    # dept_admin can delete department KB
    _set_principal(monkeypatch, DEPT_ADMIN_A)
    resp = client.delete(f"/kb/{dept_kb_id}")
    assert resp.status_code == 204
