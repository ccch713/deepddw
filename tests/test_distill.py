"""R4-3 / R4-4（DSH for Teams）：记忆+KB 蒸馏测试。

验收：DistillationTarget 接口注册；family 简化版去重写入 family:default；
team 完整版 LLM→规则降级写入 team:default；solo 不可用。
"""

from __future__ import annotations

import os

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-distill-token")

import pytest  # noqa: E402

from core.api import distill as distill_api  # noqa: E402
from core.api import teams as teams_api  # noqa: E402
from core.knowledge import (  # noqa: E402
    memory_log_append,
    memory_logs_recent,
    reset_conn_pool,
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """独立库 + 重置注册表 + 默认 team 模式。"""
    from core import knowledge as kb

    monkeypatch.setattr(kb, "_db_path", lambda: tmp_path / "kb.db")
    monkeypatch.setattr(teams_api, "_db_path", lambda: tmp_path / "teams.db")
    monkeypatch.setattr("core.config.get_deployment_mode", lambda: "team")
    distill_api.reset_distillation_registry()
    # 重新注册内置目标
    distill_api.register_distillation(distill_api.DistillationTarget(
        mode="family", name="family:default",
        source_filter="all", distill_fn=distill_api.distill_memory_family,
    ))
    distill_api.register_distillation(distill_api.DistillationTarget(
        mode="team", name="team:default",
        source_filter="members_only", distill_fn=distill_api.distill_memory_team,
    ))
    reset_conn_pool()
    yield
    distill_api.reset_distillation_registry()
    reset_conn_pool()


def _add_members(monkeypatch):
    """在 team 模式下创建 2 个成员并写入个人记忆。"""
    monkeypatch.setattr("core.config.get_deployment_mode", lambda: "team")
    inv = teams_api.create_invite()
    m1 = teams_api.register_member(inv["invite_code"], "成员A", "dev-a")
    inv2 = teams_api.create_invite()
    m2 = teams_api.register_member(inv2["invite_code"], "成员B", "dev-b")
    ws1 = f"member:{m1['member_id']}"
    ws2 = f"member:{m2['member_id']}"
    memory_log_append("成员A的日志1", auto=True, workspace=ws1)
    memory_log_append("成员A的日志2", auto=True, workspace=ws1)
    memory_log_append("成员B的日志1", auto=True, workspace=ws2)
    return ws1, ws2


def test_distillation_target_registry():
    """DistillationTarget 注册正确（mode 与目标对应）。"""
    targets = distill_api.get_distillation_targets("team")
    assert len(targets) == 1 and targets[0].name == "team:default"
    targets_f = distill_api.get_distillation_targets("family")
    assert len(targets_f) == 1
    assert distill_api.get_distillation_targets("solo") == []


async def test_family_distill_dedup(monkeypatch, tmp_path):
    """family 简化版：成员记忆 → 去重合并 → family:default。"""
    import asyncio

    monkeypatch.setattr("core.config.get_deployment_mode", lambda: "family")
    ws1, ws2 = _add_members(monkeypatch)
    result = await distill_api.distill_memory_family(recent_days=1)
    assert result["ok"] is True and result["mode"] == "family"
    assert result["wrote"] >= 2  # 至少 2 条非重复
    # family:default 空间有数据
    shared = memory_logs_recent(days=1, workspace="family:default").get("results", [])
    contents = [r["content"] for r in shared]
    assert "成员A的日志1" in contents or "成员A的日志2" in contents
    assert "成员B的日志1" in contents


async def test_team_distill_rule_fallback(monkeypatch, tmp_path):
    """team 完整版：LLM 不可用 → 规则降级（仍写入 team:default）。"""
    from core.llm_gateway.gateway import chat as _gw

    async def boom(messages, **kwargs):
        raise RuntimeError("no LLM")

    monkeypatch.setattr(_gw, "__call__", boom)
    ws1, ws2 = _add_members(monkeypatch)
    result = await distill_api.distill_memory_team(recent_days=1)
    assert result["ok"] is True and result["mode"] == "team"
    assert result["method"] == "rule"
    assert result["wrote"] >= 1
    shared = memory_logs_recent(days=1, workspace="team:default").get("results", [])
    assert len(shared) >= 1


def test_solo_no_distill(monkeypatch):
    """solo 模式：蒸馏端点拒绝。"""
    monkeypatch.setattr("core.config.get_deployment_mode", lambda: "solo")
    assert distill_api.get_distillation_targets("solo") == []
