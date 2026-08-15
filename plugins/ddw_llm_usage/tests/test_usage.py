"""ddw_llm_usage — 端到端测试（≥6 条，全绿）。

覆盖任务规约列出的 8 条核心场景 + 一些边界（健康检查、按日明细回补等）。
每个测试用独立临时 SQLite 文件，互不影响；可重复执行。
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 让测试既能在 ``pytest plugins/ddw_llm_usage/tests`` 跑，也能在根目录 ``pytest`` 跑
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parents[3]
for p in (str(_ROOT), str(_ROOT / "cloud-llm" / "ddw-ai-hub")):
    if p not in sys.path:
        sys.path.insert(0, p)

from plugins.ddw_llm_usage import PLUGIN_NAME, VERSION  # noqa: E402
from plugins.ddw_llm_usage.models import (  # noqa: E402
    DEFAULT_PRICES,
    compute_cost_cents,
)
from plugins.ddw_llm_usage.plugin import Plugin  # noqa: E402
from plugins.ddw_llm_usage.storage import UsageStorage  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_storage(tmp_path: Path) -> UsageStorage:
    """每个测试用独立 SQLite 文件，测试结束自动清理。"""
    db_path = tmp_path / "llm_usage.db"
    return UsageStorage(db_path)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """组装 FastAPI app + 插件，返回 TestClient。

    严格按底座 ``core/main.py:load_plugins`` 的调用顺序：
        1. ``cls(app, config, manifest)`` → __init__ 末尾自动 setup()
        2. ``instance.register()`` → include_router 到 app

    测试用例通过 TestClient 调 API 之前，所有 routes 都已经挂上。
    """
    import sys as _sys

    # 防御性检查：sdk 必须来自本地 v1，否则测试结果是假绿
    assert "sdk.plugin_base" in _sys.modules
    pb = _sys.modules["sdk.plugin_base"]
    assert pb.__file__.endswith(
        "sdk/plugin_base.py"), f"PluginBase 来自错误位置: {pb.__file__}"

    app = FastAPI()
    db_path = str(tmp_path / "llm_usage.db")
    plugin = Plugin(
        app=app,
        config={"db_path": db_path},
        manifest={"config": {"db_path": db_path},
            "name": PLUGIN_NAME, "version": VERSION},
    )
    plugin.register()  # 与底座流程一致
    # 重置价格表覆盖（避免上一次跑留下的 PUT 影响本次）
    plugin.storage.delete_price("deepseek-v4-flash")
    return TestClient(app)


_SERVICE_HEADERS = {"X-Service-Key": "test-service-key"}
_ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


def _post_record(client: TestClient, **overrides):
    body = {
        "id": str(uuid.uuid4()),
        "plugin": "ddw_wenqu_tutor",
        "user": "alice",
        "model": "deepseek-v4-flash",
        "provider": "deepseek",
        "input_tokens": 0,  # 默认 0，调用方显式覆盖
        "output_tokens": 0,  # 同上，避免无意识累加
        "cache_hit_tokens": 0,
        "session_id": "sess-1",
    }
    body.update(overrides)
    return client.post("/api/v1/plugins/ddw_llm_usage/records", json=body, headers=_SERVICE_HEADERS)  # noqa: E501


# ---------------------------------------------------------------------------
# 1) 一次调用：入库成功 + 费用精确计算
# ---------------------------------------------------------------------------


def test_single_record_cost_precise(tmp_storage: UsageStorage) -> None:
    """deepseek-v4-flash：1.0/2.0 元/M ⇒ 1k input + 0.5k output = 0.001 + 0.001 = 0.002 元 = 0 分（四舍五入）"""  # noqa: E501
    rec, created = tmp_storage.record_usage(
        id="rec-1",
        ts=datetime.now(timezone.utc),
        plugin="ddw_wenqu_tutor",
        user="alice",
        model="deepseek-v4-flash",
        provider="deepseek",
        input_tokens=1_000_000,  # 1M → 1.0 元
        output_tokens=500_000,  # 0.5M → 1.0 元
        cache_hit_tokens=0,
        session_id=None,
    )
    assert created is True
    # 1.0 + 1.0 = 2.0 元 = 200 分
    assert rec.cost_cents == 200
    assert rec.pricing_defaulted is False


def test_compute_cost_cents_unit_math() -> None:
    """compute_cost_cents 单元精度：tokens * yuan/M / 10000 = cents。"""
    # 1M token × 1.0 元/M = 100 分
    assert (
        compute_cost_cents(
            input_tokens=1_000_000,
            output_tokens=0,
            cache_hit_tokens=0,
            input_price=1.0,
            output_price=2.0,
        )
        == 100
    )
    # 0 token = 0 分
    assert (
        compute_cost_cents(
            input_tokens=0,
            output_tokens=0,
            cache_hit_tokens=0,
            input_price=1.0,
            output_price=2.0,
        )
        == 0
    )
    # 半进位：0.5 分 → 1 分
    assert (
        compute_cost_cents(
            input_tokens=50_000,
            output_tokens=0,
            cache_hit_tokens=0,
            input_price=0.1,
            output_price=0.1,
        )
        == 1
    )


# ---------------------------------------------------------------------------
# 2) 幂等：同 id 重复提交 → 忽略
# ---------------------------------------------------------------------------


def test_idempotent_insert(client: TestClient) -> None:
    r1 = _post_record(client, id="dup-id", input_tokens=1_000_000, output_tokens=0)
    assert r1.status_code == 201
    assert r1.json()["created"] is True
    # 1M × 1.0 元/M / 10000 = 100 分
    assert r1.json()["record"]["cost_cents"] == 100

    # 用同 id 再提交（更大 token）：应被忽略，cost_cents 仍为第一次的 100
    r2 = _post_record(
        client,
        id="dup-id",
        input_tokens=1_000_000,
        output_tokens=999_999,
        cache_hit_tokens=10_000_000,
    )
    assert r2.status_code == 201
    assert r2.json()["created"] is False
    assert r2.json()["record"]["cost_cents"] == 100  # 旧值，不被新参数覆写
    assert r2.json()["record"]["output_tokens"] == 0  # 输出 token 也是旧值
    assert r2.json()["record"]["input_tokens"] == 1_000_000  # 输入也是旧值

    # 统计侧只算 1 次
    s = client.get("/api/v1/plugins/ddw_llm_usage/stats/summary?days=7").json()
    assert s["calls"] == 1
    assert s["total_cents"] == 100
    assert s["input_tokens"] == 1_000_000
    assert s["output_tokens"] == 0


# ---------------------------------------------------------------------------
# 3) 按模型统计：2 条记录 → 分组正确
# ---------------------------------------------------------------------------


def test_by_model_grouping(client: TestClient) -> None:
    _post_record(client, model="deepseek-v4-flash", input_tokens=1_000_000)  # 100 分
    _post_record(client, model="deepseek-v4-flash",
                 input_tokens=0, output_tokens=500_000)  # 100 分
    _post_record(client, model="mimo-v2.5-pro",
                 input_tokens=100_000)  # 0.1M × 3.2 = 32 分

    items = client.get(
        "/api/v1/plugins/ddw_llm_usage/stats/by-model?days=30").json()["items"]
    by = {x["model"]: x for x in items}

    assert by["deepseek-v4-flash"]["calls"] == 2
    assert by["deepseek-v4-flash"]["input_tokens"] == 1_000_000
    assert by["deepseek-v4-flash"]["output_tokens"] == 500_000
    assert by["deepseek-v4-flash"]["total_cents"] == 200

    assert by["mimo-v2.5-pro"]["calls"] == 1
    # 100_000 × 3.2 / 10_000 = 32 分
    assert by["mimo-v2.5-pro"]["total_cents"] == 32


# ---------------------------------------------------------------------------
# 4) 按插件统计：不同插件 → 分组正确
# ---------------------------------------------------------------------------


def test_by_plugin_grouping(client: TestClient) -> None:
    _post_record(client, plugin="ddw_wenqu_tutor", input_tokens=1_000_000)  # 100 分
    _post_record(client, plugin="ddw_wenqu_tutor",
                 input_tokens=0, output_tokens=500_000)  # 100 分
    _post_record(client, plugin="ddw_smart_cs", input_tokens=1_000_000)  # 100 分

    items = client.get(
        "/api/v1/plugins/ddw_llm_usage/stats/by-plugin?days=30").json()["items"]
    by = {x["plugin"]: x for x in items}

    assert by["ddw_wenqu_tutor"]["calls"] == 2
    assert by["ddw_wenqu_tutor"]["total_cents"] == 200
    assert by["ddw_smart_cs"]["calls"] == 1
    assert by["ddw_smart_cs"]["total_cents"] == 100


# ---------------------------------------------------------------------------
# 5) 单价表 PUT 更新 → 后续记录用新价
# ---------------------------------------------------------------------------


def test_put_price_affects_next_record(client: TestClient) -> None:
    # 用默认价先记一次：1M input = 100 分
    r1 = _post_record(client, id="before", input_tokens=1_000_000, output_tokens=0)
    assert r1.json()["record"]["cost_cents"] == 100

    # PUT 调价：把 deepseek-v4-flash 输入调到 5.0 元/M
    put = client.put(
        "/api/v1/plugins/ddw_llm_usage/prices/deepseek-v4-flash",
        json={"input_price": 5.0, "output_price": 10.0,
            "cache_hit_price": 0.5, "provider": "deepseek"},
        headers=_ADMIN_HEADERS,
    )
    assert put.status_code == 200
    assert put.json()["input_price"] == 5.0

    # 再记一次：1M input = 500 分
    r2 = _post_record(client, id="after", input_tokens=1_000_000, output_tokens=0)
    assert r2.json()["record"]["cost_cents"] == 500
    # 旧记录费用不变
    assert r2.json()["created"] is True

    # 汇总 = 100 + 500 = 600 分
    s = client.get("/api/v1/plugins/ddw_llm_usage/stats/summary?days=7").json()
    assert s["total_cents"] == 600


# ---------------------------------------------------------------------------
# 6) 未知 model → 走 provider 默认价 + pricing_defaulted=true
# ---------------------------------------------------------------------------


def test_unknown_model_uses_provider_default(client: TestClient) -> None:
    # "deepseek-v999-ultra" 不在表里，但 provider=deepseek → 走 deepseek 默认 (1.0/2.0)
    r = _post_record(
        client,
        model="deepseek-v999-ultra",
        provider="deepseek",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    body = r.json()["record"]
    assert body["pricing_defaulted"] is True
    # 1M × 1.0 / 1 = 100 分（按 deepseek 默认）
    assert body["cost_cents"] == 100


def test_unknown_provider_falls_back_to_deepseek(client: TestClient) -> None:
    """provider 也不在兜底表里 → 取 deepseek 默认价。"""
    r = _post_record(
        client,
        model="mystery-llm",
        provider="unknown-corp",
        input_tokens=1_000_000,
    )
    body = r.json()["record"]
    assert body["pricing_defaulted"] is True
    assert body["cost_cents"] == 100  # 按 deepseek 默认价


# ---------------------------------------------------------------------------
# 7) 汇总接口 days 参数
# ---------------------------------------------------------------------------


def test_summary_endpoint_days_7(client: TestClient) -> None:
    # 多条记录合计：1M input (100) + 0.5M output (100) + 0.1M input mimo (32) = 232 分
    _post_record(client, model="deepseek-v4-flash",
                 input_tokens=1_000_000, output_tokens=500_000)
    _post_record(client, model="mimo-v2.5-pro", input_tokens=100_000)

    s = client.get("/api/v1/plugins/ddw_llm_usage/stats/summary?days=7").json()
    assert s["days"] == 7
    assert s["calls"] == 2
    assert s["input_tokens"] == 1_100_000
    assert s["output_tokens"] == 500_000
    assert s["total_tokens"] == 1_600_000
    assert s["total_cents"] == 232


# ---------------------------------------------------------------------------
# 8) 本地模型 qwen3.6 → 费用 0 但 token 照记
# ---------------------------------------------------------------------------


def test_local_model_zero_cost_token_counted(client: TestClient) -> None:
    r = _post_record(
        client,
        model="qwen3.6:27b",
        provider="ollama",
        input_tokens=10_000,
        output_tokens=2_000,
        cache_hit_tokens=0,
    )
    body = r.json()["record"]
    assert body["cost_cents"] == 0
    assert body["input_tokens"] == 10_000
    assert body["output_tokens"] == 2_000
    assert body["pricing_defaulted"] is False  # 在表里

    s = client.get("/api/v1/plugins/ddw_llm_usage/stats/summary?days=7").json()
    assert s["total_tokens"] == 12_000
    assert s["total_cents"] == 0
    assert s["calls"] == 1


# ---------------------------------------------------------------------------
# 9) 附加：按用户分组 + 按日明细
# ---------------------------------------------------------------------------


def test_by_user_grouping(client: TestClient) -> None:
    _post_record(client, user="alice", input_tokens=1_000_000)
    _post_record(client, user="bob", input_tokens=2_000_000)
    _post_record(client, user="bob", input_tokens=0, output_tokens=500_000)

    items = client.get(
        "/api/v1/plugins/ddw_llm_usage/stats/by-user?days=30").json()["items"]
    by = {x["user"]: x for x in items}
    assert by["alice"]["calls"] == 1
    assert by["alice"]["total_cents"] == 100
    assert by["bob"]["calls"] == 2
    # 2M input (200) + 0.5M output (100) = 300 分
    assert by["bob"]["total_cents"] == 300


def test_daily_endpoint_pads_zero_days(client: TestClient) -> None:
    """即使今天没有数据，daily(days=7) 也应返回 7 天的连续日期（零数据日填 0）。"""
    items = client.get(
        "/api/v1/plugins/ddw_llm_usage/stats/daily?days=7").json()["items"]
    assert len(items) == 7
    today = datetime.now(timezone.utc).date().isoformat()
    assert items[-1]["day"] == today
    assert all(it["total_cents"] == 0 for it in items)


# ---------------------------------------------------------------------------
# 10) Plugin 类装配（防止 load_plugins 报 init failed）
# ---------------------------------------------------------------------------


def test_plugin_setup_runs_clean(tmp_path: Path) -> None:
    """模拟底座 load_plugins 的调用形式：Plugin(app, config, manifest, **kwargs)。"""
    app = FastAPI()
    db_path = str(tmp_path / "plugin_test.db")
    plugin = Plugin(
        app=app,
        config={"db_path": db_path},
        manifest={"config": {"db_path": db_path},
            "name": PLUGIN_NAME, "version": VERSION},
        some_extra_kw="ignored",
    )

    assert plugin.name == PLUGIN_NAME
    assert plugin.version == VERSION
    assert plugin.router_prefix == f"/api/v1/plugins/{PLUGIN_NAME}"
    # setup 已被父类 __init__ 自动触发，self.storage 和 self.router 都就绪
    assert plugin.storage is not None
    assert plugin.db_path.exists()
    # 显式再调一次 setup() 也不应崩（幂等，不重复加 routes）
    routes_before = len(plugin.router.routes)
    plugin.setup()
    assert len(plugin.router.routes) == routes_before, "setup() 必须是幂等的"
    # 调 register() 后路由可访问
    plugin.register()
    r = TestClient(app).get(f"{plugin.router_prefix}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["plugin"] == PLUGIN_NAME
    assert body["version"] == VERSION
    assert body["record_count"] == 0


def test_plugin_register_via_parents(tmp_path: Path) -> None:
    """底座走 instance.register()（父类实现）→ app.include_router(self.router)。"""
    app = FastAPI()
    db_path = str(tmp_path / "register_test.db")
    plugin = Plugin(
        app=app,
        config={"db_path": db_path},
        manifest={"config": {"db_path": db_path},
            "name": PLUGIN_NAME, "version": VERSION},
    )
    # register() 走父类实现，把 self.router 挂到 app
    plugin.register()
    # 路由可达
    r = TestClient(app).get(f"{plugin.router_prefix}/prices")
    assert r.status_code == 200
    assert isinstance(r.json()["prices"], list)


def test_default_prices_contract() -> None:
    """任务规约要求 4 个 model 都在默认单价表里。"""
    assert "deepseek-v4-flash" in DEFAULT_PRICES
    assert "minimax-m3" in DEFAULT_PRICES
    assert "mimo-v2.5-pro" in DEFAULT_PRICES
    assert "qwen3.6:27b" in DEFAULT_PRICES
    # 任务规约给的具体值
    assert DEFAULT_PRICES["deepseek-v4-flash"].input_price == 1.0
    assert DEFAULT_PRICES["deepseek-v4-flash"].output_price == 2.0
    assert DEFAULT_PRICES["deepseek-v4-flash"].cache_hit_price == 0.02
    assert DEFAULT_PRICES["mimo-v2.5-pro"].input_price == 3.2
    assert DEFAULT_PRICES["mimo-v2.5-pro"].output_price == 9.6
    assert DEFAULT_PRICES["qwen3.6:27b"].input_price == 0.0


# ---------------------------------------------------------------------------
# 11) 鉴权测试
# ---------------------------------------------------------------------------


def test_put_price_no_admin_key_returns_503(monkeypatch, client: TestClient) -> None:
    """未配置 DDW_LLM_USAGE_ADMIN_KEY 时，PUT prices 返回 503。"""
    monkeypatch.delenv("DDW_LLM_USAGE_ADMIN_KEY", raising=False)
    r = client.put(
        "/api/v1/plugins/ddw_llm_usage/prices/deepseek-v4-flash",
        json={"input_price": 5.0, "output_price": 10.0, "cache_hit_price": 0.5},
    )
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]


def test_put_price_wrong_admin_key_returns_403(client: TestClient) -> None:
    """带错误 X-Admin-Key 时，PUT prices 返回 403。"""
    r = client.put(
        "/api/v1/plugins/ddw_llm_usage/prices/deepseek-v4-flash",
        json={"input_price": 5.0, "output_price": 10.0, "cache_hit_price": 0.5},
        headers={"X-Admin-Key": "wrong-key"},
    )
    assert r.status_code == 403
    assert "Invalid admin key" in r.json()["detail"]


def test_put_price_correct_admin_key_succeeds(client: TestClient) -> None:
    """带正确 X-Admin-Key 时，PUT prices 返回 200。"""
    r = client.put(
        "/api/v1/plugins/ddw_llm_usage/prices/deepseek-v4-flash",
        json={"input_price": 5.0, "output_price": 10.0, "cache_hit_price": 0.5},
        headers=_ADMIN_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["input_price"] == 5.0


def test_delete_price_no_admin_key_returns_503(monkeypatch, client: TestClient) -> None:
    """未配置 DDW_LLM_USAGE_ADMIN_KEY 时，DELETE prices 返回 503。"""
    monkeypatch.delenv("DDW_LLM_USAGE_ADMIN_KEY", raising=False)
    r = client.delete("/api/v1/plugins/ddw_llm_usage/prices/deepseek-v4-flash")
    assert r.status_code == 503


def test_post_record_no_service_key_returns_503(monkeypatch, client: TestClient) -> None:  # noqa: E501
    """未配置 DDW_LLM_USAGE_SERVICE_KEY 时，POST records 返回 503。"""
    monkeypatch.delenv("DDW_LLM_USAGE_SERVICE_KEY", raising=False)
    body = {
        "id": str(uuid.uuid4()),
        "plugin": "ddw_wenqu_tutor",
        "user": "alice",
        "model": "deepseek-v4-flash",
        "provider": "deepseek",
        "input_tokens": 100,
        "output_tokens": 0,
    }
    r = client.post("/api/v1/plugins/ddw_llm_usage/records", json=body)
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]


def test_post_record_wrong_service_key_returns_403(client: TestClient) -> None:
    """带错误 X-Service-Key 时，POST records 返回 403。"""
    body = {
        "id": str(uuid.uuid4()),
        "plugin": "ddw_wenqu_tutor",
        "user": "alice",
        "model": "deepseek-v4-flash",
        "provider": "deepseek",
        "input_tokens": 100,
        "output_tokens": 0,
    }
    r = client.post(
        "/api/v1/plugins/ddw_llm_usage/records",
        json=body,
        headers={"X-Service-Key": "wrong-key"},
    )
    assert r.status_code == 403
    assert "Invalid service key" in r.json()["detail"]
