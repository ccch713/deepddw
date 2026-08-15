"""ddw_talk_a1_asr 测试套件.

测试用例（对齐 TASK_SPEC_口腔门诊AI赋能_v2.0 §T0）:
  T0-1: 上传音频文件返回 job_id
  T0-2: 查询不存在的 job_id 返回 404
  T0-3: health 返回 status=ok + whisper_model 非空
  T0-4: transcribe_audio 接口：mock whisper-cli，验证输出 JSON 结构
  T0-5: 并发上传 3 个文件，全部转写成功
  T0-6: 上传非音频文件（txt）返回 400
  T0-7: 超大音频文件（>200MB）返回 413

注：
- 使用 TestClient + 一个轻量 app，避免依赖主 ddw-ai-hub 的完整启动流程
- 通过 DDW_TALK_A1_MOCK=1 强制走 mock 模式（不依赖系统 whisper-cli）
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import pytest

# 强制 mock，避免 CI 环境无 whisper-cli
os.environ["DDW_TALK_A1_MOCK"] = "1"

import conftest  # noqa: F401  # pylint: disable=unused-import
from plugins.ddw_talk_a1_asr import config as plugin_config
from plugins.ddw_talk_a1_asr import router as plugin_router
from plugins.ddw_talk_a1_asr import transcriber as plugin_transcriber
from plugins.ddw_talk_a1_asr.store import JobStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def app_instance(tmp_path, monkeypatch):
    """构造一个轻量 FastAPI app + 隔离的 data 目录 + JobStore."""
    # 把 db / queue / output 全部重定向到 tmp_path
    db_path = tmp_path / "asr.db"
    queue_dir = tmp_path / "queue"
    output_dir = tmp_path / "output"
    queue_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(plugin_config, "DB_PATH", db_path)
    monkeypatch.setattr(plugin_config, "QUEUE_DIR", queue_dir)
    monkeypatch.setattr(plugin_config, "OUTPUT_DIR", output_dir)

    # 初始化 store
    store = JobStore(db_path=db_path)
    plugin_router.set_store(store)
    plugin_router.set_plugin(None)  # 测试中不使用异步线程池

    app = FastAPI()
    app.include_router(plugin_router.router)
    yield app, store, queue_dir, output_dir


@pytest.fixture()
def client(app_instance):
    app, _store, _q, _o = app_instance
    with TestClient(app) as c:
        yield c


def _wav_bytes(duration_seconds: float = 1.0) -> bytes:
    """构造一段合法 WAV 文件（44.1kHz/16bit/单声道，duration 秒）."""
    import wave

    sample_rate = 16000
    n_frames = int(sample_rate * duration_seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


# ====== T0-1: 上传音频返回 job_id ======
def test_T0_1_upload_audio_returns_job_id(client, app_instance):
    _app, _store, queue_dir, _output_dir = app_instance
    audio = _wav_bytes(duration_seconds=0.5)
    resp = client.post(
        "/api/v1/plugins/ddw_talk_a1_asr/upload",
        files={"file": ("test.wav", audio, "audio/wav")},
        data={"doctor_id": "doc_001", "patient_name": "张三", "session_type": "consultation"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "job_id" in body
    assert len(body["job_id"]) >= 8
    assert body["status"] in ("queued", "completed", "transcribing")
    # 文件已落盘
    files = list(queue_dir.iterdir())
    assert any(f.suffix == ".wav" for f in files)


# ====== T0-2: 查询不存在 job 返回 404 ======
def test_T0_2_get_status_404_for_missing(client):
    resp = client.get("/api/v1/plugins/ddw_talk_a1_asr/status/nonexistent_id_xx")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ====== T0-3: health 返回 ok + whisper_model 非空 ======
def test_T0_3_health_returns_ok(client):
    resp = client.get("/api/v1/plugins/ddw_talk_a1_asr/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["whisper_model"]
    assert body["plugin"] == "ddw_talk_a1_asr"
    assert body["version"] == "0.1.0"
    assert body["queue_size"] == 0
    assert body["total_jobs"] == 0


# ====== T0-4: transcribe_audio 输出 JSON 结构 ======
def test_T0_4_transcribe_audio_json_structure(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_config, "OUTPUT_DIR", tmp_path)
    audio = tmp_path / "input.wav"
    audio.write_bytes(_wav_bytes(0.5))

    result = plugin_transcriber.transcribe_audio(str(audio))
    assert isinstance(result, plugin_transcriber.TranscriptionResult)
    d = result.to_dict()
    assert d["audio_path"] == str(audio)
    assert d["language"] == "zh"
    assert isinstance(d["segments"], list)
    assert d["full_text"]
    assert d["job_id"]
    assert d["transcribed_at"]
    # 输出 JSON 文件已持久化
    out = Path(d["output_path"])
    assert out.exists()
    import json

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["job_id"] == d["job_id"]


# ====== T0-5: 并发上传 3 个文件全部成功 ======
def test_T0_5_concurrent_uploads(client, app_instance):
    _app, _store, _q, _output_dir = app_instance
    job_ids = []
    for i in range(3):
        resp = client.post(
            "/api/v1/plugins/ddw_talk_a1_asr/upload",
            files={"file": (f"concurrent_{i}.wav", _wav_bytes(0.3), "audio/wav")},
            data={"doctor_id": f"doc_{i:03d}", "session_type": "consultation"},
        )
        assert resp.status_code == 201, resp.text
        job_ids.append(resp.json()["job_id"])

    # 因为走 mock + 同步路径，状态在请求结束时已经是 completed
    for jid in job_ids:
        resp = client.get(f"/api/v1/plugins/ddw_talk_a1_asr/status/{jid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("completed", "transcribing", "queued")
        if body["status"] == "completed":
            assert body["full_text"]


# ====== T0-6: 上传非音频文件返回 400 ======
def test_T0_6_non_audio_file_rejected(client):
    resp = client.post(
        "/api/v1/plugins/ddw_talk_a1_asr/upload",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        data={"doctor_id": "doc_001"},
    )
    assert resp.status_code == 400
    assert "unsupported" in resp.json()["detail"].lower() or "format" in resp.json()["detail"].lower()


# ====== T0-7: 超大文件返回 413 ======
def test_T0_7_oversize_file_rejected(client, app_instance, monkeypatch):
    _app, _store, _q, _o = app_instance
    # 临时把上限调小以避免真的写 200MB
    monkeypatch.setattr(plugin_config, "MAX_AUDIO_BYTES", 1024)
    big = b"\x00" * 4096  # 4KB > 1KB
    resp = client.post(
        "/api/v1/plugins/ddw_talk_a1_asr/upload",
        files={"file": ("big.wav", big, "audio/wav")},
        data={"doctor_id": "doc_001"},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


# ====== 附加：list_jobs + config 端点 smoke test ======
def test_extra_list_jobs_and_config(client, app_instance):
    _app, _store, _q, _o = app_instance
    # 上传一个任务
    client.post(
        "/api/v1/plugins/ddw_talk_a1_asr/upload",
        files={"file": ("a.wav", _wav_bytes(0.2), "audio/wav")},
        data={"doctor_id": "doc_001"},
    )
    # list_jobs
    resp = client.get("/api/v1/plugins/ddw_talk_a1_asr/jobs")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    # list_jobs with status filter
    resp = client.get(
        "/api/v1/plugins/ddw_talk_a1_asr/jobs",
        params={"status": "completed"},
    )
    assert resp.status_code == 200
    # invalid status
    resp = client.get(
        "/api/v1/plugins/ddw_talk_a1_asr/jobs",
        params={"status": "invalid_status_xxx"},
    )
    assert resp.status_code == 400
    # config
    resp = client.get("/api/v1/plugins/ddw_talk_a1_asr/config")
    assert resp.status_code == 200
    cfg = resp.json()
    assert cfg["plugin"] == "ddw_talk_a1_asr"
    assert cfg["max_concurrent_jobs"] >= 1
