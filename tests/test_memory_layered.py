"""分层记忆测试（借鉴 dsh-auto-memory：三层/注入/沉淀/反思/预算/迁移/降级）。"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-memory-layered-token")

import pytest  # noqa: E402

from core.knowledge import (  # noqa: E402
    memory_budget_status,
    memory_context_build,
    memory_log_append,
    memory_logs_recent,
    memory_maintain,
    memory_note_put,
    memory_reflect_save,
    memory_search_v2,
    memory_user_put,
    migrate_memory_entries,
    reset_conn_pool,
)


@pytest.fixture(autouse=True)
def _reset(monkeypatch, tmp_path):
    """每测试独立库 + 清连接。"""
    from core import knowledge as kb

    monkeypatch.setattr(kb, "_db_path", lambda: tmp_path / "kb.db")
    reset_conn_pool()
    yield
    reset_conn_pool()


def test_layered_write_and_read():
    """三层写入/读取隔离（user/notes/logs/reflections 各自独立）。"""
    assert memory_user_put("规则A", "值A")["ok"]
    assert memory_note_put("决策B", "值B", source="deepddw")["ok"]
    assert memory_log_append("日志C", auto=True)["ok"]
    assert memory_reflect_save("反思D")["ok"]

    ctx = memory_context_build()
    assert "规则A" in ctx["context"]
    assert "决策B" in ctx["context"]
    assert "日志C" in ctx["context"]
    assert "反思D" not in ctx["context"]  # 反思不注入，仅检索
    assert ctx["chars"] <= ctx["budget"] * 1.2  # 预算截断不超太多


def test_context_budget_truncation():
    """注入预算截断：超预算时保留头尾并标注省略。"""
    for i in range(30):
        memory_user_put(f"规则{i}", "x" * 300)
    ctx = memory_context_build(budget=500)
    assert ctx["chars"] <= 600  # 500 预算 + 包装开销
    assert "…(记忆注入按预算截断" in ctx["context"]


def test_logs_append_only_and_recent():
    """日志 append-only：多次追加都在，recent 按日期倒序。"""
    memory_log_append("第一条")
    memory_log_append("第二条", auto=True)
    logs = memory_logs_recent(days=1)["results"]
    assert len(logs) == 2
    contents = [r["content"] for r in logs]
    assert "第一条" in contents and "第二条" in contents


def test_reflect_save_overwrites_same_date():
    """反思同日期覆盖（UNIQUE ref_date）。"""
    memory_reflect_save("v1", style="生活化")
    memory_reflect_save("v2", style="专业")
    from core.knowledge import memory_reflect_get

    r = memory_reflect_get(__import__("datetime").date.today().strftime("%Y-%m-%d"))
    assert r["found"] and r["content"] == "v2" and r["style"] == "专业"


def test_search_v2_multi_layer_with_source():
    """分层检索：跨层命中且带来源标注。"""
    memory_user_put("偏好", "喜欢简洁回答")
    memory_note_put("部署", "deepDDW 用 Docker 部署")
    memory_log_append("今天修了部署问题")
    hits = memory_search_v2("部署 简洁", 10)["results"]
    layers = {h["layer"] for h in hits}
    assert "user" in layers
    assert "notes" in layers
    assert "logs" in layers
    for h in hits:
        assert "source" in h and h["source"]  # 来源标注必有


def test_budget_status_and_maintain():
    """预算统计 + 超限压缩归档（不丢数据）。"""
    memory_note_put("旧1", "x" * 100)
    memory_note_put("旧2", "x" * 100)
    status = memory_budget_status()
    assert "user" in status and "notes" in status and "over" in status
    # 强制超限场景：直接归档最旧（maintain 在 over 时归档）
    result = memory_maintain()
    assert "archived" in result


def test_migrate_preserves_data():
    """迁移：旧 memory_entries → 分层（分类正确、数据不丢）。"""
    from core.knowledge import memory_put

    memory_put("default", "user-key", "用户规则内容", ["user"])
    memory_put("default", "note-key", "笔记内容", ["note"])
    memory_put("default", "log-key", "日志内容", ["log"])
    result = migrate_memory_entries()
    assert result["total"] == 3
    assert result["user"] >= 1
    assert result["notes"] >= 1
    assert result["logs"] >= 1


def test_consolidate_rule_base():
    """自动沉淀基座：统计当日 auto 日志数（寒暄阈值由调用方控制）。"""
    from core.knowledge import memory_consolidate

    memory_log_append("要点一", auto=True)
    info = memory_consolidate(auto_consolidate_min_chars=60)
    assert info["ok"] and info["today_auto_count"] >= 1


# ---------------------------------------------------------------------------
# HTTP 端点 + MCP 工具（v2.1：分层记忆以官方接口/MCP 工具暴露）
# ---------------------------------------------------------------------------


async def test_memory_api_endpoints(client, monkeypatch, tmp_path):
    """分层记忆 HTTP 端点（user/notes/logs/context/reflect/budget/maintain）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}

    r = await client.post("/api/v1/memory/user", headers=headers,
                          json={"key": "语气", "value": "亲切"})
    assert r.status_code == 200 and r.json()["data"]["ok"]

    r = await client.post("/api/v1/memory/notes", headers=headers,
                          json={"key": "决策", "value": "用 MCP 接入"})
    assert r.status_code == 200 and r.json()["data"]["ok"]

    r = await client.post("/api/v1/memory/logs", headers=headers,
                          json={"content": "今天完成记忆分层", "auto": True})
    assert r.status_code == 200 and r.json()["data"]["ok"]

    r = await client.get("/api/v1/memory/context", headers=headers)
    assert r.status_code == 200
    assert "语气" in r.json()["data"]["context"]

    r = await client.get("/api/v1/memory/logs", headers=headers, params={"days": 1})
    assert r.status_code == 200 and r.json()["data"]["results"]

    r = await client.post("/api/v1/memory/reflect", headers=headers,
                          json={"content": "今天反思", "style": "auto"})
    assert r.status_code == 200 and r.json()["data"]["ok"]

    r = await client.get("/api/v1/memory/budget", headers=headers)
    assert r.status_code == 200 and "user" in r.json()["data"]

    r = await client.get("/api/v1/memory/search-v2", headers=headers,
                         params={"q": "记忆"})
    assert r.status_code == 200 and "layers" in r.json()["data"]


