"""培训插件 services 包入口。"""

from core.events.bus import get_bus
from plugins.ddw_training.services.assessment_engine import AssessmentEngine
from plugins.ddw_training.services.courseware_manager import (
    COURSEWARE_TYPES,
    Courseware,
    CoursewareManager,
)
from plugins.ddw_training.services.progress_tracker import ProgressTracker
from plugins.ddw_training.services.socratic_engine import SessionState, SocraticEngine

# 事件名常量
EVENT_TRAINING_COMPLETED = "training.session.completed"
EVENT_ASSESSMENT_COMPLETED = "training.assessment.completed"


def publish_training_completed(payload: dict) -> None:
    get_bus().publish_threadsafe(EVENT_TRAINING_COMPLETED, payload)


def publish_assessment_completed(payload: dict) -> None:
    get_bus().publish_threadsafe(EVENT_ASSESSMENT_COMPLETED, payload)


__all__ = [
    "AssessmentEngine",
    "COURSEWARE_TYPES",
    "Courseware",
    "CoursewareManager",
    "EVENT_ASSESSMENT_COMPLETED",
    "EVENT_TRAINING_COMPLETED",
    "ProgressTracker",
    "SessionState",
    "SocraticEngine",
    "publish_assessment_completed",
    "publish_training_completed",
]
