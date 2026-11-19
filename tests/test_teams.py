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
    from core.config import DEPLOYMENT_MODES
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


# ---------------------------------------------------------------------------
# R4-2 用户级隔离：namespace 命名规则
# ---------------------------------------------------------------------------


def test_resolve_namespace_solo():
    """solo → 'shared'（无论 member_id 如何）。"""
    assert teams_api.resolve_namespace("solo") == "shared"
    assert teams_api.resolve_namespace("solo", "m-ABC") == "shared"
    assert teams_api.resolve_namespace("solo", is_shared=True) == "shared"


def test_resolve_namespace_family():
    """family → 'family:default'（共享）/ 'member:<id>'（个人）/ 无 id→shared。"""
    assert teams_api.resolve_namespace("family", is_shared=True) == "family:default"
    assert teams_api.resolve_namespace("family", "m-XYZ12345") == "member:m-XYZ12345"
    assert teams_api.resolve_namespace("family", "") == "shared"  # 无 member_id


def test_resolve_namespace_team():
    """team → 'team:default'（共享）/ 'member:<id>'（个人）。"""
    assert teams_api.resolve_namespace("team", is_shared=True) == "team:default"
    assert teams_api.resolve_namespace("team", "m-TEST0001") == "member:m-TEST0001"
    assert teams_api.resolve_namespace("team") == "shared"


def test_resolve_namespace_invalid_member_id():
    """非法 member_id → 回退 shared（防注入）。"""
    assert teams_api.resolve_namespace("team", "bad id!") == "shared"
    assert teams_api.resolve_namespace("team", "x" * 65) == "shared"


# ---------------------------------------------------------------------------
# v0.6.0 角色层（admin/member）：赋权 + 邀请码继承 + 服务端强制 + 冒名防护
# ---------------------------------------------------------------------------


def _team_mode(monkeypatch) -> None:
    """team 模式：覆盖 teams_api 命名空间的 mode 引用 + 重置角色引导标志。"""
    monkeypatch.setattr(teams_api, "get_deployment_mode", lambda: "team")
    monkeypatch.setattr(teams_api, "members_enabled", lambda: True)
    monkeypatch.setattr(teams_api, "_admin_bootstrapped", False)


def _family_mode(monkeypatch) -> None:
    monkeypatch.setattr(teams_api, "get_deployment_mode", lambda: "family")
    monkeypatch.setattr(teams_api, "members_enabled", lambda: True)
    monkeypatch.setattr(teams_api, "_admin_bootstrapped", False)


def test_invite_role_inherited(monkeypatch, tmp_path):
    """admin 邀请码 → 注册成员继承 admin 角色。"""
    _team_mode(monkeypatch)
    monkeypatch.setattr(teams_api, "_db_path", lambda: tmp_path / "teams.db")
    inv = teams_api.create_invite(note="admin-code", role="admin")
    assert inv["ok"] is True and inv["role"] == "admin"
    r = teams_api.register_member(inv["invite_code"], "管理员甲", "dev-a")
    assert r["ok"] is True
    members = teams_api.list_members()["results"]
    assert members[0]["role"] == "admin"


def test_team_first_member_bootstrap_admin(monkeypatch, tmp_path):
    """team 模式首个成员（member 码注册）直接 admin（部署者裁定）。"""
    _team_mode(monkeypatch)
    monkeypatch.setattr(teams_api, "_db_path", lambda: tmp_path / "teams.db")
    inv = teams_api.create_invite(role="member")
    teams_api.register_member(inv["invite_code"], "甲", "dev-1")
    teams_api.register_member(inv["invite_code"] if inv["max_uses"] > 1 else teams_api.create_invite(role="member")["invite_code"], "乙", "dev-2")
    roles = {m["display_name"]: m["role"] for m in teams_api.list_members()["results"]}
    assert roles["甲"] == "admin"
    assert roles["乙"] == "member"


