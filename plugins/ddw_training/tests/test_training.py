"""DDW 培训插件单元测试（pytest）。"""

from __future__ import annotations

from pathlib import Path


from plugins.ddw_training.services.assessment_engine import AssessmentEngine
from plugins.ddw_training.services.courseware_manager import (
    COURSEWARE_TYPES,
    CoursewareManager,
)
from plugins.ddw_training.services.progress_tracker import ProgressTracker
from plugins.ddw_training.services.socratic_engine import SessionState, SocraticEngine

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


# ---------------------------------------------------------------------------
# Socratic
# ---------------------------------------------------------------------------


def test_socratic_engine_loads():
    eng = SocraticEngine(CONFIG_DIR)
    assert len(eng._moves) == 6
    assert len(eng._vignettes) == 12
    assert "physics" in eng.subjects
    assert "chemistry" in eng.subjects


def test_socratic_session_progression():
    eng = SocraticEngine(CONFIG_DIR)
    s = SessionState(session_id="t1", user_id=1, tenant_id=1, course_id="p", subject="physics")
    out = eng.start_session(s)
    assert out["move"] == 1
    assert s.current_move == 1
    assert len(s.vignettes_used) == 1

    # 走完 6 步
    import asyncio
    for step in range(6):
        r = asyncio.run(eng.next_turn(s, f"我的回答是 {step}"))
        assert "content" in r
    assert s.status == "completed"
    assert len(s.moves_completed) == 6


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------


def test_assessment_generate_and_grade():
    a = AssessmentEngine()
    qs = a.generate_quiz("physics", n=2)
    assert len(qs) == 2
    # 数值题
    r = a.grade(qs[0], "5")
    assert r["score"] >= 0
    # 文本题
    r2 = a.grade({"type": "text", "answer": "氮气"}, "氮气")
    assert r2["correct"] is True


def test_assessment_overall_grade():
    a = AssessmentEngine()
    g = a.overall_grade([
        {"score": 0.9}, {"score": 0.8}, {"score": 0.7},
    ])
    assert g["score"] >= 0.7
    assert g["grade"] in ("A", "B")


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


def test_progress_tracker_summary():
    pt = ProgressTracker()
    pt.record_session({"session_id": "s1", "user_id": 7, "duration_sec": 600, "status": "completed"})
    pt.record_assessment({"user_id": 7, "score": 0.85, "grade": "B", "by_dimension": {"conceptual_clarity": 0.8}})
    summary = pt.user_summary(7)
    assert summary["sessions_total"] == 1
    assert summary["assessments_total"] == 1
    assert summary["duration_minutes"] == 10
    assert summary["latest_grade"] == "B"


# ---------------------------------------------------------------------------
# Courseware
# ---------------------------------------------------------------------------


def test_courseware_templates_loaded():
    cm = CoursewareManager(CONFIG_DIR)
    items = cm.list_by_course("physics")
    assert len(items) > 0
    for it in items:
        assert it.type in COURSEWARE_TYPES
    d = cm.to_dict(items[0])
    assert "id" in d and "title" in d


# ---------------------------------------------------------------------------
# 多媒体生成器（v0.1.1 新增 5 种类型）
# ---------------------------------------------------------------------------


def test_courseware_types_count():
    """COURSEWARE_TYPES 现在应该有 10 种。"""
    assert len(COURSEWARE_TYPES) == 10
    for t in ("slides", "interactive_sim", "quiz", "pbl", "whiteboard",
              "viz3d", "game", "tts", "image", "video"):
        assert t in COURSEWARE_TYPES, f"missing media type: {t}"


def test_generate_viz3d():
    cm = CoursewareManager(CONFIG_DIR)
    cw = cm.generate_viz3d("水分子", "chemistry", scene_type="molecule")
    assert cw.type == "viz3d"
    assert cw.subject == "chemistry"
    assert cw.scene_json.get("engine") == "three.js"
    assert cw.scene_json.get("scene_type") == "molecule"
    assert len(cw.scene_json.get("objects", [])) > 0
    assert cm.get(cw.id) is cw


def test_generate_game():
    cm = CoursewareManager(CONFIG_DIR)
    cw = cm.generate_game("自由落体", "physics", game_type="physics_sim")
    assert cw.type == "game"
    assert "<!DOCTYPE html>" in cw.html_content
    assert "自由落体" in cw.html_content
    assert "physics_sim" in cw.html_content


def test_generate_tts():
    cm = CoursewareManager(CONFIG_DIR)
    cw = cm.generate_tts("牛顿第二定律", "physics", voice="male-qn-qingse", speed=1.2)
    assert cw.type == "tts"
    assert cw.audio_url.startswith("/api/v1/platform/tts/synthesize")
    assert cw.config["voice"] == "male-qn-qingse"
    assert cw.config["speed"] == 1.2
    assert cw.config["duration_sec"] >= 1


def test_generate_image():
    cm = CoursewareManager(CONFIG_DIR)
    cw = cm.generate_image("分子结构", "chemistry", prompt="教学配图：分子结构示意")
    assert cw.type == "image"
    assert cw.image_url.startswith("/api/v1/platform/llm/image")
    assert "分子结构" in cw.config["prompt"]


def test_generate_video():
    cm = CoursewareManager(CONFIG_DIR)
    cw = cm.generate_video("氧气制取", "chemistry", duration_sec=60)
    assert cw.type == "video"
    assert cw.video_url.startswith("/api/v1/platform/llm/video")
    assert cw.config["duration_sec"] == 60


def test_list_by_course_with_media_type_filter():
    cm = CoursewareManager(CONFIG_DIR)
    # 生成两个 viz3d
    cm.generate_viz3d("概念A", "physics", scene_type="molecule")
    cm.generate_viz3d("概念B", "physics", scene_type="geometry")
    # 过滤 slides（应该都是自动生成的）
    slides = cm.list_by_course("physics", media_type="slides")
    assert all(c.type == "slides" for c in slides)
    # 过滤 viz3d（应该 2 个）
    viz3d = cm.list_by_course("physics", media_type="viz3d")
    assert len(viz3d) == 2
    assert all(c.type == "viz3d" for c in viz3d)


def test_to_dict_contains_media_specific_fields():
    cm = CoursewareManager(CONFIG_DIR)
    cw_viz = cm.generate_viz3d("test", "physics")
    d = cm.to_dict(cw_viz)
    assert "scene_json" in d
    assert d["type"] == "viz3d"

    cw_tts = cm.generate_tts("test", "physics")
    d_tts = cm.to_dict(cw_tts)
    assert "audio_url" in d_tts
    assert d_tts["type"] == "tts"

    cw_img = cm.generate_image("test", "physics")
    d_img = cm.to_dict(cw_img)
    assert "image_url" in d_img

    cw_vid = cm.generate_video("test", "physics")
    d_vid = cm.to_dict(cw_vid)
    assert "video_url" in d_vid

    cw_game = cm.generate_game("test", "physics")
    d_game = cm.to_dict(cw_game)
    assert "html_content" in d_game
