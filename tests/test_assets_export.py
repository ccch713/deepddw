"""P0-3（R6）：AI 资产导出/导入测试（ddw_assets_v1.zip）。

验收映射：
- 导出包结构/manifest 契约（ddw_assets_v1 同构格式）；
- roundtrip：导出 → 换库 → 导入 → 知识/记忆找回；
- 幂等：同包重导（skip）不重复；
- 跨产品：Hub 风格包可降级导入（knowledge/memory 落地，skills/flows 忽略）；
- HTTP：Token 门禁 + 下载防穿越 + 非法包 4xx。
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-assets-token")

import core.knowledge as knowledge  # noqa: E402
from core.api import assets_export, assets_import  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """独立主库 + 独立导出目录（knowledge 层共享连接按路径重建）。

    向量检索关闭（_lance_available_cache=False + LANCEDB_PATH 指向临时目录）：
    检索走关键词路径，确定性断言且不污染仓库本地 LanceDB。
    """
    db = tmp_path / "ddw_main.db"
    monkeypatch.setattr(knowledge, "_db_path", lambda: db.resolve())
    knowledge.reset_conn_pool()
    monkeypatch.setattr(knowledge, "_lance_available_cache", False)
    monkeypatch.setenv("LANCEDB_PATH", str(tmp_path / "vec"))
    monkeypatch.setenv("DDW_EXPORT_DIR", str(tmp_path / "exports"))
    yield db
    knowledge.reset_conn_pool()


def _seed(db: Path) -> None:
    """造数：两篇知识文档 + 五层记忆各一条。"""
    knowledge.kb_add_document("退货政策", "七天无理由退货，运费自理", "support")
    knowledge.kb_add_document("部署手册", "局域网一条命令启动 deepDDW", "docs")
    knowledge.memory_user_put("tone", "简洁直接", workspace="shared")
    knowledge.memory_note_put("p0-3", "资产导出薄版", source="test", workspace="shared")
    conn = knowledge.get_conn()
    try:
        conn.execute(
            "INSERT INTO memory_logs (log_date, content, auto, workspace) "
            "VALUES ('2026-11-03', '完成导出功能', 0, 'shared')"
        )
        conn.execute(
            "INSERT INTO memory_reflections (ref_date, content, style, workspace, created_at) "
            "VALUES ('2026-11-02', '薄版优先', 'auto', 'shared', datetime('now'))"
        )
        conn.commit()
    finally:
        knowledge.close_conn(conn)
    knowledge.memory_put("imported", "hub-doc", "来自 Hub 的资产")


def test_export_package_contract(tmp_path):
    """导出：manifest 契约 + knowledge/*.json + memory/entries.jsonl。"""
    _seed(tmp_path / "ddw_main.db")
    r = assets_export.create_export()
    assert r["ok"] is True, r
    assert "/" not in r["file"]  # 仅文件名（DEF-004 口径）
    assert r["counts"]["knowledge"] == 2
    assert r["counts"]["memory"] == 5
    assert r["counts"]["skills"] == 0 and r["counts"]["flows"] == 0

    zpath = Path(os.environ["DDW_EXPORT_DIR"]) / r["file"]
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "memory/entries.jsonl" in names
        assert sum(1 for n in names if n.startswith("knowledge/")) == 2
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["format"] == "ddw_assets_v1"
        assert manifest["source"]["product"] == "deepddw"
        assert manifest["assets"]["knowledge"]["count"] == 2
        doc = json.loads(zf.read("knowledge/doc-00000.json"))
        assert doc["title"] == "退货政策"
        assert len(doc["file_hash"]) == 64  # sha256
        entries = [
            json.loads(ln)
            for ln in zf.read("memory/entries.jsonl").decode().splitlines()
        ]
        ns_set = {e["namespace"] for e in entries}
        assert ns_set == {"user", "notes", "logs", "reflection", "imported"}


def test_roundtrip(tmp_path):
    """roundtrip：导出 → 清库重导 → 数据找回（幂等 skip 不重复）。"""
    _seed(tmp_path / "ddw_main.db")
    r = assets_export.create_export()
    zpath = Path(os.environ["DDW_EXPORT_DIR"]) / r["file"]

    # 清库（模拟换机/重装）
    conn = knowledge.get_conn()
    try:
        conn.execute("DELETE FROM kb_documents")
        conn.execute("DELETE FROM memory_user")
        conn.execute("DELETE FROM memory_notes")
        conn.execute("DELETE FROM memory_logs")
        conn.execute("DELETE FROM memory_reflections")
        conn.execute("DELETE FROM memory_entries")
        conn.commit()
    finally:
        knowledge.close_conn(conn)

    res = assets_import.import_package(zpath, conflict="skip")
    assert res["ok"] is True
    assert res["counts"]["knowledge"]["added"] == 2
    assert res["counts"]["knowledge"]["skipped"] == 0
    assert res["counts"]["memory"]["upserted"] == 5

    # 知识找回（检索可用——关键词路径命中标题/摘要）
    hits = knowledge.kb_search("退货")["results"]
    assert any("退货政策" in (h.get("title") or "") + (h.get("excerpt") or "")
               for h in hits)
    # 记忆找回
    assert knowledge.memory_user_list()["results"][0]["key"] == "tone"
    assert knowledge.memory_note_list()["results"][0]["value"] == "资产导出薄版"

    # 幂等：同包重导（skip）→ 知识全跳过、日志不重复
    res2 = assets_import.import_package(zpath, conflict="skip")
    assert res2["counts"]["knowledge"]["skipped"] == 2
    assert res2["counts"]["knowledge"]["added"] == 0
    conn = knowledge.get_conn()
    try:
        n_logs = conn.execute(
            "SELECT COUNT(*) FROM memory_logs WHERE content='完成导出功能'"
        ).fetchone()[0]
    finally:
        knowledge.close_conn(conn)
    assert n_logs == 1  # append-only 判重


def test_import_hub_package(tmp_path):
    """跨产品：Hub 风格包降级导入——knowledge/memory 落地，skills/flows 忽略。"""
    pkg = tmp_path / "hub-export.zip"
    doc = {
        "external_id": "kh-001", "title": "华工正源8D流程",
        "content": "8D报告自动生成", "category": "quality",
        "file_hash": "a" * 64,
        "chunks": [{"index": 0, "content": "8D报告自动生成"}],
    }
    manifest = {
        "format": "ddw_assets_v1",
        "created_at": "2026-11-03T00:00:00",
        "source": {"product": "hub", "app_version": "1.0", "tenant": "t1"},
        "assets": {"knowledge": {"count": 1}, "skills": {"count": 1},
                   "memory": {"count": 1}, "flows": {"count": 1}},
    }
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr("knowledge/doc-00000.json", json.dumps(doc, ensure_ascii=False))
        zf.writestr("memory/entries.jsonl", json.dumps(
            {"namespace": "user", "key": "owner", "value": "陈烨",
             "tags": [], "source": None, "created_at": None}, ensure_ascii=False))
        zf.writestr("skills/three-way-match.yaml", "skill_id: three-way-match")
        zf.writestr("flows/flows.json", "[]")

    res = assets_import.import_package(pkg, conflict="skip")
    assert res["ok"] is True
    assert res["source"]["product"] == "hub"
    assert res["counts"]["knowledge"]["added"] == 1
    assert res["counts"]["skills_ignored"] == 1
    assert res["counts"]["flows_ignored"] == 1
    assert res["note"]  # 忽略说明
    # 落地校验
    assert knowledge.kb_search("8D")["results"]
    assert knowledge.memory_user_list()["results"][0]["value"] == "陈烨"


def test_import_rejects_bad_package(tmp_path):
    """非法包：非 zip / 缺 manifest / 格式不对 → ValueError（客户端错误）。"""
    bad1 = tmp_path / "not-a-zip.zip"
    bad1.write_bytes(b"plain text")
    with pytest.raises(ValueError):
        assets_import.import_package(bad1)

    bad2 = tmp_path / "no-manifest.zip"
    with zipfile.ZipFile(bad2, "w") as zf:
        zf.writestr("knowledge/doc.json", "{}")
    with pytest.raises(ValueError):
        assets_import.import_package(bad2)

    bad3 = tmp_path / "wrong-format.zip"
    with zipfile.ZipFile(bad3, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "something_else"}))
    with pytest.raises(ValueError):
        assets_import.import_package(bad3)


async def test_assets_http_endpoints(client, tmp_path):
    """HTTP：export/list/download + import 上传 + 401 门禁 + 4xx 分流。"""
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    knowledge.kb_add_document("HTTP文档", "资产包 HTTP 冒烟", "test")

    r = await client.post("/api/v1/assets/export", headers=headers,
                          json={"workspace": "shared"})
    assert r.status_code == 200 and r.json()["data"]["ok"]
    fname = r.json()["data"]["file"]

    r2 = await client.get("/api/v1/assets/exports", headers=headers)
    assert r2.status_code == 200 and r2.json()["data"]["results"]

    r3 = await client.get(f"/api/v1/assets/exports/{fname}", headers=headers)
    assert r3.status_code == 200

    # 不存在 → 404（不泄露文件）；穿越防护由 Path(name).name 归一兜底
    r4 = await client.get("/api/v1/assets/exports/no-such-export.zip",
                          headers=headers)
    assert r4.status_code == 404

    # import：dry_run 上传
    with open(Path(os.environ["DDW_EXPORT_DIR"]) / fname, "rb") as f:
        r5 = await client.post(
            "/api/v1/assets/import", headers=headers,
            files={"file": (fname, f, "application/zip")},
            data={"workspace": "shared", "conflict": "skip", "dry_run": "true"},
        )
    assert r5.status_code == 200
    assert r5.json()["data"]["dry_run"] is True

    # 非法包 → 4xx（非 500）
    r6 = await client.post(
        "/api/v1/assets/import", headers=headers,
        files={"file": ("bad.zip", b"not a zip", "application/zip")},
        data={"conflict": "skip"},
    )
    assert 400 <= r6.status_code < 500

    # 无 Token → 401
    r7 = await client.get("/api/v1/assets/exports")
    assert r7.status_code == 401
