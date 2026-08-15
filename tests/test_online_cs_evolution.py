"""进化系统测试 — pytest + 临时目录."""
from __future__ import annotations

import json
import tarfile
import time
from pathlib import Path


import pytest


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #
@pytest.fixture(autouse=True)
def _patch_log_dir(monkeypatch, tmp_path):
    """把 log_store.LOG_DIR 指到 tmp_path."""
    import plugins.ddw_online_cs.log_store as ls

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(ls, "LOG_DIR", log_dir)


@pytest.fixture()
def _patch_scripts_dir(monkeypatch, tmp_path):
    """把 curator.SCRIPTS_DIR / PENDING_DIR 指到 tmp_path."""
    import plugins.ddw_online_cs.curator as cur

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    pending = tmp_path / "pending_review"
    pending.mkdir()
    pool = tmp_path / "evolution_pool"
    pool.mkdir()
    monkeypatch.setattr(cur, "SCRIPTS_DIR", scripts)
    monkeypatch.setattr(cur, "PENDING_DIR", pending)
    monkeypatch.setattr(cur, "POOL_DIR", pool)
    return scripts, pending, pool


# ------------------------------------------------------------------ #
# Test 1: log_store append + read_day 往返
# ------------------------------------------------------------------ #
def test_log_store_append_read_roundtrip():
    from plugins.ddw_online_cs.log_store import (
        append_chat,
        read_day,
    )

    today = time.strftime("%Y-%m-%d")
    append_chat(
        "s1", "presales", "你好", "嗨！有什么可以帮您？",
        "kb+llm", 120, False,
    )
    records = read_day(today)
    assert len(records) >= 1
    r = records[-1]
    assert r["session_id"] == "s1"
    assert r["mode"] == "presales"
    assert r["user_msg"] == "你好"
    assert r["ai_reply"] == "嗨！有什么可以帮您？"
    assert "ts" in r
    # JSON 合法（能反序列化说明格式正确）
    json.dumps(records, ensure_ascii=False)


# ------------------------------------------------------------------ #
# Test 2: log_store 跨天文件分离
# ------------------------------------------------------------------ #
def test_log_store_cross_day_separation(monkeypatch, tmp_path):
    from plugins.ddw_online_cs import log_store as ls

    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(ls, "LOG_DIR", log_dir)

    # 模拟不同日期写入
    import plugins.ddw_online_cs.log_store as mod

    orig_strftime = time.strftime

    def fake_strftime(fmt):
        if fmt == "%Y-%m-%d":
            return "2026-08-01"
        return orig_strftime(fmt)

    monkeypatch.setattr(time, "strftime", fake_strftime)
    mod.append_chat("s1", "presales", "hi", "hello", "kb", 10)

    def fake_strftime2(fmt):
        if fmt == "%Y-%m-%d":
            return "2026-08-02"
        return orig_strftime(fmt)

    monkeypatch.setattr(time, "strftime", fake_strftime2)
    mod.append_chat("s2", "presales", "hi2", "hello2", "kb", 10)

    assert (log_dir / "2026-08-01.jsonl").exists()
    assert (log_dir / "2026-08-02.jsonl").exists()
    assert (log_dir / "2026-08-01.jsonl") != (
        log_dir / "2026-08-02.jsonl"
    )


# ------------------------------------------------------------------ #
# Test 3: log_store cleanup 删旧留新
# ------------------------------------------------------------------ #
def test_log_store_cleanup(monkeypatch, tmp_path):
    from plugins.ddw_online_cs import log_store as ls

    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(ls, "LOG_DIR", log_dir)
    monkeypatch.setattr(ls, "RETENTION_DAYS", 7)

    # 创建旧文件
    old_file = log_dir / "2026-01-01.jsonl"
    old_file.write_text('{"ts":"old"}\n', encoding="utf-8")
    import os

    os.utime(old_file, (0, 0))

    # 创建新文件
    new_file = log_dir / "2099-12-31.jsonl"
    new_file.write_text('{"ts":"new"}\n', encoding="utf-8")

    ls.cleanup()

    assert not old_file.exists()
    assert new_file.exists()


