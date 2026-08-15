"""
转发器测试

覆盖:
- RelayRequest/RelayResponse 数据结构
- 请求构建
- 响应解析
"""
from __future__ import annotations

from ddw_llm_gateway.relay import Relay, RelayRequest, RelayResponse


class TestRelayRequest:
    """转发请求测试"""

    def test_basic_request(self):
        """基本请求构建"""
        req = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert req.model == "gpt-4"
        assert len(req.messages) == 1
        assert req.stream is False

    def test_stream_request(self):
        """流式请求"""
        req = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,
        )

        assert req.stream is True

    def test_request_with_params(self):
        """带参数的请求"""
        req = RelayRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=100,
            temperature=0.7,
            top_p=0.9,
            user_id=123,
        )

        assert req.max_tokens == 100
        assert req.temperature == 0.7
        assert req.top_p == 0.9
        assert req.user_id == 123


class TestRelayResponse:
    """转发响应测试"""

    def test_success_response(self):
        """成功响应"""
        resp = RelayResponse(
            success=True,
            status_code=200,
            data={"choices": []},
            channel_id=1,
            channel_name="test",
            response_time=100,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

        assert resp.success is True
        assert resp.total_tokens == 30

    def test_error_response(self):
        """错误响应"""
        resp = RelayResponse(
            success=False,
            status_code=503,
            error_message="无可用渠道",
        )

        assert resp.success is False
        assert resp.status_code == 503
        assert "无可用渠道" in resp.error_message


class TestRelay:
    """转发器测试"""

    def setup_method(self):
        """每个测试方法前初始化"""
        self.relay = Relay()

    def test_relay_initialization(self):
        """转发器初始化"""
        assert self.relay._load_balancer is not None
        assert self.relay._circuit_breaker is not None