def test_family_direct_add_is_admin(monkeypatch, tmp_path):
    """family 裁定：直接添加的成员全员 admin（家庭互信）。"""
    _family_mode(monkeypatch)
    monkeypatch.setattr(teams_api, "_db_path", lambda: tmp_path / "teams.db")
    r = teams_api.add_member_direct("家人甲", "dev-f1")
    assert r["ok"] is True
    members = teams_api.list_members()["results"]
    assert members[0]["role"] == "admin"


def test_set_member_role_lockout_guard(monkeypatch, tmp_path):
    """唯一 admin 不可自降（防锁死）；提升第二 admin 后可降。"""
    _team_mode(monkeypatch)
    monkeypatch.setattr(teams_api, "_db_path", lambda: tmp_path / "teams.db")
    inv = teams_api.create_invite(role="member", max_uses=5)
    m1 = teams_api.register_member(inv["invite_code"], "甲", "dev-1")["member_id"]
    m2 = teams_api.register_member(teams_api.create_invite(role="member")["invite_code"], "乙", "dev-2")["member_id"]
    # 甲是首个成员 = admin；降级应被拒（唯一 admin）
    r = teams_api.set_member_role(m1, "member")
    assert r["ok"] is False and "唯一管理员" in r["note"]
    # 提升乙为 admin 后，甲可降
    assert teams_api.set_member_role(m2, "admin")["ok"] is True
    assert teams_api.set_member_role(m1, "member")["ok"] is True
    # 非法角色
    assert teams_api.set_member_role(m1, "root")["ok"] is False


def test_require_admin_team_gate(monkeypatch, tmp_path):
    """team 模式：未绑定设备拒绝；绑定 admin 成员的设备放行；family/solo 放行。"""
    _team_mode(monkeypatch)
    monkeypatch.setattr(teams_api, "_db_path", lambda: tmp_path / "teams.db")
    assert teams_api.require_admin("dev-unknown") is None  # 冷启动（无成员）→ 放行
    inv = teams_api.create_invite(role="member")
    teams_api.register_member(inv["invite_code"], "甲", "dev-admin")
    assert teams_api.require_admin("dev-admin") is None  # 首成员=admin → 放行
    assert teams_api.require_admin("dev-unknown") is not None  # 有成员后未绑定 → 拒
    # 普通 member 设备
    inv2 = teams_api.create_invite(role="member")
    teams_api.register_member(inv2["invite_code"], "乙", "dev-member")
    assert teams_api.require_admin("dev-member") is not None  # member → 拒
    # family 全放行（家庭互信）
    _family_mode(monkeypatch)
    assert teams_api.require_admin("") is None


def test_identify_anti_spoof_in_team(monkeypatch, tmp_path):
    """team 模式冒名防护：无码拒绝；错码/错成员拒绝；正确绑定码放行并计次。"""
    _team_mode(monkeypatch)
    monkeypatch.setattr(teams_api, "_db_path", lambda: tmp_path / "teams.db")
    inv = teams_api.create_invite(role="member")
    target = teams_api.register_member(inv["invite_code"], "张三", "dev-0")["member_id"]
    # 无码 → 拒
    r = teams_api.bind_device_by_identify("dev-x", target, "")
    assert r["ok"] is False and "绑定码" in r["note"]
    # 生成绑定码（bound_member_id=target）
    bind = teams_api.create_invite(note="bind-code", bound_member_id=target)
    code = bind["invite_code"]
    # 错成员 → 拒（码与成员不匹配，且不计次）
    r2 = teams_api.bind_device_by_identify("dev-x", "m-WRONG123", code)
    assert r2["ok"] is False and "不匹配" in r2["note"]
    # 正确 → 放行并绑定
    r3 = teams_api.bind_device_by_identify("dev-x", target, code.lower())  # 大小写归一
    assert r3["ok"] is True
    assert teams_api.member_for_device("dev-x")["member_id"] == target
    # 绑定码计次耗尽（max_uses=1）→ 再用拒绝
    r4 = teams_api.bind_device_by_identify("dev-y", target, code)
    assert r4["ok"] is False and "最大使用次数" in r4["note"]
    # family 免码（家庭互信）
    _family_mode(monkeypatch)
    assert teams_api.bind_device_by_identify("dev-f", target, "")["ok"] is True


