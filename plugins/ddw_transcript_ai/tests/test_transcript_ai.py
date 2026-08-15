from __future__ import annotations

"""DDW 转写与结构化插件测试用例（7 个，覆盖 health + 4 个 AI 能力 + 边界）。

设计原则：
- 使用 echo backend LLM（无外部依赖、CI 友好）
- 断言保持宽松：端点返回 200、字段存在、类型正确、echo 模式下内容合理
- 因为 echo backend 返回 "[echo] ..." 固定格式，**不**对 LLM 输出做严格匹配
"""

import pytest

# ===========================================================================
# 1. 健康检查
# ===========================================================================


@pytest.mark.asyncio
async def test_health(client):
    """/health 返回 200 且字段完整。"""
    resp = await client.get("/api/v1/plugins/ddw-transcript-ai/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plugin"] == "ddw-transcript-ai"
    assert body["version"] == "1.0.0"
    assert body["status"] == "ok"
    # backend 字段必填（用于运维排查）
    assert "backend" in body
    assert isinstance(body["backend"], str)
    assert body["backend"] != ""


# ===========================================================================
# 2. 转写
# ===========================================================================


@pytest.mark.asyncio
async def test_transcribe(client):
    """录音转写：返回 transcript 字段、字段类型正确、长度合理。"""
    req = {
        "file_url": "https://cdn.example.com/voice/2026-08-15/call-001.m4a",
        "language": "zh-CN",
    }
    resp = await client.post(
        "/api/v1/plugins/ddw-transcript-ai/transcript/transcribe", json=req
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 字段完整性
    assert body["file_url"] == req["file_url"]
    assert body["language"] == "zh-CN"
    assert isinstance(body["transcript"], str)
    assert len(body["transcript"]) > 0
    assert isinstance(body["transcript_length"], int)
    assert body["transcript_length"] == len(body["transcript"])
    assert isinstance(body["backend"], str)
    assert isinstance(body["model"], str)


# ===========================================================================
# 3. 摘要（短文本）
# ===========================================================================


@pytest.mark.asyncio
async def test_summarize_short(client):
    """短文本摘要：max_length=50，原文 ~100 字，echo 模式截断到 50 字。"""
    text = (
        "客户经理拜访锐果互动公司，介绍 DDW AI 底座的核心能力。"
        "客户对智能问答和知识库功能很感兴趣，约下周技术交流。"
        "本次拜访还涉及价格区间、合同模板、SLA 条款等议题。"
    )
    req = {"text": text, "max_length": 50}
    resp = await client.post(
        "/api/v1/plugins/ddw-transcript-ai/transcript/summarize", json=req
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["summary"], str)
    assert len(body["summary"]) > 0
    assert body["original_length"] == len(text)
    # summary_length 应 <= max_length + 1（ellipsis 占 1 字符）
    assert body["summary_length"] <= 51
    # 压缩比 = summary/original（保留 4 位小数，故断言容差 1e-4）
    assert 0.0 <= body["compression_ratio"] <= 1.0
    assert (
        abs(body["compression_ratio"] - body["summary_length"] / body["original_length"])
        < 1e-4
    )


# ===========================================================================
# 4. 摘要（长文本）
# ===========================================================================


@pytest.mark.asyncio
async def test_summarize_long(client):
    """长文本摘要：原文 > 1000 字，max_length=200。"""
    paragraphs = [
        "今天下午我们拜访了某大型制造业客户的 CIO 王总，深入讨论了 DDW AI 底座在该客户集团内的落地路径。",
        "客户目前已经完成了 ERP、MES、PLM 等核心系统的建设，正在向数据中台和 AI 中台演进。",
        "客户对多租户隔离、本地化部署、知识库增强检索（RAG）非常关注，希望我们提供 PoC 验证。",
        "价格方面，客户希望按调用量计费，而非传统的 License 模式；我们记录了客户对 30 万/年预算上限的接受度。",
        "下一步我们将安排技术团队与客户架构组对接，预计下周完成第一次技术 PoC 演示。",
    ]
    text = "\n".join(paragraphs) * 5  # ~1500 字
    req = {"text": text, "max_length": 200}
    resp = await client.post(
        "/api/v1/plugins/ddw-transcript-ai/transcript/summarize", json=req
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["original_length"] == len(text)
    # echo 模式：截断到 200 字（带 ellipsis）
    assert body["summary_length"] <= 201
    assert body["summary_length"] > 0
    # 压缩比应明显小于 1
    assert body["compression_ratio"] < 0.5


# ===========================================================================
# 5. 待办提取
# ===========================================================================


@pytest.mark.asyncio
async def test_extract_todos(client):
    """待办提取：返回 todos 列表（echo 模式可能为空，类型必须正确）。"""
    text = (
        "与锐果互动张总沟通后达成以下共识：\n"
        "1. 下周一前发送产品白皮书到客户邮箱；\n"
        "2. 安排技术团队与客户架构组对接；\n"
        "3. 准备 PoC 演示方案，含 RAG 场景；\n"
        "4. 提交 30 万/年预算明细。"
    )
    resp = await client.post(
        "/api/v1/plugins/ddw-transcript-ai/transcript/extract-todos",
        json={"text": text},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # todos 字段必须是 list
    assert isinstance(body["todos"], list)
    # count 必须 == len(todos)
    assert body["count"] == len(body["todos"])
    # 其它字段
    assert isinstance(body["backend"], str)
    assert isinstance(body["model"], str)


# ===========================================================================
# 6. 实体抽取（正常文本）
# ===========================================================================


@pytest.mark.asyncio
async def test_extract_entities(client):
    """实体抽取：返回 4 类实体（echo 模式可能为空），字段类型正确。"""
    text = (
        "锐果互动公司的张经理拜访了华为技术有限公司。"
        "双方约定 2026-08-15 进行技术交流，预算 30 万人民币。"
        "项目负责人是李工程师。"
    )
    resp = await client.post(
        "/api/v1/plugins/ddw-transcript-ai/transcript/extract-entities",
        json={"text": text},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 4 个列表字段 + total_count
    for k in ("companies", "people", "amounts", "dates"):
        assert k in body, f"missing field: {k}"
        assert isinstance(body[k], list), f"{k} must be list, got {type(body[k])}"
        for item in body[k]:
            assert isinstance(item, str)
            assert len(item) > 0
    # total_count = 4 类合计
    expected_total = (
        len(body["companies"])
        + len(body["people"])
        + len(body["amounts"])
        + len(body["dates"])
    )
    assert body["total_count"] == expected_total
    assert body["total_count"] >= 0


# ===========================================================================
# 7. 实体抽取（空 / 极短文本）
# ===========================================================================


@pytest.mark.asyncio
async def test_extract_entities_empty(client):
    """实体抽取：极短/无实体文本应返回空列表 + total_count=0。"""
    text = "你好。"
    resp = await client.post(
        "/api/v1/plugins/ddw-transcript-ai/transcript/extract-entities",
        json={"text": text},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 4 类都应是 list
    for k in ("companies", "people", "amounts", "dates"):
        assert isinstance(body[k], list)
    # total_count == 0（echo 模式必然为 0；真实 LLM 也应识别不到实体）
    assert body["total_count"] == 0
    assert body["companies"] == []
    assert body["people"] == []
    assert body["amounts"] == []
    assert body["dates"] == []


# ===========================================================================
# 8. (补充) 错误输入：缺 file_url / text
# ===========================================================================


@pytest.mark.asyncio
async def test_validation_missing_text(client):
    """缺必填 text 字段应返回 422 (Pydantic ValidationError)。"""
    # summarize 缺 text
    resp = await client.post(
        "/api/v1/plugins/ddw-transcript-ai/transcript/summarize",
        json={"max_length": 100},
    )
    assert resp.status_code == 422
    # transcribe 缺 file_url
    resp2 = await client.post(
        "/api/v1/plugins/ddw-transcript-ai/transcript/transcribe",
        json={"language": "zh-CN"},
    )
    assert resp2.status_code == 422


# ===========================================================================
# 9. (补充) 服务层单元测试 —— echo backend 行为
# ===========================================================================


@pytest.mark.asyncio
async def test_service_echo_behavior(service):
    """直接测服务层：echo backend 下 transcribe / summarize 行为可预测。"""
    # transcribe
    r = await service.transcribe("https://x/y/test.m4a", "zh-CN")
    assert r["file_url"].endswith("test.m4a")
    assert r["transcript"], "echo backend 应返回非空占位转写文本"
    # summarize: echo 模式截断
    r2 = await service.summarize("a" * 500, max_length=50)
    assert r2["summary_length"] <= 51
    assert r2["original_length"] == 500
    # extract_todos: echo 模式返回空 list
    r3 = await service.extract_todos("随便聊了聊")
    assert r3["todos"] == []
    assert r3["count"] == 0
    # extract_entities: echo 模式 4 类都空
    r4 = await service.extract_entities("随便聊了聊")
    assert r4["total_count"] == 0
    assert r4["companies"] == []


# ===========================================================================
# 10. (补充) 解析辅助：宽松 JSON 解析对 echo 输出也安全
# ===========================================================================


def test_safe_parse_json_handles_garbage():
    """_safe_parse_json 对各种格式都要安全（不抛异常）。"""
    from plugins.ddw_transcript_ai.services import _safe_parse_json

    # 1) JSON 代码块
    assert _safe_parse_json('```json\n["a", "b"]\n```') == ["a", "b"]
    # 2) 裸 JSON
    assert _safe_parse_json('{"a": 1}') == {"a": 1}
    # 3) 裸数组
    assert _safe_parse_json('["x", "y"]') == ["x", "y"]
    # 4) Python literal（ast 兜底）
    assert _safe_parse_json("{'a': 1}") == {"a": 1}
    # 5) 纯文本 -> None
    assert _safe_parse_json("hello world") is None
    # 6) echo 输出 -> None
    assert _safe_parse_json("[echo] kb='...' prompt='...'") is None
    # 7) 空字符串 -> None
    assert _safe_parse_json("") is None