async def test_memory_api_requires_auth(client, tmp_path):
    """无 Token → 记忆端点 401。"""
    r = await client.get("/api/v1/memory/context")
    assert r.status_code == 401


async def test_mcp_memory_tools(monkeypatch, tmp_path):
    """MCP 记忆工具：context/consolidate/reflect/maintain/note/user/search-v2。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core.mcp.server import get_mcp_server

    mcp = get_mcp_server()
    for name in ("ddw.memory.context", "ddw.memory.consolidate",
                 "ddw.memory.reflect", "ddw.memory.maintain",
                 "ddw.memory.note", "ddw.memory.user",
                 "ddw.memory.search-v2"):
        assert mcp.tools.get(name) is not None, name

    note = await mcp.tools.get("ddw.memory.note").handler(
        {"key": "MCP笔记", "value": "通过工具写入"}, {})
    assert note["ok"] is True

    user = await mcp.tools.get("ddw.memory.user").handler(
        {"key": "MCP偏好", "value": "简明"}, {})
    assert user["ok"] is True

    cons = await mcp.tools.get("ddw.memory.consolidate").handler(
        {"content": "工具沉淀要点"}, {})
    assert cons["ok"] is True

    ctx = await mcp.tools.get("ddw.memory.context").handler({}, {})
    assert "MCP笔记" in ctx["content"][0]["text"]

    ref = await mcp.tools.get("ddw.memory.reflect").handler(
        {"content": "工具反思", "style": "auto"}, {})
    assert ref["ok"] is True

    sv = await mcp.tools.get("ddw.memory.search-v2").handler(
        {"query": "MCP"}, {})
    assert sv["results"]

    mt = await mcp.tools.get("ddw.memory.maintain").handler({}, {})
    assert "ok" in mt


# ---------------------------------------------------------------------------
# LLM 增强（auto-memory 智能检索：关键词扩写 / AI 提炼沉淀；失败降级）
# ---------------------------------------------------------------------------


async def test_search_v2_llm_expand_uses_keywords(monkeypatch, tmp_path):
    """LLM 扩写命中：mock 网关返回关键词 → 用扩写词扫描并带 expanded 标注。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb
    from core.llm_gateway.base import ChatResponse

    kb.memory_user_put("部署", "deepDDW 用 Docker Compose 部署")
    kb.memory_log_append("修复了 compose 网络问题")

    async def fake_chat(messages, **kwargs):
        return ChatResponse(
            content='["部署", "compose", "容器"]',
            model="mock", provider="mock", finish_reason="stop",
        )

    monkeypatch.setattr("core.llm_gateway.gateway.chat", fake_chat)
    result = await kb.memory_search_v2_async("怎么部署服务", top_k=10, expand=True)
    assert result["expanded"] == ["部署", "compose", "容器"]
    layers = {h["layer"] for h in result["results"]}
    assert "user" in layers and "logs" in layers
    assert result["degraded"] is False


