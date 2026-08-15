"""口腔诊所客服插件（ddw_clinic_cs）基础测试."""
from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import yaml

_PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "ddw_clinic_cs"


# ------------------------------------------------------------------ #
# Test 1: import 链
# ------------------------------------------------------------------ #
def test_import_chain():
    mod = importlib.import_module("plugins.ddw_clinic_cs")
    assert hasattr(mod, "Plugin")
    assert mod.Plugin.name == "ddw_clinic_cs"


# ------------------------------------------------------------------ #
# Test 2: manifest 合法
# ------------------------------------------------------------------ #
def test_manifest_valid():
    manifest_path = _PLUGIN_DIR / "manifest.yaml"
    assert manifest_path.exists(), "manifest.yaml 不存在"
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert data["name"] == "ddw_clinic_cs"
    assert "config" in data
    assert "optional" in data["config"]
    assert "clinic_name" in data["config"]["optional"]


# ------------------------------------------------------------------ #
# Test 3: 知识库加载
# ------------------------------------------------------------------ #
def test_knowledge_base_loads():
    from plugins.ddw_clinic_cs.kb import KnowledgeBase

    kb_dir = str(_PLUGIN_DIR / "knowledge")
    kb = KnowledgeBase(kb_dir)
    assert len(kb.chunks) >= 1, (
        f"知识库应加载 ≥1 chunk，实际 {len(kb.chunks)}"
    )


# ------------------------------------------------------------------ #
# Test 4: 价格红线
# ------------------------------------------------------------------ #
def test_price_red_line():
    """prompt 含面诊引导词；话术库无价格数字."""
    # 4a: prompt 含「面诊」
    router_path = _PLUGIN_DIR / "router.py"
    router_src = router_path.read_text(encoding="utf-8")
    assert "面诊" in router_src, "prompt 应包含「面诊」"
    assert "不透露" in router_src or "绝不透露" in router_src, (
        "prompt 应包含价格红线规则"
    )

    # 4b: clinic_price.json exemplar_qa.ai 不含"\d+元"模式
    price_file = _PLUGIN_DIR / "scripts" / "clinic_price.json"
    assert price_file.exists(), "clinic_price.json 不存在"
    items = json.loads(price_file.read_text(encoding="utf-8"))
    price_pattern = re.compile(r"\d+\s*元")
    for item in items:
        ai_text = item.get("exemplar_qa", {}).get("ai", "")
        assert not price_pattern.search(ai_text), (
            f"价格话术含数字价格: {ai_text}"
        )


# ------------------------------------------------------------------ #
# Test 5: health 端点（TestClient）
# ------------------------------------------------------------------ #
def test_health_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from plugins.ddw_clinic_cs.router import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    resp = client.get(
        "/api/v1/plugins/ddw_clinic_cs/health",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["plugin"] == "ddw_clinic_cs"


# ------------------------------------------------------------------ #
# Test 6: chat 端点（mock LLM）
# ------------------------------------------------------------------ #
def test_chat_endpoint_mock_llm(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from plugins.ddw_clinic_cs import router as r

    # Mock _ask_llm 返回固定文本
    async def fake_ask_llm(system, user, history):
        return "您好！有什么可以帮您的吗？"

    monkeypatch.setattr(r, "_ask_llm", fake_ask_llm)

    app = FastAPI()
    app.include_router(r.router)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/plugins/ddw_clinic_cs/chat",
        json={"message": "你好", "mode": "clinic"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"], "chat 应返回非空 answer"
    assert data["session_id"]