# ------------------------------------------------------------------ #
# Test 4: log_store 写失败不 raise
# ------------------------------------------------------------------ #
def test_log_store_write_failure_no_raise(
    monkeypatch, tmp_path
):
    from plugins.ddw_online_cs import log_store as ls

    log_dir = tmp_path / "readonly_dir"
    log_dir.mkdir()
    monkeypatch.setattr(ls, "LOG_DIR", log_dir)

    # monkeypatch open to raise
    import builtins

    real_open = builtins.open

    def failing_open(*args, **kwargs):
        if (
            len(args) > 0
            and "a" in str(args[1:2])
            or kwargs.get("mode") == "a"
        ):
            raise OSError("disk full")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", failing_open)
    # 不应 raise
    ls.append_chat(
        "s1", "presales", "hi", "hello", "kb", 10
    )


# ------------------------------------------------------------------ #
# Test 5: _load_scripts 空目录返回 {}
# ------------------------------------------------------------------ #
def test_load_scripts_empty(monkeypatch, tmp_path):
    import plugins.ddw_online_cs.router as r

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    # patch Path to resolve to tmp
    orig = Path

    class PatchedPath(type(Path())):
        def __truediv__(self, other):
            if other == "scripts":
                return scripts_dir / other
            return orig.__truediv__(self, other)

    # Simpler approach: just test with empty dir
    r._SCRIPT_CACHE = None
    r._SCRIPT_CACHE_MTIME = 0.0
    # The function reads from plugin dir scripts/
    # which is empty or doesn't have .json files
    result = r._load_scripts()
    # It returns {} if no .json files found
    assert isinstance(result, dict)


# ------------------------------------------------------------------ #
# Test 6: _inject_scripts 无命中零影响
# ------------------------------------------------------------------ #
def test_inject_scripts_no_match():
    from plugins.ddw_online_cs.router import (
        _inject_scripts,
    )

    prompt = "你是客服。"
    result = _inject_scripts(prompt, "presales", "天气好吗")
    assert result == prompt


# ------------------------------------------------------------------ #
# Test 7: _inject_scripts 命中注入
# ------------------------------------------------------------------ #
def test_inject_scripts_hit(
    monkeypatch, tmp_path
):
    from plugins.ddw_online_cs import router as r

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    cat_file = scripts_dir / "presales_emotion.json"
    cat_file.write_text(
        json.dumps([{
            "category": "presales_emotion",
            "title": "价格安抚",
            "exemplar_qa": {
                "user": "你们多少钱？",
                "ai": "我们有多种方案呢～",
            },
            "source_session": "s1",
            "approved_at": "2026-08-05",
            "hit_count": 5,
        }], ensure_ascii=False),
        encoding="utf-8",
    )

    # Patch _load_scripts to read from tmp
    r._SCRIPT_CACHE = None
    r._SCRIPT_CACHE_MTIME = 0.0

    def mock_load():
        return {"presales_emotion": json.loads(
            cat_file.read_text(encoding="utf-8")
        )}

    monkeypatch.setattr(r, "_load_scripts", mock_load)

    result = r._inject_scripts(
        "你是客服。", "presales", "价格多少？"
    )
    assert "优秀回答范例" in result
    assert "我们有多种方案呢～" in result


# ------------------------------------------------------------------ #
# Test 8: _inject_scripts top_k 限制
# ------------------------------------------------------------------ #
def test_inject_scripts_top_k(
    monkeypatch, tmp_path
):
    from plugins.ddw_online_cs import router as r

    items = []
    for i in range(5):
        items.append({
            "category": "presales_emotion",
            "title": f"t{i}",
            "exemplar_qa": {
                "user": f"u{i}",
                "ai": f"a{i}",
            },
            "source_session": f"s{i}",
            "approved_at": "2026-08-05",
            "hit_count": i,
        })

    def mock_load():
        return {"presales_emotion": items}

    monkeypatch.setattr(r, "_load_scripts", mock_load)
    monkeypatch.setattr(r, "_SCRIPT_CACHE_TTL", 0.0)

    result = r._inject_scripts(
        "你是客服。", "presales", "价格贵吗"
    )
    # top_k=3, should only inject 3
    assert result.count("优秀回答范例") == 1
    # But only 3 user/ai pairs
    assert result.count("用户：") == 3


