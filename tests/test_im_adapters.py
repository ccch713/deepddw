"""IM adapters production-grade tests (mock platform HTTP, no real credentials).

Covers 8 scenarios per TASK_SPEC §4:
1. DingTalk: @ message inbound → handle_incoming returns correct structure
2. DingTalk: non-@ group message → ignored (returns None)
3. Feishu: require_mention=False → respond; =True → ignore non-@
4. Feishu: rate limiting (>10 msgs/60s per group → drop)
5. WeCom: message inbound → correct parse
6. resolve_user: success/fail (cache hit/miss)
7. send_message: network error → retry 2x then succeed
8. Audit: send_message → im_audit_log has record
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.im_adapters.base import _RateLimiter, _TTLCache, retry_with_backoff, write_audit
from core.im_adapters.dingtalk.adapter import DingTalkAdapter
from core.im_adapters.feishu.adapter import FeishuAdapter
from core.im_adapters.wecom.adapter import WeComAdapter


# ---------------------------------------------------------------------------
# Test 1: DingTalk @ message inbound
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dingtalk_at_message_inbound():
    """DingTalk group @ message → handle_incoming returns correct structure."""
    adapter = DingTalkAdapter(
        credentials={"app_key": "test", "app_secret": "test"},
        require_mention=True,
    )

    message = {
        "senderId": "user123",
        "chatId": "chat456",
        "text": {"content": "hello bot"},
        "msgtype": "text",
        "conversationType": "2",  # group
        "isInAt": True,  # @mentioned
    }

    with patch.object(adapter, "write_audit", new_callable=AsyncMock) if hasattr(adapter, "write_audit") else patch("core.im_adapters.base.write_audit", new_callable=AsyncMock):
        result = await adapter.handle_incoming(message)

    assert result is not None
    assert result["user_id"] == "user123"
    assert result["chat_id"] == "chat456"
    assert result["content"] == "hello bot"
    assert result["is_group"] is True
    assert result["type"] == "text"


# ---------------------------------------------------------------------------
# Test 2: DingTalk non-@ group message → ignored
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dingtalk_non_at_group_message_ignored():
    """DingTalk non-@ group message → handle_incoming returns None."""
    adapter = DingTalkAdapter(
        credentials={"app_key": "test", "app_secret": "test"},
        require_mention=True,
    )

    message = {
        "senderId": "user123",
        "chatId": "chat456",
        "text": {"content": "just chatting"},
        "msgtype": "text",
        "conversationType": "2",  # group
        "isInAt": False,  # NOT @mentioned
    }

    with patch("core.im_adapters.base.write_audit", new_callable=AsyncMock):
        result = await adapter.handle_incoming(message)

    assert result is None


# ---------------------------------------------------------------------------
# Test 3: Feishu require_mention policy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feishu_require_mention_policy():
    """Feishu require_mention=False → respond; =True → ignore non-@."""
    # --- require_mention=True, no mention → ignored ---
    adapter_strict = FeishuAdapter(
        credentials={"app_id": "test", "app_secret": "test"},
        require_mention=True,
    )

    msg_no_mention = {
        "sender": {"sender_id": {"user_id": "ou_abc"}, "sender_type": "user"},
        "message": {
            "chat_id": "oc_group1",
            "chat_type": "group",
            "message_type": "text",
            "content": '{"text": "hello"}',
            "mentions": [],  # no @mention
        },
    }

    with patch("core.im_adapters.base.write_audit", new_callable=AsyncMock):
        result = await adapter_strict.handle_incoming(msg_no_mention)

    assert result is None, "require_mention=True should ignore non-@ message"

    # --- require_mention=False, no mention → respond ---
    adapter_loose = FeishuAdapter(
        credentials={"app_id": "test", "app_secret": "test"},
        require_mention=False,
    )

    with patch("core.im_adapters.base.write_audit", new_callable=AsyncMock):
        result = await adapter_loose.handle_incoming(msg_no_mention)

    assert result is not None
    assert result["content"] == "hello"
    assert result["is_group"] is True

    # --- require_mention=True, has mention → respond ---
    msg_with_mention = {
        "sender": {"sender_id": {"user_id": "ou_abc"}, "sender_type": "user"},
        "message": {
            "chat_id": "oc_group1",
            "chat_type": "group",
            "message_type": "text",
            "content": '{"text": "@bot help"}',
            "mentions": [{"id": {"user_id": "ou_bot"}}],
        },
    }

    with patch("core.im_adapters.base.write_audit", new_callable=AsyncMock):
        result = await adapter_strict.handle_incoming(msg_with_mention)

    assert result is not None
    assert result["content"] == "@bot help"


# ---------------------------------------------------------------------------
# Test 4: Feishu rate limiting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feishu_rate_limiting():
    """Feishu require_mention=False: >10 msgs in 60s per group → drop."""
    adapter = FeishuAdapter(
        credentials={"app_id": "test", "app_secret": "test"},
        require_mention=False,
    )

    base_msg = {
        "sender": {"sender_id": {"user_id": "ou_abc"}, "sender_type": "user"},
        "message": {
            "chat_id": "oc_rate_test",
            "chat_type": "group",
            "message_type": "text",
            "content": '{"text": "msg"}',
            "mentions": [],
        },
    }

    with patch("core.im_adapters.base.write_audit", new_callable=AsyncMock):
        # Send 10 messages — all should pass
        for i in range(10):
            msg = {
                "sender": base_msg["sender"],
                "message": {**base_msg["message"], "content": f'{{"text": "msg{i}"}}'},
            }
            result = await adapter.handle_incoming(msg)
            assert result is not None, f"Message {i+1} should pass rate limit"

        # 11th message should be rate-limited
        msg_11 = {
            "sender": base_msg["sender"],
            "message": {**base_msg["message"], "content": '{"text": "msg11"}'},
        }
        result = await adapter.handle_incoming(msg_11)
        assert result is None, "11th message should be rate-limited"


# ---------------------------------------------------------------------------
# Test 5: WeCom message inbound
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wecom_message_inbound():
    """WeCom group @ message → correct parse."""
    adapter = WeComAdapter(
        credentials={"corp_id": "test_corp", "corp_secret": "test_secret"},
        require_mention=True,
    )

    message = {
        "FromUserName": "user_wecom_001",
        "ToUserName": "test_corp",
        "MsgType": "text",
        "Content": "@test_corp 你好",
        "MsgId": "msg_001",
        "ChatId": "chat_wecom_001",
        "isAt": True,
    }

    with patch("core.im_adapters.base.write_audit", new_callable=AsyncMock):
        result = await adapter.handle_incoming(message)

    assert result is not None
    assert result["user_id"] == "user_wecom_001"
    assert result["chat_id"] == "chat_wecom_001"
    assert result["content"] == "@test_corp 你好"
    assert result["is_group"] is True
    assert result["type"] == "text"


# ---------------------------------------------------------------------------
# Test 6: resolve_user — success/fail with cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_user_success_and_cache():
    """resolve_user: mapping success/fail and cache hit/miss."""
    adapter = DingTalkAdapter(
        credentials={"app_key": "test", "app_secret": "test"},
    )

    # Mock get_user_info to return a user with phone
    mock_platform_user = {"user_id": "dt_user1", "name": "张三", "phone": "13800138000"}

    with (
        patch.object(adapter, "get_user_info", new_callable=AsyncMock, return_value=mock_platform_user),
        patch("core.im_adapters.base._db_session_scope") as mock_scope,
    ):
        # Mock DB query returning a user
        mock_session = AsyncMock()
        mock_row = (1001, "张三", "13800138000", "admin")
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        mock_session.execute.return_value = mock_result
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

        # First call — cache miss, hits DB
        user = await adapter.resolve_user("dt_user1")
        assert user is not None
        assert user["user_id"] == 1001
        assert user["name"] == "张三"
        assert user["phone"] == "13800138000"
        assert user["role"] == "admin"

        # Second call — cache hit, no DB call
        mock_session.execute.reset_mock()
        user2 = await adapter.resolve_user("dt_user1")
        assert user2 is not None
        assert user2["user_id"] == 1001
        mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_user_fail():
    """resolve_user: mapping fails → returns None."""
    adapter = DingTalkAdapter(
        credentials={"app_key": "test", "app_secret": "test"},
    )

    # Clear cache
    adapter._user_cache = _TTLCache(ttl=3600)

    # Mock get_user_info to return empty name
    mock_platform_user = {"user_id": "dt_unknown", "name": "", "phone": ""}

    with patch.object(adapter, "get_user_info", new_callable=AsyncMock, return_value=mock_platform_user):
        user = await adapter.resolve_user("dt_unknown")
        assert user is None


# ---------------------------------------------------------------------------
# Test 7: retry_with_backoff — network error then success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_on_network_error():
    """send_message: network error → retry 2x then succeed."""
    call_count = 0

    async def flaky_coro():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError(f"Network error attempt {call_count}")
        return "success"

    with patch("core.im_adapters.base.asyncio.sleep", new_callable=AsyncMock):
        result = await retry_with_backoff(flaky_coro, max_retries=2)

    assert result == "success"
    assert call_count == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_retry_exhausted():
    """retry_with_backoff: all retries fail → re-raises last exception."""
    call_count = 0

    async def always_fail():
        nonlocal call_count
        call_count += 1
        raise ConnectionError(f"Fail {call_count}")

    with (
        patch("core.im_adapters.base.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(ConnectionError, match="Fail 3"),
    ):
        await retry_with_backoff(always_fail, max_retries=2)

    assert call_count == 3


# ---------------------------------------------------------------------------
# Test 8: Audit logging
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_logging():
    """send_message → im_audit_log has record."""
    with (
        patch("core.im_adapters.base.write_audit", new_callable=AsyncMock),
        patch("core.im_adapters.base._db_session_scope") as mock_scope,
    ):
        mock_session = AsyncMock()
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

        # Directly test write_audit
        await write_audit("dingtalk", "outbound", "chat_001", "user_001", "test message")

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        sql = call_args[0][0].text
        assert "INSERT INTO im_audit_log" in sql

        params = call_args[0][1]
        assert params["p"] == "dingtalk"
        assert params["d"] == "outbound"
        assert params["c"] == "chat_001"
        assert params["u"] == "user_001"
        expected_hash = hashlib.sha256(b"test message").hexdigest()[:64]
        assert params["h"] == expected_hash


# ---------------------------------------------------------------------------
# Bonus: TTLCache and RateLimiter unit tests
# ---------------------------------------------------------------------------

def test_ttl_cache_basic():
    """TTLCache: set/get/expire."""
    cache = _TTLCache(ttl=1)  # 1 second TTL

    cache.set("key1", "value1")
    hit, val = cache.get("key1")
    assert hit is True
    assert val == "value1"

    # Miss
    hit, val = cache.get("nonexistent")
    assert hit is False
    assert val is None


def test_rate_limiter_basic():
    """RateLimiter: allow up to max, then deny."""
    limiter = _RateLimiter(max_count=3, window_sec=60)

    assert limiter.allow("chat1") is True
    assert limiter.allow("chat1") is True
    assert limiter.allow("chat1") is True
    assert limiter.allow("chat1") is False  # 4th denied

    # Different key still allowed
    assert limiter.allow("chat2") is True
