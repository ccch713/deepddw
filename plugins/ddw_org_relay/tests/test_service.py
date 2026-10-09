"""org_relay 服务层测试：组织 / 签码 / 校验消耗 / 绑定关系 / 令牌。"""

from __future__ import annotations

import time

import pytest

from plugins.ddw_org_relay import bindcode, service, store


@pytest.fixture(autouse=True)
def _mock_models(monkeypatch):
    monkeypatch.setattr(service, "available_models", lambda: ["mock-model-x", "mock-model-y"])


def _mk_org(name="Acme", **kw):
    return service.create_org(name, **kw)


def _issue(org, **kw):
    return service.issue_bindcodes(org["org_id"], **kw)["codes"][0]


def test_create_org_returns_secret_once():
    org = _mk_org()
    assert org["org_id"].startswith("org_") and len(org["org_id"]) > 8
    assert len(org["org_secret"]) >= 64
    # 落盘为密文：密文不以明文出现
    with store.get_conn() as conn:
        row = conn.execute("SELECT secret_enc FROM orgs WHERE org_id=?",
                           (org["org_id"],)).fetchone()
    assert org["org_secret"] not in row["secret_enc"]


def test_bind_unbind_me_roundtrip():
    org = _mk_org()
    code = _issue(org, ttl_min=15, max_uses=10)
    result = service.do_bind("user-1", code)
    assert result["bound"] is True
    payload = result["org"]
    assert payload["org_id"] == org["org_id"]
    assert payload["access_token"].startswith("orgm_")
    assert payload["server_base_url"].endswith("/api/v1/plugins/ddw-org-relay")
    assert sorted(payload["models"]) == ["mock-model-x", "mock-model-y"]

    state = service.org_state("user-1")
    assert state["bound"] and state["org_consumed_total"] == 0

    assert service.do_unbind("user-1") == {"bound": False}
    assert service.org_state("user-1")["bound"] is False
    # 幂等解绑
    assert service.do_unbind("user-1") == {"bound": False}


def test_member_token_invalid_after_unbind():
    org = _mk_org()
    token = service.do_bind("user-1", _issue(org))["org"]["access_token"]
    assert service.binding_for_token(token) is not None
    service.do_unbind("user-1")
    assert service.binding_for_token(token) is None


def test_code_usage_exhausted():
    org = _mk_org()
    code = _issue(org, ttl_min=15, max_uses=1)
    service.do_bind("user-a", code)
    with pytest.raises(service.ServiceError) as e:
        service.do_bind("user-b", code)
    assert e.value.code == 409


def test_code_revoked_means_deleted():
    org = _mk_org()
    code = _issue(org)
    assert service.revoke_bindcodes(org["org_id"], code=code)["revoked"] == 1
    with pytest.raises(service.ServiceError) as e:
        service.do_bind("user-a", code)
    assert e.value.code == 404


def test_code_expired():
    org = _mk_org()
    with store.get_conn() as conn:
        row = store.row_to_org(
            conn.execute("SELECT * FROM orgs WHERE org_id=?", (org["org_id"],)).fetchone(),
            with_secret=True)
    past = int(time.time()) - 100
    code = bindcode.issue_code(org["org_id"], row["secret"], past)
    with store.get_conn() as conn:
        conn.execute(
            "INSERT INTO org_codes(code, org_id, exp_ts, max_uses, created_at) VALUES(?,?,?,?,?)",
            (code, org["org_id"], past, 10, past))
    with pytest.raises(service.ServiceError) as e:
        service.do_bind("user-a", code)
    assert e.value.code == 410


def test_forged_code():
    _mk_org()
    with pytest.raises(service.ServiceError) as e:
        service.do_bind("user-a", "DDWORG-YWJjZGVm.0123456789abcdef")
    assert e.value.code == 403