async def test_search_v2_llm_failure_degrades(monkeypatch, tmp_path):
    """LLM 故障 → 降级原词扫描，仍返回结果且不阻塞。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb

    kb.memory_user_put("偏好", "喜欢简洁回答")

    async def boom(messages, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("core.llm_gateway.gateway.chat", boom)
    result = await kb.memory_search_v2_async("偏好 风格", top_k=5, expand=True)
    assert result["expanded"] == []  # 降级无扩写
    assert any("偏好" in h["content"] or h["key"] == "偏好" for h in result["results"])


async def test_consolidate_llm_distills_points(monkeypatch, tmp_path):
    """LLM 提炼沉淀：mock 返回要点数组 → 写入今日日志（auto=1）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb
    from core.llm_gateway.base import ChatResponse

    async def fake_chat(messages, **kwargs):
        return ChatResponse(
            content='["决定用 Docker Compose 部署", "偏好中文回复"]',
            model="mock", provider="mock", finish_reason="stop",
        )

    monkeypatch.setattr("core.llm_gateway.gateway.chat", fake_chat)
    result = await kb.memory_consolidate_llm(
        "今天我们讨论了部署方案，最终决定用 Docker Compose。"
        "另外用户表示希望用中文回复。这是足够长的一段对话文本内容。"
    )
    assert result["mode"] == "llm" and result["wrote"] == 2
    logs = kb.memory_logs_recent(days=1)["results"]
    contents = [r["content"] for r in logs]
    assert any("Docker Compose" in c for c in contents)


async def test_consolidate_llm_too_short_skips(monkeypatch, tmp_path):
    """寒暄短轮 → 跳过沉淀（不写日志）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb

    result = await kb.memory_consolidate_llm("你好")
    assert result.get("skipped") == "too_short"
    assert kb.memory_logs_recent(days=1)["results"] == []


# ---------------------------------------------------------------------------
# 优化① 反思生成接 LLM / 优化③ 扩写缓存去重 / chat 自动沉淀
# ---------------------------------------------------------------------------


async def test_reflect_generate_llm_saves(monkeypatch, tmp_path):
    """反思生成：mock LLM 返回正文 → 保存当日反思（generated=True）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb
    from core.llm_gateway.base import ChatResponse

    kb.memory_log_append("完成了记忆分层重构", auto=True)
    # 造"昨天有日志且今天无反思"的触发条件：日志日期需为昨天
    from core.knowledge import get_conn, close_conn

    conn = get_conn()
    conn.execute("UPDATE memory_logs SET log_date=date('now','-1 day')")
    conn.commit()
    close_conn(conn)

    async def fake_chat(messages, **kwargs):
        return ChatResponse(
            content="今天完成了记忆分层重构，进展顺利，明天继续优化检索。",
            model="mock", provider="mock", finish_reason="stop",
        )

    monkeypatch.setattr("core.llm_gateway.gateway.chat", fake_chat)
    result = await kb.memory_reflect_generate(style="auto")
    assert result["due"] is True and result["generated"] is True
    r = kb.memory_reflect_get(__import__("datetime").date.today().strftime("%Y-%m-%d"))
    assert r["found"] and "记忆分层" in r["content"]


