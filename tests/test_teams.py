"""R4-0 / R4-1（DSH for Teams）：部署模式 + 成员系统测试。

验收：未配置 → 默认 solo（v0.3.0 行为）；mode 可写入/读取；family/team
启用成员系统；邀请码创建/注册（过期/次数校验）；直接添加；吊销；
设备↔成员绑定与重连识别；solo 模式成员端点不启用。
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("DDW_ACCESS_TOKEN", "test-teams-token")

import pytest  # noqa: E402

from core.api import teams as teams_api  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """独立库 + 默认 solo 模式 + 重置 settings 单例。"""
    monkeypatch.setattr(teams_api, "_db_path", lambda: tmp_path / "teams.db")
    monkeypatch.setattr(teams_api, "get_deployment_mode", lambda: "solo")
    monkeypatch.setattr(teams_api, "members_enabled", lambda: False)
    # 重置 settings 单例（避免前序测试写入的 config 污染）
    import core.config as cfg
    monkeypatch.setattr(cfg, "_settings", None)
    yield


def _set_mode(monkeypatch, mode: str) -> None:
    monkeypatch.setattr("core.config.get_deployment_mode", lambda: mode)


# ---------------------------------------------------------------------------
# R4-0 部署模式
# ---------------------------------------------------------------------------


def test_default_mode_solo(monkeypatch):
    """未配置 → 默认 solo（向后兼容）。"""
    import core.config as cfg
    monkeypatch.delenv("DDW_DEPLOYMENT_MODE", raising=False)
    monkeypatch.setattr(cfg, "_settings", None)
    # 强制 settings.raw 无 deployment.mode（模拟未配置）
    class FakeSettings:
        raw = {"mode": "standalone", "databases": {"main": {"engine": "sqlite", "path": ":memory:"}}}
        deployment_yaml_path = None
        plugin_root = "."
        mode = "standalone"
        env = "development"
        def __init__(self): pass
    monkeypatch.setattr(cfg, "get_settings", lambda: FakeSettings())
    assert cfg.get_deployment_mode() == "solo"


def test_mode_enum():
    """DEPLOYMENT_MODES 枚举正确（solo/family/team）。"""
    from core.config import DEPLOYMENT_MODES, get_deployment_mode
    assert "solo" in DEPLOYMENT_MODES and "family" in DEPLOYMENT_MODES and "team" in DEPLOYMENT_MODES
    assert "hacker" not in DEPLOYMENT_MODES


# ---------------------------------------------------------------------------
# R4-1 成员系统
# ---------------------------------------------------------------------------


def test_members_disabled_in_solo():
    """solo 模式：成员系统不启用（成员函数级不拦截，端点层由 members_enabled 拦截）。"""
    assert teams_api.members_enabled() is False
    # 函数级仍可调用（不强制 mode），端点层才由 members_enabled 拦截
    r = teams_api.create_invite(note="solo-should-not-reach-here")
    assert r["ok"] is True


def test_invite_create_and_register(monkeypatch, tmp_path):
    """team 模式：邀请码创建 → 注册 → 成员入库。"""
    _set_mode(monkeypatch, "team")
    inv = teams_api.create_invite(note="张三邀请", max_uses=2, expires_hours=24)
    assert inv["ok"] and len(inv["invite_code"]) == 8
    code = inv["invite_code"]

    m1 = teams_api.register_member(code, "张三", "dev-001")
    assert m1["ok"] and m1["member_id"].startswith("m-")
    m2 = teams_api.register_member(code, "李四", "dev-002")
    assert m2["ok"]
    # 超过 max_uses=2 → 拒绝
    m3 = teams_api.register_member(code, "王五", "dev-003")
    assert m3["ok"] is False and "最大使用次数" in m3["note"]


def test_invite_expired_rejected(monkeypatch, tmp_path):
    """过期邀请码拒绝注册。"""
    _set_mode(monkeypatch, "team")
    inv = teams_api.create_invite(max_uses=5, expires_hours=1)
    # 直接改 expires_at 为过去
    conn = teams_api._get_conn()
    conn.execute("UPDATE invites SET expires_at=?", (int(time.time()) - 10,))
    conn.commit()
    conn.close()
    r = teams_api.register_member(inv["invite_code"], "过期用户", "dev-x")
    assert r["ok"] is False and "过期" in r["note"]


def test_member_add_direct_family(monkeypatch, tmp_path):
    """family 模式：直接添加成员（免邀请码）。"""
    _set_mode(monkeypatch, "family")
    m = teams_api.add_member_direct("家人甲", "dev-f1")
    assert m["ok"] and m["member_id"].startswith("m-")
    lst = teams_api.list_members()
    assert any(x["display_name"] == "家人甲" for x in lst["results"])


def test_member_revoke(monkeypatch, tmp_path):
    """吊销成员。"""
    _set_mode(monkeypatch, "team")
    inv = teams_api.create_invite()
    m = teams_api.register_member(inv["invite_code"], "被吊销", "dev-r")
    r = teams_api.revoke_member(m["member_id"])
    assert r["ok"] is True
    lst = teams_api.list_members()
    target = [x for x in lst["results"] if x["member_id"] == m["member_id"]][0]
    assert target["revoked"] == 1
    # 吊销后重连识别不到（revoked 过滤）
    assert teams_api.member_for_device("dev-r") is None


def test_device_bind_and_reconnect(monkeypatch, tmp_path):
    """设备↔成员绑定 + 重连识别（身份不变）。"""
    _set_mode(monkeypatch, "team")
    inv = teams_api.create_invite()
    m = teams_api.register_member(inv["invite_code"], "多设备用户", "dev-a")
    # 绑定第二台设备
    teams_api.bind_device_to_member("dev-b", m["member_id"])
    assert teams_api.member_for_device("dev-a")["member_id"] == m["member_id"]
    assert teams_api.member_for_device("dev-b")["member_id"] == m["member_id"]
    # 未绑定设备 → None
    assert teams_api.member_for_device("dev-unknown") is None


async def test_teams_api_endpoints(client, monkeypatch, tmp_path):
    """HTTP 端点：mode 读取 + 成员端点（Token 门禁）。"""
    monkeypatch.setattr(teams_api, "_db_path", lambda: tmp_path / "teams.db")
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    # mode 读取
    r = await client.get("/api/v1/deployment/mode", headers=headers)
    assert r.status_code == 200 and r.json()["data"]["mode"] == "solo"
    # solo 模式 member/list 返回未启用
    r2 = await client.get("/api/v1/member/list", headers=headers)
    assert r2.status_code == 200
    assert "未启用" in r2.json()["data"].get("note", "")
    # 无 Token → 401
    r3 = await client.get("/api/v1/deployment/mode")
    assert r3.status_code == 401
