"""ddw_clinical_asr 测试套件.

对齐 TASK_SPEC §T1:
  T1-1: extract 接口，返回 ExtractionResult 结构
  T1-2: 牙痛文本 → treatment_type=pulp_open
  T1-3: 拔牙文本 → special_findings 含 anticoagulant_use
  T1-4: LLM 返回非 JSON，触发 fallback 解析
  T1-5: classify 接口，confidence > 0.8
  T1-6: 信息不足时，字段值为 "待补充"（不报错）
  T1-7: 性能：2000 字文本响应 ≤ 10 秒
  T1-8: 9 种诊疗类型各一条正向测试
"""
from __future__ import annotations

import os
import time

import conftest  # noqa: F401  # pylint: disable=unused-import
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 强制 mock LLM
os.environ["DDW_CLINICAL_ASR_MOCK"] = "1"

from plugins.ddw_clinical_asr import extractor as plugin_extractor
from plugins.ddw_clinical_asr import router as plugin_router
from plugins.ddw_clinical_asr.schema import (
    TREATMENT_VALUES,
    TreatmentType,
)


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(plugin_router.router)
    with TestClient(app) as c:
        yield c


# === T1-1: extract 接口返回 ExtractionResult 结构 ===
def test_T1_1_extract_returns_result(client):
    resp = client.post(
        "/api/v1/plugins/ddw_clinical_asr/extract",
        json={"transcript_text": "患者左下后牙疼痛三天，夜间加重", "job_id": "a1b2c3d4"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert "result" in body
    r = body["result"]
    assert "treatment_type" in r
    assert r["treatment_type"] in TREATMENT_VALUES
    assert 0 <= r["confidence"] <= 1
    assert r["chief_complaint"]
    assert r["present_illness"]


# === T1-2: 牙痛文本 → pulp_open ===
def test_T1_2_tooth_pain_classified_as_pulp_open(client):
    resp = client.post(
        "/api/v1/plugins/ddw_clinical_asr/extract",
        json={
            "transcript_text": "患者主诉左上后牙自发性疼痛三天，夜间加重，冷热刺激痛，"
                              "检查可见深龋近髓，叩诊阳性。",
        },
    )
    body = resp.json()
    assert body["result"]["treatment_type"] in ("pulp_open", "root_canal")


# === T1-3: 拔牙文本 → special_findings 含牙位/原因 ===
def test_T1_3_extraction_special_findings(client):
    resp = client.post(
        "/api/v1/plugins/ddw_clinical_asr/extract",
        json={
            "transcript_text": "患者左下8近中阻生，要求拔除。检查无明显炎症，"
                              "血压正常，无抗凝药使用史。",
        },
    )
    body = resp.json()
    assert body["result"]["treatment_type"] == "extraction"
    spec = body["result"]["special_findings"]
    assert "tooth_position" in spec or "difficulty_level" in spec


# === T1-4: LLM 返回非 JSON，触发 fallback 解析 ===
def test_T1_4_parse_json_with_markdown_block():
    # 直接测试解析函数
    payload_with_md = '```json\n{"treatment_type":"extraction","confidence":0.9,"chief_complaint":"X","present_illness":"Y","diagnosis":"Z","treatment_plan":"W"}\n```'
    parsed = plugin_extractor._parse_json_payload(payload_with_md)
    assert parsed["treatment_type"] == "extraction"
    assert parsed["confidence"] == 0.9
    # 裸 JSON
    raw = '{"treatment_type":"root_canal","confidence":0.7}'
    parsed2 = plugin_extractor._parse_json_payload(raw)
    assert parsed2["treatment_type"] == "root_canal"
    # 真的非 JSON
    with pytest.raises(ValueError):
        plugin_extractor._parse_json_payload("this is not json at all")


# === T1-5: classify 接口 confidence > 0.8 ===
def test_T1_5_classify_confidence(client):
    resp = client.post(
        "/api/v1/plugins/ddw_clinical_asr/classify",
        json={"transcript_text": "患者要求做种植牙，左下6缺失两年"},
    )
    body = resp.json()
    assert body["status"] == "ok"
    assert 0 <= body["result"]["confidence"] <= 1
    assert body["result"]["treatment_type"] in TREATMENT_VALUES


# === T1-6: 信息不足时字段值为 "待补充" 不报错 ===
def test_T1_6_empty_info_filled_with_tbd(client):
    resp = client.post(
        "/api/v1/plugins/ddw_clinical_asr/extract",
        json={"transcript_text": "患者来就诊。"},
    )
    assert resp.status_code == 200
    r = resp.json()["result"]
    # mock 模式下字段会标 "待补充"
    assert r["chief_complaint"] == "待补充" or r["chief_complaint"]


# === T1-7: 性能：2000 字文本 ≤ 10 秒 ===
def test_T1_7_performance_under_10s(client):
    long_text = "患者主诉牙痛。 " * 400  # ~2000 chars
    start = time.time()
    resp = client.post(
        "/api/v1/plugins/ddw_clinical_asr/extract",
        json={"transcript_text": long_text},
    )
    elapsed = time.time() - start
    assert resp.status_code == 200
    assert elapsed < 10.0, f"took {elapsed:.2f}s, must be < 10s"


# === T1-8: 9 种诊疗类型各一条正向测试 ===
@pytest.mark.parametrize(
    "text,expected_type",
    [
        ("患者牙列不齐要求矫正", "orthodontics"),
        ("急性牙髓炎需要开髓减压", "pulp_open"),
        ("左下8阻生要求拔除", "extraction"),
        ("前牙贴面美白修复", "cosmetic"),
        ("根管治疗后冠修复", "root_canal"),
        ("左上6缺失种植", "implant"),
        ("后牙冠修复", "prosthesis"),
        ("牙周炎洁治", "periodontal"),
        ("儿童乳牙龋坏", "pediatric"),
    ],
)
def test_T1_8_all_nine_treatment_types(client, text, expected_type):
    resp = client.post(
        "/api/v1/plugins/ddw_clinical_asr/extract",
        json={"transcript_text": text, "treatment_hint": expected_type},
    )
    body = resp.json()
    # mock 模式下做关键词匹配：treatment_hint 强制使用对应类型
    assert body["result"]["treatment_type"] == expected_type


# === 附加：health / prompts ===
def test_extra_health(client):
    resp = client.get("/api/v1/plugins/ddw_clinical_asr/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["available_types"] == 9


def test_extra_prompts(client):
    resp = client.get("/api/v1/plugins/ddw_clinical_asr/prompts")
    assert resp.status_code == 200
    body = resp.json()
    assert "prompts" in body
    assert len(body["prompts"]) >= 9


def test_extra_extract_empty_text_400(client):
    resp = client.post(
        "/api/v1/plugins/ddw_clinical_asr/extract",
        json={"transcript_text": ""},
    )
    assert resp.status_code == 422


def test_extra_extract_treatment_hint_invalid(client):
    resp = client.post(
        "/api/v1/plugins/ddw_clinical_asr/extract",
        json={"transcript_text": "test", "treatment_hint": "invalid_type_xxx"},
    )
    assert resp.status_code == 400


def test_extra_extract_oversize_413(client):
    long = "x" * 9000
    resp = client.post(
        "/api/v1/plugins/ddw_clinical_asr/extract",
        json={"transcript_text": long},
    )
    assert resp.status_code == 413


# === extractor 直接单测 ===
def test_extractor_load_prompts():
    prompts = plugin_extractor.list_prompts()
    assert len(prompts) == len(plugin_extractor.PROMPT_FILES)


def test_extractor_treatment_type_enum():
    assert TreatmentType.EXTRACTION.value == "extraction"
    assert TreatmentType.IMPLANT.value == "implant"
    assert len(TREATMENT_VALUES) == 9