async def test_reflect_generate_no_trigger(monkeypatch, tmp_path):
    """不满足触发（无昨日日志）→ due=False，不调 LLM。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb

    result = await kb.memory_reflect_generate()
    assert result["due"] is False and result["generated"] is False


async def test_reflect_generate_llm_failure_degrades(monkeypatch, tmp_path):
    """LLM 故障 → generated=False + degraded，不写空内容。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb

    kb.memory_log_append("昨天有日志", auto=True)
    from core.knowledge import get_conn, close_conn

    conn = get_conn()
    conn.execute("UPDATE memory_logs SET log_date=date('now','-1 day')")
    conn.commit()
    close_conn(conn)

    async def boom(messages, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("core.llm_gateway.gateway.chat", boom)
    result = await kb.memory_reflect_generate()
    assert result["due"] is True and result["generated"] is False
    assert result.get("degraded") is True


async def test_keyword_expand_cache_dedupe(monkeypatch, tmp_path):
    """扩写缓存：同查询第二次不调 LLM（命中缓存返回同结果）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb
    from core.llm_gateway.base import ChatResponse

    calls = []

    async def fake_chat(messages, **kwargs):
        calls.append(1)
        return ChatResponse(
            content='["部署", "compose", "容器"]',
            model="mock", provider="mock", finish_reason="stop",
        )

    monkeypatch.setattr("core.llm_gateway.gateway.chat", fake_chat)
    kb.reset_keyword_cache()
    r1 = await kb._llm_expand_keywords_async("怎么部署服务")
    r2 = await kb._llm_expand_keywords_async("怎么部署服务")  # 缓存命中
    assert r1 == ["部署", "compose", "容器"]
    assert r2 == r1
    assert len(calls) == 1  # 只调了一次 LLM
    kb.reset_keyword_cache()


async def test_chat_auto_consolidate_background(client, monkeypatch, tmp_path):
    """chat auto_consolidate：响应后后台沉淀写日志（不阻塞响应）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core.api import chat as chat_mod
    from core.llm_gateway.base import ChatResponse

    async def fake_chat(messages, **kwargs):
        return ChatResponse(
            content="好的，我们决定用 Docker 部署这个服务。",
            model="deepseek-chat", provider="deepseek", finish_reason="stop",
        )

    monkeypatch.setattr(chat_mod, "llm_chat", fake_chat)
    # 记忆注入降级为空，聚焦 auto_consolidate 路径
    monkeypatch.setattr(
        chat_mod, "_apply_memory", lambda m: {"chars": 0, "degraded": False}
    )
    # 记录 consolidate 是否被调用（后台任务）
    called = {"n": 0}

    async def fake_consolidate(text):
        called["n"] += 1
        return {"ok": True, "mode": "rule", "wrote": 1}

    monkeypatch.setattr("core.knowledge.memory_consolidate_llm", fake_consolidate)

    resp = await client.post(
        "/api/v1/chat/",
        headers={"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]},
        json={"message": "我们决定用 Docker 部署，用国内镜像加速。", "rag": False},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["content"]
    # 后台任务异步执行：让事件循环跑一拍后再断言
    import asyncio

    for _ in range(10):
        await asyncio.sleep(0.01)
        if called["n"] > 0:
            break
    assert called["n"] == 1

    # auto_consolidate=False 时不触发
    resp2 = await client.post(
        "/api/v1/chat/",
        headers={"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]},
        json={"message": "这条不沉淀。", "rag": False, "auto_consolidate": False},
    )
    assert resp2.status_code == 200
    await asyncio.sleep(0.02)
    assert called["n"] == 1


# ---------------------------------------------------------------------------
# v0.3.0 反思 LLM 化收尾：风格指南 / 无价值跳过 / 空日志 / 不重复
# ---------------------------------------------------------------------------


async def test_reflect_generate_style_guide_in_prompt(monkeypatch, tmp_path):
    """反思 prompt 含风格指南（专业风格 → 分点陈述指令）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb
    from core.llm_gateway.base import ChatResponse

    kb.memory_log_append("完成了压测", auto=True)
    from core.knowledge import get_conn, close_conn

    conn = get_conn()
    conn.execute("UPDATE memory_logs SET log_date=date('now','-1 day')")
    conn.commit()
    close_conn(conn)

    captured = {}

    async def fake_chat(messages, **kwargs):
        captured["prompt"] = messages[0].content
        return ChatResponse(
            content="进展：完成压测。\n问题：无。\n明日注意：发布。",
            model="mock", provider="mock", finish_reason="stop",
        )

    monkeypatch.setattr("core.llm_gateway.gateway.chat", fake_chat)
    result = await kb.memory_reflect_generate(style="专业")
    assert result["generated"] is True
    assert "面向团队复盘" in captured["prompt"]  # 风格指南注入
    assert "进展 / 问题 / 明日注意" in captured["prompt"]  # 三段结构


async def test_consolidate_llm_no_value_skips_rule(monkeypatch, tmp_path):
    """LLM 判断无价值（[]）→ 不落日志（不触发规则降级）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb
    from core.llm_gateway.base import ChatResponse

    async def fake_chat(messages, **kwargs):
        return ChatResponse(
            content="[]", model="mock", provider="mock", finish_reason="stop",
        )

    monkeypatch.setattr("core.llm_gateway.gateway.chat", fake_chat)
    result = await kb.memory_consolidate_llm(
        "今天就是随便聊了聊天气，没有什么特别值得记住的内容，纯闲聊。"
        "天气不错，晚饭吃了面，其他就没有什么特别的进展了，一切照旧。"
    )
    assert result["ok"] is True and result["mode"] == "llm"
    assert result.get("skipped") == "no_value"
    assert result["wrote"] == 0
    # 无任何日志落库
    logs = kb.memory_logs_recent(days=1).get("results", [])
    assert logs == []


async def test_reflect_generate_empty_logs_no_write(monkeypatch, tmp_path):
    """触发条件满足但无日志 → 不生成、不写空内容。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb

    # 触发条件成立（mock _reflection_due=True）但日志为空 → 不生成
    monkeypatch.setattr(kb, "_reflection_due", lambda: True)

    result = await kb.memory_reflect_generate()
    assert result["due"] is True
    assert result["generated"] is False
    assert result.get("note") == "no logs"


# ---------------------------------------------------------------------------
# v0.3.0 记忆检索质量优化：跨层排序 + 扩写缓存失效
# ---------------------------------------------------------------------------


def test_search_v2_ranking_user_before_logs(monkeypatch, tmp_path):
    """排序优化：同命中数下 user 层优先于 logs 层（层权重 4 > 1）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb

    # 同一关键词同时命中 user 与 logs
    kb.memory_user_put("部署", "deepDDW 用 Docker 部署")
    kb.memory_log_append("今天研究了 Docker 部署")

    hits = kb.memory_search_v2("Docker 部署", top_k=5)["results"]
    layers = [h["layer"] for h in hits]
    # 两个来源都命中；user 层排在最前（权重高）
    assert "user" in layers and "logs" in layers
    assert layers.index("user") < layers.index("logs")


def test_search_v2_ranking_hit_count(monkeypatch, tmp_path):
    """排序优化：命中关键词更多的条目排前（同层内）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb

    kb.memory_note_put("A", "Docker Compose 部署方案")
    kb.memory_note_put("B", "只有 Docker")

    hits = kb.memory_search_v2("Docker Compose", top_k=5)["results"]
    keys = [h["key"] for h in hits]
    assert keys.index("A") < keys.index("B")  # A 命中 2 词，B 命中 1 词


async def test_keyword_cache_expiry_reinvokes_llm(monkeypatch, tmp_path):
    """扩写缓存过期后重新调 LLM（TTL 控制，避免无限缓存）。"""
    monkeypatch.setattr("core.knowledge._db_path", lambda: tmp_path / "kb.db")
    from core import knowledge as kb
    from core.llm_gateway.base import ChatResponse

    calls = {"n": 0}

    async def fake_chat(messages, **kwargs):
        calls["n"] += 1
        return ChatResponse(
            content='["缓存", "测试"]',
            model="mock", provider="mock", finish_reason="stop",
        )

    monkeypatch.setattr("core.llm_gateway.gateway.chat", fake_chat)
    kb.reset_keyword_cache()
    # 第一次：调 LLM 并缓存
    r1 = await kb._llm_expand_keywords_async("缓存测试")
    assert r1 == ["缓存", "测试"] and calls["n"] == 1
    # 缓存命中：不调 LLM
    r2 = await kb._llm_expand_keywords_async("缓存测试")
    assert r2 == r1 and calls["n"] == 1
    # 强制过期：直接改缓存时间戳 → 重新调 LLM
    with kb._keyword_cache_lock:
        _, expire = kb._keyword_cache["缓存测试"]
        kb._keyword_cache["缓存测试"] = (("缓存", "测试"), expire - 7200)
    r3 = await kb._llm_expand_keywords_async("缓存测试")
    assert r3 == ["缓存", "测试"] and calls["n"] == 2
    kb.reset_keyword_cache()