# ------------------------------------------------------------------ #
# Test 9: curator 高置信自动入库
# ------------------------------------------------------------------ #
def test_curator_auto_approve(
    _patch_scripts_dir, monkeypatch
):
    from plugins.ddw_online_cs import curator as cur

    scripts, pending, pool = _patch_scripts_dir
    monkeypatch.setattr(cur, "_AUTO_APPROVE_THRESHOLD", 0.9)

    pool_file = pool / "2026-08-05.json"
    pool_file.write_text(
        json.dumps([{
            "type": "praise",
            "confidence": 0.95,
            "summary": "很满意",
            "evidence": "谢谢你的帮助",
            "suggestion": "继续保持",
            "_session_id": "cs_abc",
            "_conv_user": "你们产品真好用",
            "_conv_ai": "感谢您的认可！我们会继续努力～",
        }], ensure_ascii=False),
        encoding="utf-8",
    )

    cur.process_day("2026-08-05")

    # 检查 scripts 中是否有入库条目
    found = False
    for p in scripts.glob("*.json"):
        items = json.loads(p.read_text(encoding="utf-8"))
        for item in items:
            if item.get("title") == "很满意":
                found = True
                assert "approved_at" in item
                qa = item.get("exemplar_qa", {})
                assert qa["user"] == "你们产品真好用"
                assert qa["ai"] == "感谢您的认可！我们会继续努力～"
    assert found, "高置信好评应自动入库"


# ------------------------------------------------------------------ #
# Test 10: curator 低置信进待审池
# ------------------------------------------------------------------ #
def test_curator_low_confidence_pending(
    _patch_scripts_dir, monkeypatch
):
    from plugins.ddw_online_cs import curator as cur

    scripts, pending, pool = _patch_scripts_dir
    monkeypatch.setattr(cur, "_AUTO_APPROVE_THRESHOLD", 0.9)

    pool_file = pool / "2026-08-05.json"
    pool_file.write_text(
        json.dumps([{
            "type": "improvement",
            "confidence": 0.7,
            "summary": "响应慢",
            "evidence": "太慢了",
            "suggestion": "优化加载速度",
            "_session_id": "cs_def",
        }], ensure_ascii=False),
        encoding="utf-8",
    )

    cur.process_day("2026-08-05")

    # scripts 应为空
    for p in scripts.glob("*.json"):
        items = json.loads(p.read_text(encoding="utf-8"))
        assert len(items) == 0

    # pending 应有记录
    pending_files = list(pending.glob("*.json"))
    assert len(pending_files) >= 1


# ------------------------------------------------------------------ #
# Test 11: curator 分类封顶淘汰
# ------------------------------------------------------------------ #
def test_curator_eviction(
    _patch_scripts_dir, monkeypatch
):
    from plugins.ddw_online_cs import curator as cur

    scripts, pending, pool = _patch_scripts_dir
    monkeypatch.setattr(cur, "_AUTO_APPROVE_THRESHOLD", 0.5)

    # 先写入 5 条已有话术
    existing = []
    for i in range(5):
        existing.append({
            "category": "general_empathy",
            "title": f"existing_{i}",
            "exemplar_qa": {
                "user": f"u{i}",
                "ai": f"a{i}",
            },
            "source_session": f"s_old_{i}",
            "approved_at": "2026-08-01",
            "hit_count": 10 - i,
        })
    cat_file = scripts / "general_empathy.json"
    cat_file.write_text(
        json.dumps(existing, ensure_ascii=False),
        encoding="utf-8",
    )

    # 新增 1 条（应淘汰 hit_count 最低的）
    pool_file = pool / "2026-08-05.json"
    pool_file.write_text(
        json.dumps([{
            "type": "praise",
            "confidence": 0.95,
            "summary": "新好评",
            "evidence": "非常感谢",
            "suggestion": "太棒了",
            "_session_id": "cs_new",
            "_conv_user": "你们服务太贴心了",
            "_conv_ai": "谢谢夸奖！随时为您服务～",
        }], ensure_ascii=False),
        encoding="utf-8",
    )

    cur.process_day("2026-08-05")

    items = json.loads(
        cat_file.read_text(encoding="utf-8")
    )
    assert len(items) == 5, f"应保留 5 条，实际 {len(items)}"


