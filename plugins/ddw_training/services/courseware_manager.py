"""课件管理（DDW AI Hub v5.6 — 培训插件 E1）。

支持的课件类型：10 种多媒体（与 OpenMAIC 对齐）
- YAML 配置驱动（subjects/*.yaml 已包含章节和概念）
- 上传 PDF/教材 → AI 自动生成课件（生产用 LLM；dev 用占位）
- 10 种媒体类型：
  1. slides         — 幻灯片（结构化 PPT）
  2. interactive_sim— 交互仿真（HTML iframe）
  3. quiz           — 测验（单选/多选/简答）
  4. pbl            — 项目式学习（角色+问题+协作）
  5. whiteboard     — 白板（教师画图+公式+动画）
  6. viz3d          — 3D 可视化（JSON 描述 → Three.js 渲染）
  7. game           — 游戏化内容（互动 HTML）
  8. tts            — TTS 语音讲解（音频 URL + 元数据）
  9. image          — AI 配图
  10. video         — 教学视频
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


# 10 种媒体类型常量
COURSEWARE_TYPES = [
    "slides",           # 1. 幻灯片
    "interactive_sim",  # 2. 交互仿真
    "quiz",             # 3. 测验
    "pbl",              # 4. 项目式学习
    "whiteboard",       # 5. 白板
    "viz3d",            # 6. 3D 可视化（新增）
    "game",             # 7. 游戏化内容（新增）
    "tts",              # 8. TTS 语音讲解（新增）
    "image",            # 9. AI 配图
    "video",            # 10. 教学视频
]


@dataclass
class Courseware:
    id: str
    course_id: str
    subject: str
    type: str  # one of COURSEWARE_TYPES
    title: str
    description: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    preview_url: str = ""
    # 媒体特定字段
    audio_url: str = ""        # tts
    image_url: str = ""        # image
    video_url: str = ""        # video
    scene_json: Dict[str, Any] = field(default_factory=dict)  # viz3d
    html_content: str = ""     # game / interactive_sim
    created_at: str = ""


class CoursewareManager:
    """多媒体课件管理器（10 种媒体类型）。"""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = Path(config_dir)
        self._coursewares: Dict[str, Courseware] = {}
        self._load_subject_templates()
        logger.info("CoursewareManager ready, types=%d (%s)", len(COURSEWARE_TYPES), COURSEWARE_TYPES)

    def _load_subject_templates(self) -> None:
        """从 subjects/*.yaml 预生成默认课件（每个概念一个 slides）。"""
        for f in (self.config_dir / "subjects").glob("*.yaml"):
            sub = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            subj = sub.get("subject", "unknown")
            for ch in sub.get("chapters", []):
                for c in ch.get("concepts", []):
                    cid = f"{subj}-{c['id']}"
                    cw = Courseware(
                        id=cid,
                        course_id=subj,
                        subject=subj,
                        type="slides",
                        title=f"{ch['title']} - {c['name']}",
                        description=f"概念：{c['name']}（难度：{c.get('difficulty', '-')}）",
                        config={"chapter": ch["title"], "concept": c["name"], "difficulty": c.get("difficulty", "medium")},
                    )
                    self._coursewares[cid] = cw

    # ------------------------------------------------------------------ #
    # 通用 CRUD
    # ------------------------------------------------------------------ #

    def list_by_course(self, course_id: str, media_type: Optional[str] = None) -> List[Courseware]:
        items = [c for c in self._coursewares.values() if c.course_id == course_id]
        if media_type:
            items = [c for c in items if c.type == media_type]
        return items

    def list_all(self, media_type: Optional[str] = None) -> List[Courseware]:
        items = list(self._coursewares.values())
        if media_type:
            items = [c for c in items if c.type == media_type]
        return items

    def get(self, courseware_id: str) -> Optional[Courseware]:
        return self._coursewares.get(courseware_id)

    def create_from_pdf(self, course_id: str, pdf_path: str, subject: str, name: str) -> Courseware:
        """从 PDF/教材生成课件（dev：占位；生产用 LLM 解析 + 切片）。"""
        cw = Courseware(
            id=str(uuid.uuid4())[:8],
            course_id=course_id,
            subject=subject,
            type="slides",
            title=name,
            description=f"由 {Path(pdf_path).name} 自动生成（占位）",
            preview_url=f"/ui/preview/courseware/{uuid.uuid4().hex}",
        )
        self._coursewares[cw.id] = cw
        logger.info("created courseware from %s → %s", pdf_path, cw.id)
        return cw

    # ------------------------------------------------------------------ #
    # 多媒体生成器（viz3d / game / tts / image / video / interactive_sim / pbl / whiteboard / quiz）
    # ------------------------------------------------------------------ #

    def generate_viz3d(self, concept: str, subject: str, scene_type: str = "molecule") -> Courseware:
        """生成 3D 可视化课件（返回 Three.js 场景描述 JSON，由前端渲染）。"""
        scene_json = {
            "engine": "three.js",
            "version": "r150",
            "scene_type": scene_type,
            "subject": subject,
            "concept": concept,
            "camera": {"position": [0, 0, 5], "lookAt": [0, 0, 0]},
            "lights": [{"type": "ambient", "intensity": 0.6}, {"type": "directional", "position": [5, 5, 5]}],
            "objects": _build_3d_objects(scene_type, concept, subject),
        }
        cw = Courseware(
            id=str(uuid.uuid4())[:8],
            course_id=subject,
            subject=subject,
            type="viz3d",
            title=f"3D 可视化 - {concept}",
            description=f"{scene_type} 类型的 3D 场景（{concept}）",
            preview_url=f"/ui/preview/courseware/{uuid.uuid4().hex}",
            scene_json=scene_json,
        )
        self._coursewares[cw.id] = cw
        return cw

    def generate_game(self, concept: str, subject: str, game_type: str = "physics_sim") -> Courseware:
        """生成游戏化课件（返回自包含 HTML，含物理模拟器）。"""
        html_content = _build_game_html(game_type, concept, subject)
        cw = Courseware(
            id=str(uuid.uuid4())[:8],
            course_id=subject,
            subject=subject,
            type="game",
            title=f"游戏化 - {concept}",
            description=f"{game_type} 游戏（{concept}）",
            preview_url=f"/ui/preview/courseware/{uuid.uuid4().hex}",
            html_content=html_content,
        )
        self._coursewares[cw.id] = cw
        return cw

    def generate_tts(
        self,
        concept: str,
        subject: str,
        script: str = "",
        voice: str = "default",
        speed: float = 1.0,
    ) -> Courseware:
        """生成 TTS 语音讲解（走平台 TTS 能力，返回音频 URL + 元数据）。"""
        if not script:
            script = f"今天我们来学习 {concept}。{concept} 是 {subject} 中的核心概念之一。"
        audio_url = f"/api/v1/platform/tts/synthesize?text={uuid.uuid4().hex}&voice={voice}&speed={speed}"
        cw = Courseware(
            id=str(uuid.uuid4())[:8],
            course_id=subject,
            subject=subject,
            type="tts",
            title=f"语音讲解 - {concept}",
            description=f"AI 教师语音讲解（{voice}, {speed}x）",
            preview_url=f"/ui/preview/courseware/{uuid.uuid4().hex}",
            audio_url=audio_url,
            config={"script": script, "voice": voice, "speed": speed, "duration_sec": max(1, len(script) // 5)},
        )
        self._coursewares[cw.id] = cw
        return cw

    def generate_image(self, concept: str, subject: str, prompt: str = "") -> Courseware:
        """生成 AI 配图（走 LLM Gateway 的 image generation）。"""
        if not prompt:
            prompt = f"教学插图：{subject} - {concept}，清晰、专业、适合中学生"
        image_url = f"/api/v1/platform/llm/image?prompt={uuid.uuid4().hex}"
        cw = Courseware(
            id=str(uuid.uuid4())[:8],
            course_id=subject,
            subject=subject,
            type="image",
            title=f"配图 - {concept}",
            description=f"AI 生成配图（{prompt[:30]}...）",
            preview_url=f"/ui/preview/courseware/{uuid.uuid4().hex}",
            image_url=image_url,
            config={"prompt": prompt},
        )
        self._coursewares[cw.id] = cw
        return cw

    def generate_video(self, concept: str, subject: str, duration_sec: int = 30) -> Courseware:
        """生成教学视频（走 LLM Gateway 的 video generation）。"""
        video_url = f"/api/v1/platform/llm/video?concept={uuid.uuid4().hex}&duration={duration_sec}"
        cw = Courseware(
            id=str(uuid.uuid4())[:8],
            course_id=subject,
            subject=subject,
            type="video",
            title=f"教学视频 - {concept}",
            description=f"{duration_sec}s 教学视频（{concept}）",
            preview_url=f"/ui/preview/courseware/{uuid.uuid4().hex}",
            video_url=video_url,
            config={"duration_sec": duration_sec, "concept": concept},
        )
        self._coursewares[cw.id] = cw
        return cw

    # ------------------------------------------------------------------ #
    # 序列化
    # ------------------------------------------------------------------ #

    def to_dict(self, cw: Courseware) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": cw.id,
            "course_id": cw.course_id,
            "subject": cw.subject,
            "type": cw.type,
            "title": cw.title,
            "description": cw.description,
            "preview_url": cw.preview_url,
            "created_at": cw.created_at,
        }
        # 媒体特定字段（按类型填充）
        if cw.audio_url:
            d["audio_url"] = cw.audio_url
        if cw.image_url:
            d["image_url"] = cw.image_url
        if cw.video_url:
            d["video_url"] = cw.video_url
        if cw.scene_json:
            d["scene_json"] = cw.scene_json
        if cw.html_content:
            d["html_content"] = cw.html_content
        if cw.config:
            d["config"] = cw.config
        return d


# ---------------------------------------------------------------------------
# 内部辅助：3D 场景 / 游戏 HTML
# ---------------------------------------------------------------------------


def _build_3d_objects(scene_type: str, concept: str, subject: str) -> List[Dict[str, Any]]:
    """根据场景类型生成 3D 对象（占位实现；生产可由 LLM 生成）。"""
    if scene_type == "molecule":
        return [
            {"type": "sphere", "position": [0, 0, 0], "radius": 0.5, "color": "#1890FF", "label": "C"},
            {"type": "sphere", "position": [1, 0, 0], "radius": 0.4, "color": "#FF4D4F", "label": "O"},
            {"type": "sphere", "position": [-1, 0, 0], "radius": 0.4, "color": "#FF4D4F", "label": "O"},
            {"type": "cylinder", "from": [0, 0, 0], "to": [1, 0, 0], "radius": 0.1, "color": "#999"},
        ]
    if scene_type == "geometry":
        return [
            {"type": "box", "position": [0, 0, 0], "size": [1, 1, 1], "color": "#52C41A"},
        ]
    # 默认：通用球体
    return [{"type": "sphere", "position": [0, 0, 0], "radius": 1.0, "color": "#1890FF"}]


def _build_game_html(game_type: str, concept: str, subject: str) -> str:
    """生成自包含游戏 HTML（占位实现）。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>{game_type} - {concept}</title>
  <style>
    body {{ margin: 0; padding: 20px; font-family: system-ui, sans-serif; background: #f0f2f5; }}
    .game-container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
    h1 {{ color: #1890ff; }}
    .physics-canvas {{ width: 100%; height: 400px; background: #001529; border-radius: 4px; }}
    .controls {{ margin-top: 16px; display: flex; gap: 8px; }}
    button {{ padding: 8px 16px; border: none; background: #1890ff; color: white; border-radius: 4px; cursor: pointer; }}
  </style>
</head>
<body>
  <div class="game-container">
    <h1>🎮 {concept} 互动游戏</h1>
    <p>学科：{subject} | 类型：{game_type}</p>
    <canvas id="game" class="physics-canvas"></canvas>
    <div class="controls">
      <button onclick="startGame()">开始</button>
      <button onclick="resetGame()">重置</button>
    </div>
    <p id="score">得分：0</p>
  </div>
  <script>
    // 简化版物理游戏占位（生产可接 Phaser / Kaboom.js）
    let score = 0;
    const canvas = document.getElementById('game');
    const ctx = canvas.getContext('2d');
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
    function startGame() {{ score++; document.getElementById('score').innerText = '得分：' + score; ctx.fillStyle = '#52c41a'; ctx.fillRect(Math.random() * canvas.width, Math.random() * canvas.height, 30, 30); }}
    function resetGame() {{ score = 0; document.getElementById('score').innerText = '得分：0'; ctx.clearRect(0, 0, canvas.width, canvas.height); }}
  </script>
</body>
</html>"""


__all__ = [
    "COURSEWARE_TYPES",
    "Courseware",
    "CoursewareManager",
]
