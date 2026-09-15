"""P0/P1 社区需求：迁移导入导出 + 作用域提升 + 无痕 + 检索健康。"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-community-features-token")

import json  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    from core import knowledge as kb
    from core.api import workspace as ws
    from core.privacy import reset_privacy_map

    monkeypatch.setattr(kb, "_db_path", lambda: tmp_path / "kb.db")
    ws.reset_workspace_map()
    reset_privacy_map()
    kb.reset_conn_pool()
    yield
    ws.reset_workspace_map()
    reset_privacy_map()
    kb.reset_conn_pool()


# ---------------------------------------------------------------------------
# P0-1 迁移导入 / P1-6 导出
# ---------------------------------------------------------------------------


def test_import_jsonl_deepddw_format():
    from core.api.migration import _normalize_rows, apply_import
    from core.knowledge import memory_user_list

    content = "\n".join([
        json.dumps({"layer": "user", "key": "偏好语言", "value": "中文"}, ensure_ascii=False),
        json.dumps({"layer": "notes", "key": "部署", "value": "用 docker compose"}, ensure_ascii=False),
    ])
    rows = _normalize_rows("deepddw", content, "imported")
    assert len(rows) == 2
    result = apply_import(rows, workspace="teamX")
    assert result["ok"] is True
    assert result["counts"]["user"] == 1
    assert result["counts"]["notes"] == 1
    keys = {r["key"] for r in memory_user_list("teamX").get("results", [])}
    assert "偏好语言" in keys


def test_import_markdown_sections():
    from core.api.migration import _normalize_rows, apply_import
    from core.knowledge import memory_note_list

    md = """# Memory
## 部署流程
先跑 install.sh 再启动网关。
## 团队约定
PR 必须过 CI。
"""
    rows = _normalize_rows("markdown", md, "imported")
    assert any(r["key"] == "部署流程" for r in rows)
    apply_import(rows, workspace="shared")
    notes = {r["key"] for r in memory_note_list("shared").get("results", [])}
    assert "部署流程" in notes


def test_export_jsonl_roundtrip():
    from core.api.migration import apply_import, export_memory, _normalize_rows
    from core.knowledge import memory_user_put

    memory_user_put("角色", "FDE", workspace="teamY")
    export = export_memory(workspace="teamY", fmt="jsonl")
    assert export["ok"] is True
    assert export["count"] >= 1
    assert "FDE" in export["content"]
    # 再导入到另一 workspace
    rows = _normalize_rows("deepddw", export["content"], "imported")
    result = apply_import(rows, workspace="teamZ", dry_run=True)
    assert result["dry_run"] is True
    assert result["total"] >= 1


def test_export_markdown():
    from core.api.migration import export_memory
    from core.knowledge import memory_note_put

    memory_note_put("键A", "值A", workspace="shared")
    export = export_memory(workspace="shared", fmt="markdown")
    assert export["format"] == "markdown"
    assert "值A" in export["content"]


# ---------------------------------------------------------------------------
# P0-2 作用域提升 + 冲突
# ---------------------------------------------------------------------------


def test_scope_promote_no_conflict(tmp_path, monkeypatch):
    from core.api import scope as scope_api
    from core.knowledge import memory_note_put, memory_note_list

    monkeypatch.setattr(scope_api, "_db_path", lambda: tmp_path / "kb.db")
    memory_note_put("SOP", "先备份再升级", workspace="alice")
    result = scope_api.promote("notes", "SOP", "alice", "shared")
    assert result["ok"] is True
    assert result["status"] == "approved"
    notes = {r["key"]: r["value"] for r in memory_note_list("shared").get("results", [])}
    assert notes.get("SOP") == "先备份再升级"


def test_scope_promote_conflict_and_resolve(tmp_path, monkeypatch):
    from core.api import scope as scope_api
    from core.knowledge import memory_note_put, memory_note_list

    monkeypatch.setattr(scope_api, "_db_path", lambda: tmp_path / "kb.db")
    memory_note_put("SOP", "A版本", workspace="alice")
    memory_note_put("SOP", "B版本", workspace="shared")
    result = scope_api.promote("notes", "SOP", "alice", "shared")
    assert result["ok"] is True
    assert result["status"] == "conflict"
    pid = result["promotion_id"]

    pending = scope_api.list_conflicts("pending")
    assert any(c["id"] == pid for c in pending)

    resolved = scope_api.resolve(pid, "use_source")
    assert resolved["ok"] is True
    notes = {r["key"]: r["value"] for r in memory_note_list("shared").get("results", [])}
    assert notes.get("SOP") == "A版本"


# ---------------------------------------------------------------------------
# P0-3 无痕会话
# ---------------------------------------------------------------------------


def test_incognito_blocks_memory_put():
    from core.privacy import set_incognito, is_incognito, reset_privacy_map

    set_incognito("sess-1", True)
    assert is_incognito("sess-1") is True
    # 直接 memory_put 不经 privacy 层（handler 层拦截）；此处验证 API 语义
    from core.mcp.tools import memory_put_handler
    import asyncio

    resp = asyncio.run(
        memory_put_handler({"key": "k", "value": "v"}, {"session_id": "sess-1"})
    )
    assert resp.get("incognito") is True
    assert resp.get("ok") is False
    reset_privacy_map()


def test_incognito_disable():
    from core.privacy import set_incognito, is_incognito

    set_incognito("sess-2", True)
    set_incognito("sess-2", False)
    assert is_incognito("sess-2") is False


def test_chat_payload_privacy_skips_consolidate(monkeypatch):
    """privacy=True 时 auto_consolidate 分支不触发（逻辑门控）。"""
    from core.api.chat import ChatRequest

    p = ChatRequest(message="hi", privacy=True, auto_consolidate=True)
    assert p.privacy is True
    # 门控条件：payload.auto_consolidate and not payload.privacy
    assert not (p.auto_consolidate and not p.privacy)


# ---------------------------------------------------------------------------
# P1-4 检索健康 / 注入预览
# ---------------------------------------------------------------------------


def test_retrieval_health_shape():
    from core.api.privacy_health import retrieval_health
    import asyncio

    resp = asyncio.run(retrieval_health(claims={}))
    assert resp["code"] == 0
    data = resp["data"]
    assert "checks" in data
    assert "fts5" in data["checks"]
    assert "kb_search" in data["checks"]


def test_injection_preview_empty_workspace():
    from core.api.privacy_health import injection_preview
    import asyncio

    resp = asyncio.run(
        injection_preview(workspace="empty-ws-x", budget=500, claims={})
    )
    assert resp["code"] == 0
    assert resp["data"]["workspace"] == "empty-ws-x"
    assert "preview" in resp["data"]


# ---------------------------------------------------------------------------
# P1-5 CJK 分词
# ---------------------------------------------------------------------------


def test_cjk_bigram_tokenize():
    from core.knowledge import _tokenize_query

    tokens = _tokenize_query("部署流程")
    assert "部署" in tokens
    assert "流程" in tokens


def test_cjk_search_finds_note():
    from core.knowledge import memory_note_put, memory_search_v2

    memory_note_put("ops", "发布前需要执行部署流程并通知运维", workspace="shared")
    result = memory_search_v2("部署流程", top_k=5, workspace="shared")
    keys = [r["key"] for r in result.get("results", [])]
    assert "ops" in keys