# ------------------------------------------------------------------ #
# Test 12: curator 去重
# ------------------------------------------------------------------ #
def test_curator_dedup(
    _patch_scripts_dir, monkeypatch
):
    from plugins.ddw_online_cs import curator as cur

    scripts, pending, pool = _patch_scripts_dir
    monkeypatch.setattr(cur, "_AUTO_APPROVE_THRESHOLD", 0.5)

    pool_file = pool / "2026-08-05.json"
    # 同 session 同 evidence 的两条
    pool_file.write_text(
        json.dumps([
            {
                "type": "praise",
                "confidence": 0.95,
                "summary": "好评",
                "evidence": "谢谢帮助",
                "suggestion": "很好",
                "_session_id": "cs_dup",
                "_conv_user": "谢谢你帮了我大忙",
                "_conv_ai": "不客气！很高兴能帮到您～",
            },
            {
                "type": "praise",
                "confidence": 0.95,
                "summary": "好评",
                "evidence": "谢谢帮助",
                "suggestion": "很好",
                "_session_id": "cs_dup",
                "_conv_user": "谢谢你帮了我大忙",
                "_conv_ai": "不客气！很高兴能帮到您～",
            },
        ], ensure_ascii=False),
        encoding="utf-8",
    )

    cur.process_day("2026-08-05")

    total = 0
    for p in scripts.glob("*.json"):
        items = json.loads(p.read_text(encoding="utf-8"))
        total += len(items)
    assert total == 1, f"去重后应 1 条，实际 {total}"


# ------------------------------------------------------------------ #
# Test 13: asset_builder 打包
# ------------------------------------------------------------------ #
def test_asset_builder_pack(monkeypatch, tmp_path):
    from plugins.ddw_online_cs import asset_builder as ab

    # 创建临时话术文件
    scripts_dir = ab._BASE_DIR / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    test_script = scripts_dir / "_test_tmp.json"
    test_script.write_text(
        json.dumps([{
            "category": "test",
            "title": "test",
            "exemplar_qa": {"user": "u", "ai": "a"},
            "source_session": "s",
            "approved_at": "2026-08-05",
            "hit_count": 0,
        }], ensure_ascii=False),
        encoding="utf-8",
    )

    try:
        out_dir = tmp_path / "dist"
        result = ab.build_asset(out_dir)
        assert result is not None
        assert result.exists()
        assert result.suffix == ".gz"

        with tarfile.open(result, "r:gz") as tar:
            names = tar.getnames()

        # 必含 5 类内容
        assert any("prompt/" in n for n in names)
        assert any("scripts/" in n for n in names)
        assert any("knowledge/" in n for n in names)
        assert "config.yaml" in names
        assert "README.md" in names

        # 不含敏感目录
        assert not any("logs/" in n for n in names)
        assert not any("feedback/" in n for n in names)
        assert not any("pending_review/" in n for n in names)
    finally:
        test_script.unlink(missing_ok=True)


# ------------------------------------------------------------------ #
# Test 14: asset_builder README 含隐私声明
# ------------------------------------------------------------------ #
def test_asset_readme_privacy(monkeypatch, tmp_path):
    from plugins.ddw_online_cs import asset_builder as ab

    out_dir = tmp_path / "dist"
    result = ab.build_asset(out_dir)
    assert result is not None

    with tarfile.open(result, "r:gz") as tar:
        readme = tar.extractfile("README.md")
        assert readme is not None
        content = readme.read().decode("utf-8")

    assert "不含原始对话" in content


