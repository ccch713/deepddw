"""绑定码签发/校验单测（bindcode-v1 §2 纯函数）。"""

from __future__ import annotations

import time

import pytest

from plugins.ddw_org_relay import bindcode

SECRET = "s" * 64  # ≥32 字节
ORG = "org_ab12cd34"


def test_issue_and_verify_roundtrip():
    exp = int(time.time()) + 900
    code = bindcode.issue_code(ORG, SECRET, exp)
    assert code.startswith("DDWORG-")
    assert code.count(".") == 1
    result = bindcode.verify_signature(code, SECRET)
    assert result.ok and result.payload is not None
    assert result.payload.org_id == ORG
    assert result.payload.exp_ts == exp
    assert len(result.payload.nonce) >= 8


def test_two_issues_differ_within_same_minute():
    exp = int(time.time()) + 60
    a = bindcode.issue_code(ORG, SECRET, exp)
    b = bindcode.issue_code(ORG, SECRET, exp)
    assert a != b  # nonce 保证


def test_fixed_nonce_is_deterministic():
    exp = int(time.time()) + 60
    a = bindcode.issue_code(ORG, SECRET, exp, nonce="deadbeef01")
    b = bindcode.issue_code(ORG, SECRET, exp, nonce="deadbeef01")
    assert a == b


def test_wrong_secret_rejected():
    exp = int(time.time()) + 900
    code = bindcode.issue_code(ORG, SECRET, exp)
    result = bindcode.verify_signature(code, "x" * 64)
    assert not result.ok and result.reason == "bad_signature"


def test_tampered_payload_rejected():
    exp = int(time.time()) + 900
    code = bindcode.issue_code(ORG, SECRET, exp)
    b64, sig = code[len("DDWORG-"):].split(".")
    # 篡改 payload 首字符（org_id 变化）而保持签名
    import base64

    raw = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
    tampered = b"X" + raw[1:]
    tb64 = base64.urlsafe_b64encode(tampered).decode().rstrip("=")
    result = bindcode.verify_signature(f"DDWORG-{tb64}.{sig}", SECRET)
    assert not result.ok and result.reason == "bad_signature"


def test_tampered_signature_rejected():
    exp = int(time.time()) + 900
    code = bindcode.issue_code(ORG, SECRET, exp)
    b64, sig = code[len("DDWORG-"):].split(".")
    bad = ("0" if sig[0] != "0" else "1") + sig[1:]
    result = bindcode.verify_signature(f"DDWORG-{b64}.{bad}", SECRET)
    assert not result.ok and result.reason == "bad_signature"


def test_expired_rejected():
    past = int(time.time()) - 10
    code = bindcode.issue_code(ORG, SECRET, past)
    result = bindcode.verify_signature(code, SECRET)
    assert not result.ok and result.reason == "expired"


def test_expiry_boundary():
    now = int(time.time())
    code = bindcode.issue_code(ORG, SECRET, now + 1)
    assert bindcode.verify_signature(code, SECRET, now_ts=now).ok
    assert bindcode.verify_signature(code, SECRET, now_ts=now + 1).reason == "expired"


@pytest.mark.parametrize("bad", [
    "",
    "not-a-code",
    "DDWORG-onlybase64",            # 无 sig 段
    "DDWORG-!!!.abcd",              # 非 b64url
    "DDWORG-YWJj.abcdef0123456789",  # payload 非 3 段
])
def test_malformed_rejected(bad):
    result = bindcode.verify_signature(bad, SECRET)
    assert not result.ok and result.reason == "malformed"


def test_short_nonce_malformed():
    import base64

    payload = f"{ORG}|{int(time.time()) + 60}|abc"  # nonce < 8
    b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    code = f"DDWORG-{b64}.0123456789abcdef"
    assert bindcode.verify_signature(code, SECRET).reason == "malformed"


def test_extract_org_id():
    exp = int(time.time()) + 60
    code = bindcode.issue_code(ORG, SECRET, exp)
    assert bindcode.extract_org_id(code) == ORG
    assert bindcode.extract_org_id("garbage") is None


def test_org_id_with_pipe_rejected():
    with pytest.raises(ValueError):
        bindcode.issue_code("org|x", SECRET, int(time.time()) + 60)