def test_cross_org_binding_conflict_and_same_org_idempotent():
    org1, org2 = _mk_org("A"), _mk_org("B")
    c1 = _issue(org1)
    c2 = _issue(org2)
    service.do_bind("user-1", c1)
    with pytest.raises(service.ServiceError) as e:
        service.do_bind("user-1", c2)
    assert e.value.code == 409
    # 同组织重复绑定：幂等，不烧码（用次不变）
    again = service.do_bind("user-1", c1)
    assert again["bound"] and again["org"]["org_id"] == org1["org_id"]
    with store.get_conn() as conn:
        used = conn.execute("SELECT used_count FROM org_codes WHERE code=?", (c1,)).fetchone()[0]
    assert used == 1


def test_secret_rotation_old_code_still_valid():
    org = _mk_org()
    code = _issue(org, ttl_min=15)
    rotated = service.rotate_secret(org["org_id"])
    assert rotated["org_secret"] != org["org_secret"]
    # 轮换后旧码在时效内仍有效（§6）
    result = service.do_bind("user-1", code)
    assert result["bound"]
    # 新密钥签的码自然也有效
    new_code = _issue(org)
    assert service.do_bind("user-2", new_code)["bound"]


def test_disabled_org_rejects_binding():
    org = _mk_org()
    code = _issue(org)
    service.set_org_status(org["org_id"], "disabled")
    with pytest.raises(service.ServiceError) as e:
        service.do_bind("user-a", code)
    assert e.value.code == 403
    # 已绑成员在组织停用后令牌失效
    service.set_org_status(org["org_id"], "active")
    token = service.do_bind("user-b", _issue(org))["org"]["access_token"]
    service.set_org_status(org["org_id"], "disabled")
    assert service.binding_for_token(token) is None


def test_quota_enforcement_and_usage_accounting():
    org = _mk_org(quota_requests=2)
    token = service.do_bind("user-1", _issue(org))["org"]["access_token"]
    binding = service.binding_for_token(token)
    service.check_and_count_quota(org["org_id"], binding["org_quota"])
    service.record_chat_usage(org["org_id"], "user-1", model="m", tokens_in=10, tokens_out=5, ok=True)
    service.check_and_count_quota(org["org_id"], binding["org_quota"])  # used=1 < 2
    service.record_chat_usage(org["org_id"], "user-1", model="m", tokens_in=1, tokens_out=1, ok=True)
    with pytest.raises(service.ServiceError) as e:
        service.check_and_count_quota(org["org_id"], binding["org_quota"])
    assert e.value.code == 429
    # 对账聚合
    report = service.usage_report(org["org_id"])
    item = report["items"][0]
    assert item["usage"]["requests_ok"] == 2 and item["usage"]["tokens_in"] == 11


def test_revoke_member_kills_token():
    org = _mk_org()
    token = service.do_bind("user-1", _issue(org))["org"]["access_token"]
    service.revoke_member("user-1")
    assert service.binding_for_token(token) is None
    assert service.org_state("user-1")["bound"] is False


def test_no_personal_data_deleted_on_unbind():
    """解绑只结束关系：用量流水（元数据）保留供对账，不删任何行。"""
    org = _mk_org()
    token = service.do_bind("user-1", _issue(org))["org"]["access_token"]
    assert service.binding_for_token(token) is not None
    service.record_chat_usage(org["org_id"], "user-1", model="m", tokens_in=3, tokens_out=4, ok=True)
    service.do_unbind("user-1")
    with store.get_conn() as conn:
        usage_cnt = conn.execute("SELECT COUNT(*) FROM org_usage WHERE org_id=?",
                                 (org["org_id"],)).fetchone()[0]
        bind_cnt = conn.execute("SELECT COUNT(*) FROM org_bindings WHERE user_id=?",
                                ("user-1",)).fetchone()[0]
    assert usage_cnt >= 2  # bind + chat 流水仍在
    assert bind_cnt == 1   # 绑定历史行保留（unbound_at 置位）