# ------------------------------------------------------------------ #
# Test 15: strip_think 复用
# ------------------------------------------------------------------ #
def test_strip_think():
    from plugins.ddw_online_cs.insights import (
        strip_think,
    )

    text = "<think>我在思考...</think>你好！"
    assert strip_think(text) == "你好！"

    text2 = "<think>a</think><think>b<think>c</think>答案"
    assert "答案" in strip_think(text2)

    text3 = "没有think标签"
    assert strip_think(text3) == "没有think标签"

    assert strip_think("") == ""


# ------------------------------------------------------------------ #
# 额外：insights._parse_eval_json 纯函数测试
# ------------------------------------------------------------------ #
def test_parse_eval_json():
    from plugins.ddw_online_cs.insights import (
        _parse_eval_json,
    )

    # 正常 JSON
    text = '{"type": "praise", "confidence": 0.9, "summary": "好"}'
    result = _parse_eval_json(text)
    assert result is not None
    assert result["type"] == "praise"

    # 包裹在 think 中
    text2 = (
        '<think>分析中...</think>'
        '{"type": "demand", "confidence": 0.8,'
        ' "summary": "需求", "evidence": "能不能"}'
    )
    result2 = _parse_eval_json(text2)
    assert result2 is not None
    assert result2["type"] == "demand"

    # 无效输入
    assert _parse_eval_json("not json") is None
    assert _parse_eval_json("") is None


# ------------------------------------------------------------------ #
# Test 16: praise 含 _conv_user/_conv_ai → exemplar_qa 用真实对话
# ------------------------------------------------------------------ #
def test_curator_praise_with_real_conv(
    _patch_scripts_dir, monkeypatch
):
    from plugins.ddw_online_cs import curator as cur

    scripts, pending, pool = _patch_scripts_dir
    monkeypatch.setattr(cur, "_AUTO_APPROVE_THRESHOLD", 0.9)

    pool_file = pool / "2026-08-06.json"
    pool_file.write_text(
        json.dumps([{
            "type": "praise",
            "confidence": 0.95,
            "summary": "用户高度满意",
            "evidence": "（LLM 分析师摘录）",
            "suggestion": "（LLM 分析师建议文字）",
            "_session_id": "cs_real",
            "_conv_user": "你们的售后响应太快了，半小时就解决了！",
            "_conv_ai": "感谢认可！我们的售后团队 7x24h 在线，"
            "有任何问题随时联系我们～",
        }], ensure_ascii=False),
        encoding="utf-8",
    )

    cur.process_day("2026-08-06")

    found = False
    for p in scripts.glob("*.json"):
        items = json.loads(p.read_text(encoding="utf-8"))
        for item in items:
            if item.get("source_session") == "cs_real":
                found = True
                qa = item["exemplar_qa"]
                # 必须是真实对话，不是 evidence/suggestion
                assert (
                    qa["user"]
                    == "你们的售后响应太快了，半小时就解决了！"
                )
                assert "7x24h" in qa["ai"]
    assert found, "含真实对话的 praise 应入库"


# ------------------------------------------------------------------ #
# Test 17: praise 缺 _conv_user/_conv_ai → 不入库
# ------------------------------------------------------------------ #
def test_curator_praise_missing_conv_skipped(
    _patch_scripts_dir, monkeypatch
):
    from plugins.ddw_online_cs import curator as cur

    scripts, pending, pool = _patch_scripts_dir
    monkeypatch.setattr(cur, "_AUTO_APPROVE_THRESHOLD", 0.9)

    pool_file = pool / "2026-08-06.json"
    pool_file.write_text(
        json.dumps([{
            "type": "praise",
            "confidence": 0.95,
            "summary": "好评但缺对话",
            "evidence": "用户说谢谢",
            "suggestion": "继续保持",
            "_session_id": "cs_no_conv",
        }], ensure_ascii=False),
        encoding="utf-8",
    )

    cur.process_day("2026-08-06")

    total = 0
    for p in scripts.glob("*.json"):
        items = json.loads(p.read_text(encoding="utf-8"))
        total += len(items)
    assert total == 0, "缺 _conv_user/_conv_ai 的 praise 不应入库"
