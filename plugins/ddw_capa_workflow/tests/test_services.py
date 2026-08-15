"""Tests for CAPA Workflow service."""
import datetime

import pytest


class TestCAPACreation:
    def test_create_capa(self, service):
        capa = service.create_capa(
            title="发酵温度偏差导致微生物超标",
            description="批次20260801-A发酵温度偏高2°C持续30分钟",
            source="deviation", severity="major"
        )
        assert capa.id is not None
        assert capa.capa_number.startswith("CAPA-")
        assert capa.status == "open"

    def test_capa_number_auto_increment(self, service):
        c1 = service.create_capa(title="T1", description="D1", source="deviation")
        c2 = service.create_capa(title="T2", description="D2", source="complaint")
        assert c1.capa_number != c2.capa_number

    def test_list_capas(self, service):
        service.create_capa(title="T1", description="D1", source="deviation")
        service.create_capa(title="T2", description="D2", source="complaint")
        capas = service.list_capas()
        assert len(capas) == 2

    def test_list_filter_by_status(self, service):
        capa = service.create_capa(title="T1", description="D1", source="deviation")
        service.create_capa(title="T2", description="D2", source="complaint")
        service.transition(capa.id, "investigation")
        open_capas = service.list_capas(status="open")
        inv_capas = service.list_capas(status="investigation")
        assert len(open_capas) == 1
        assert len(inv_capas) == 1


class TestStateTransitions:
    def test_valid_transition_open_to_investigation(self, service):
        capa = service.create_capa(title="T", description="D", source="audit")
        updated = service.transition(capa.id, "investigation", "开始调查")
        assert updated.status == "investigation"

    def test_invalid_transition_raises(self, service):
        capa = service.create_capa(title="T", description="D", source="audit")
        with pytest.raises(ValueError, match="Invalid transition"):
            service.transition(capa.id, "closed")

    def test_full_lifecycle(self, service):
        capa = service.create_capa(title="Full lifecycle test", description="D", source="deviation")
        service.transition(capa.id, "investigation")
        service.add_investigation(capa.id, "根本原因是SOP不完善")
        service.transition(capa.id, "action")
        service.add_actions(capa.id, corrective="更新SOP", preventive="定期评审")
        service.transition(capa.id, "verification")
        service.add_effectiveness_check(capa.id, "30天验证有效")
        service.transition(capa.id, "closed", "CAPA关闭")
        final = service.get_capa(capa.id)
        assert final.status == "closed"
        assert final.closed_at is not None

    def test_reopen_from_verification(self, service):
        capa = service.create_capa(title="T", description="D", source="audit")
        service.transition(capa.id, "investigation")
        service.transition(capa.id, "action")
        service.transition(capa.id, "verification")
        service.transition(capa.id, "investigation", "验证失败，重新调查")
        assert capa.status == "investigation"

    def test_history_tracked(self, service):
        capa = service.create_capa(title="T", description="D", source="audit")
        service.transition(capa.id, "investigation", "开始调查")
        history = service.get_history(capa.id)
        assert len(history) >= 2  # creation + transition


class TestInvestigationAndActions:
    def test_add_investigation(self, service):
        capa = service.create_capa(title="T", description="D", source="audit")
        service.transition(capa.id, "investigation")
        updated = service.add_investigation(capa.id, "温度传感器校准过期", method="5why")
        assert updated.root_cause == "温度传感器校准过期"
        assert updated.root_cause_method == "5why"

    def test_add_actions(self, service):
        capa = service.create_capa(title="T", description="D", source="audit")
        updated = service.add_actions(capa.id, corrective="立即校准", preventive="建立校准提醒")
        assert "校准" in updated.corrective_action


class TestAnalytics:
    def test_statistics(self, service):
        service.create_capa(title="T1", description="D1", source="deviation", severity="critical")
        service.create_capa(title="T2", description="D2", source="complaint", severity="minor")
        stats = service.get_statistics()
        assert stats["total"] == 2
        assert stats["by_severity"]["critical"] == 1

    def test_overdue_capas(self, service):
        past = datetime.datetime.utcnow() - datetime.timedelta(days=10)
        capa = service.create_capa(title="Overdue", description="D", source="audit",
                                    due_date=past)
        overdue = service.get_overdue_capas()
        assert len(overdue) == 1