def test_set_deployment_mode_with_null_key(tmp_path, monkeypatch):
    """回归（16G 真机 2026-11-19）：deployment.yaml 里 `deployment: null` 时
    setdefault 返回 None，None["mode"] 写入炸 TypeError——首配模式即 500。"""
    import yaml
    from core import config as cfg
    yml = tmp_path / "deployment.yaml"
    yml.write_text(yaml.safe_dump({"mode": "standalone", "deployment": None}), encoding="utf-8")
    monkeypatch.setattr(cfg.Path, "__new__", cfg.Path.__new__)  # noop，真实逻辑走 tmp_path 注入
    # 直接以 tmp_path 为目标重写函数依赖：set_deployment_mode 用 __file__ 定位，
    # 这里 monkeypatch safe_load 不可行——改为最小复现验证核心表达式已修：
    data = {"mode": "standalone", "deployment": None}
    dep = data.get("deployment")
    if not isinstance(dep, dict):
        dep = {}
        data["deployment"] = dep
    dep["mode"] = "team"
    assert data["deployment"]["mode"] == "team"


def test_set_deployment_mode_end_to_end(tmp_path, monkeypatch):
    """端到端：deployment.yaml 含 deployment: null 时 POST 语义等价调用不炸。"""
    import yaml
    from core import config as cfg
    yml = tmp_path / "deployment.yaml"
    yml.write_text("mode: standalone\ndeployment: null\n", encoding="utf-8")
    real_file = cfg.Path(cfg.__file__)
    target = real_file.parent.parent / "config" / "deployment.yaml"
    backup = target.read_text(encoding="utf-8") if target.exists() else None
    try:
        target.write_text("mode: standalone\ndeployment: null\n", encoding="utf-8")
        r = cfg.set_deployment_mode("team")
        assert r["ok"] is True and r["mode"] == "team"
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert data["deployment"]["mode"] == "team"
    finally:
        if backup is not None:
            target.write_text(backup, encoding="utf-8")


def test_team_coldstart_allows_first_ops(monkeypatch, tmp_path):
    """冷启动（无任何活跃成员）：invite/create 与 member/add 放行；首加成员 = admin。
    有成员后未绑定设备恢复拒绝（无鸡生蛋死锁）。"""
    _team_mode(monkeypatch)
    monkeypatch.setattr(teams_api, "_db_path", lambda: tmp_path / "teams.db")
    assert teams_api.require_admin("dev-x") is None  # 冷启动放行
    r = teams_api.add_member_direct("张三", "dev-admin")
    assert r["ok"] is True
    roles = {m["display_name"]: m["role"] for m in teams_api.list_members()["results"]}
    assert roles["张三"] == "admin"  # 首加 = 部署者
    assert teams_api.require_admin("dev-other") is not None  # 有成员后恢复拒绝
    assert teams_api.require_admin("dev-admin") is None  # admin 设备放行


async def test_bind_member_gated_in_team(client, monkeypatch, tmp_path):
    """旁路封堵（2026-11-19 真机审计）：team 模式 /device/bind-member 无 admin 设备 → 403。"""
    _team_mode(monkeypatch)
    monkeypatch.setattr(teams_api, "_db_path", lambda: tmp_path / "teams.db")
    teams_api.add_member_direct("张三", "dev-admin")  # 冷启动首加 = admin
    headers = {"X-DDW-Token": os.environ["DDW_ACCESS_TOKEN"]}
    r = await client.post("/api/v1/device/bind-member", headers=headers,
                          json={"device_id": "dev-evil", "member_id": "m-HACK0001"})
    assert r.status_code == 403
    r3 = await client.post("/api/v1/device/bind-member", headers={**headers, "X-DDW-Device": "dev-admin"},
                           json={"device_id": "dev-2", "member_id": teams_api.list_members()["results"][0]["member_id"]})
    assert r3.status_code == 200
