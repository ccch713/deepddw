"""ddw_personnel_qual 单元 + 集成测试。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from plugins.ddw_personnel_qual.services.cert_service import parse_csv
from plugins.ddw_personnel_qual.services.expiry_service import _bucket

# ---------------------------------------------------------------------------
# 纯函数：CSV 解析
# ---------------------------------------------------------------------------


def test_parse_csv_basic():
    csv = "person_name,person_id,cert_type,cert_no\n张三,ZS001,注册结构师,SJ-001\n李四,LS002,注册建筑师,JZ-002"
    headers, rows = parse_csv(csv, skip_header=True)
    assert headers == ["person_name", "person_id", "cert_type", "cert_no"]
    assert len(rows) == 2
    assert rows[0]["person_name"] == "张三"
    assert rows[1]["cert_type"] == "注册建筑师"


def test_parse_csv_with_blank_lines():
    csv = "a,b\n1,2\n\n3,4\n"
    _, rows = parse_csv(csv, skip_header=True)
    assert len(rows) == 2


def test_parse_csv_no_header():
    csv = "1,2\n3,4"
    headers, rows = parse_csv(csv, skip_header=False)
    # skip_header=False 时自动生成 col_0/col_1 列名，全部行都是数据
    assert headers == ["col_0", "col_1"]
    assert rows == [{"col_0": "1", "col_1": "2"}, {"col_0": "3", "col_1": "4"}]


# ---------------------------------------------------------------------------
# 纯函数：到期分档
# ---------------------------------------------------------------------------


def test_bucket():
    today = date(2026, 1, 1)
    assert _bucket(-5) == "expired"
    assert _bucket(0) == "within_30"
    assert _bucket(15) == "within_30"
    assert _bucket(30) == "within_30"
    assert _bucket(31) == "within_60"
    assert _bucket(60) == "within_60"
    assert _bucket(61) == "within_90"
    assert _bucket(90) == "within_90"
    assert _bucket(180) == "ok"


# ---------------------------------------------------------------------------
# 集成：CRUD + 筛选 + 统计 + 到期 + 年检
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cert_crud(db_session, cert_service, seeded_tenant):

    payload = {
        "tenant_id": seeded_tenant,
        "person_name": "张三",
        "person_id": "ZS001",
        "cert_type": "注册结构师",
        "cert_no": "SJ-2020-001",
        "cert_level": "一级",
        "issue_org": "住建部",
        "issue_date": date(2020, 3, 1),
        "expiry_date": date(2026, 3, 1),
        "status": "active",
    }
    c = await cert_service.create(db_session, payload)
    assert c.id is not None
    await db_session.commit()

    # get
    g = await cert_service.get(db_session, c.id)
    assert g.cert_no == "SJ-2020-001"

    # list
    total, items = await cert_service.list(db_session, page=1, page_size=10)
    assert total == 1
    assert items[0].person_name == "张三"

    # filter
    total2, _ = await cert_service.list(db_session, cert_type="注册建筑师")
    assert total2 == 0

    # update
    u = await cert_service.update(db_session, c.id, {"cert_level": "二级"})
    assert u.cert_level == "二级"

    # delete
    ok = await cert_service.delete(db_session, c.id)
    assert ok is True
    total3, _ = await cert_service.list(db_session)
    assert total3 == 0


@pytest.mark.asyncio
async def test_cert_list_by_person(db_session, cert_service, seeded_tenant):
    base = {
        "tenant_id": seeded_tenant,
        "person_id": "ZS001",
        "cert_type": "注册结构师",
        "cert_no": "SJ-001",
        "status": "active",
    }
    await cert_service.create(db_session, {**base, "person_name": "张三"})
    await cert_service.create(db_session, {**base, "cert_no": "SJ-002", "person_name": "张三"})
    await cert_service.create(db_session, {**base, "person_id": "LS002", "person_name": "李四"})
    await db_session.commit()

    rows = await cert_service.list_by_person(db_session, "ZS001")
    assert len(rows) == 2
    assert all(r.person_id == "ZS001" for r in rows)


@pytest.mark.asyncio
async def test_cert_stats(db_session, cert_service, seeded_tenant):
    rows = [
        ("注册结构师", "一级", "active"),
        ("注册结构师", "二级", "active"),
        ("注册建筑师", "一级", "expired"),
        ("高级工程师", "高级", "renewing"),
    ]
    for i, (t, lv, st) in enumerate(rows):
        await cert_service.create(db_session, {
            "tenant_id": seeded_tenant,
            "person_name": f"人员{i}",
            "person_id": f"P{i:03d}",
            "cert_type": t,
            "cert_no": f"C{i:03d}",
            "cert_level": lv,
            "status": st,
        })
    await db_session.commit()

    s = await cert_service.stats(db_session)
    assert s["total"] == 4
    assert s["active"] == 2
    assert s["expired"] == 1
    assert s["renewing"] == 1
    assert s["by_type"]["注册结构师"] == 2
    assert s["by_level"]["一级"] == 2


@pytest.mark.asyncio
async def test_expiry_scan_within_30(db_session, cert_service, expiry_service, seeded_tenant):
    today = date.today()
    # 7 天后到期 → within_30
    await cert_service.create(db_session, {
        "tenant_id": seeded_tenant, "person_name": "王五", "person_id": "WW",
        "cert_type": "注册结构师", "cert_no": "X1",
        "expiry_date": today + timedelta(days=7), "status": "active",
    })
    # 已过期
    await cert_service.create(db_session, {
        "tenant_id": seeded_tenant, "person_name": "赵六", "person_id": "ZL",
        "cert_type": "注册建筑师", "cert_no": "X2",
        "expiry_date": today - timedelta(days=10), "status": "expired",
    })
    # 长期有效
    await cert_service.create(db_session, {
        "tenant_id": seeded_tenant, "person_name": "钱七", "person_id": "QQ",
        "cert_type": "工程师", "cert_no": "X3",
        "expiry_date": today + timedelta(days=365), "status": "active",
    })
    await db_session.commit()

    data = await expiry_service.scan(db_session, persist=True)
    await db_session.commit()
    assert data["within_30"] == 1
    assert data["expired"] == 1
    assert any(item["person_name"] == "王五" for item in data["items"])
    assert any(item["person_name"] == "赵六" for item in data["items"])

    # 再次 scan 不应重复产生告警
    await expiry_service.scan(db_session, persist=True)
    await db_session.commit()
    alerts = await expiry_service.list_alerts(db_session)
    # expired 1 + within_30 1
    assert alerts["total"] == 2
    assert alerts["unread"] == 2


@pytest.mark.asyncio
async def test_renewal_lifecycle(db_session, cert_service, renewal_service, seeded_tenant):
    c = await cert_service.create(db_session, {
        "tenant_id": seeded_tenant, "person_name": "孙八", "person_id": "SB",
        "cert_type": "高级工程师", "cert_no": "GJ-001",
        "status": "active",
    })
    await db_session.commit()

    # 发起年检
    r = await renewal_service.create(db_session, {
        "tenant_id": seeded_tenant,
        "cert_id": c.id,
        "renewal_date": date(2026, 6, 1),
        "operator": "张主任",
        "status": "pending",
    })
    assert r.id is not None
    # cert 应该被同步到 renewing
    c2 = await cert_service.get(db_session, c.id)
    assert c2.status == "renewing"
    assert c2.renewal_date == date(2026, 6, 1)
    await db_session.commit()

    # 更新年检通过
    r2 = await renewal_service.update(db_session, r.id, {"status": "passed", "result": "通过"})
    assert r2.status == "passed"
    c3 = await cert_service.get(db_session, c.id)
    assert c3.status == "active"
    await db_session.commit()

    # 列表
    listed = await renewal_service.list(db_session, cert_id=c.id)
    assert listed["total"] == 1


@pytest.mark.asyncio
async def test_csv_export(db_session, cert_service, seeded_tenant):
    await cert_service.create(db_session, {
        "tenant_id": seeded_tenant, "person_name": "周九", "person_id": "ZJ",
        "cert_type": "注册电气工程师", "cert_no": "DQ-001",
        "expiry_date": date(2027, 1, 1), "status": "active",
    })
    await db_session.commit()
    csv = await cert_service.export_csv(db_session)
    assert "周九" in csv
    assert "注册电气工程师" in csv
    assert "DQ-001" in csv
    # 表头
    assert "person_name" in csv.splitlines()[0]


@pytest.mark.asyncio
async def test_import_rows(db_session, cert_service, seeded_tenant):
    rows = [
        {"tenant_id": seeded_tenant, "person_name": "吴十", "person_id": "WS", "cert_type": "工程师", "cert_no": "GC-001", "status": "active"},
        {"tenant_id": seeded_tenant, "person_name": "郑十一", "person_id": "ZSY", "cert_type": "高级工程师", "cert_no": "GJ-002", "status": "active", "expiry_date": "2030-12-31"},
    ]
    result = await cert_service.import_rows(db_session, rows)
    await db_session.commit()
    assert result["success"] == 2
    assert result["failed"] == 0
    total, items = await cert_service.list(db_session)
    assert total == 2
    # 日期字符串被解析
    assert any(i.expiry_date == date(2030, 12, 31) for i in items)


# ---------------------------------------------------------------------------
# Router 集成（端到端，验证路径注册）
# ---------------------------------------------------------------------------


def test_router_has_14_routes():
    """验证 router 包含 14 个 API 端点。"""
    from plugins.ddw_personnel_qual.router import build_router

    class _StubPlugin:
        name = "ddw-personnel-qual"
        cert_service = type("S", (), {})()
        expiry_service = type("S", (), {})()
        renewal_service = type("S", (), {})()

    r = build_router(_StubPlugin())
    # FastAPI 把 prefix 拼到 route.path 上，按 (full_path, method) 收集体
    collected: dict[str, set[str]] = {}
    for route in r.routes:
        # 跳过非 APIRoute（Mount、Redirect 等）
        if not hasattr(route, "methods"):
            continue
        # 跳过 UI 页面路由（不进 OpenAPI 的 include_in_schema=False 路由）
        if getattr(route, "include_in_schema", True) is False:
            continue
        for m in route.methods:
            collected.setdefault(route.path, set()).add(m)

    # 14 个 endpoint = 14 个 (path, method) 对（FastAPI 会合并同 path 不同 method）
    total_endpoints = sum(len(m) for m in collected.values())
    assert total_endpoints == 15, f"expected 15 endpoints, got {total_endpoints}: {collected}"

    # 校验每个端点存在并有预期 method
    prefix = "/api/v1/plugins/ddw-personnel-qual"
    expectations = [
        (f"{prefix}/certs", "GET"),
        (f"{prefix}/certs", "POST"),
        (f"{prefix}/certs/import", "POST"),
        (f"{prefix}/certs/export", "GET"),
        (f"{prefix}/certs/{{cert_id}}", "GET"),
        (f"{prefix}/certs/{{cert_id}}", "PUT"),
        (f"{prefix}/certs/{{cert_id}}", "DELETE"),
        (f"{prefix}/expiring", "GET"),
        (f"{prefix}/stats", "GET"),
        (f"{prefix}/persons/{{person_id}}/certs", "GET"),
        (f"{prefix}/renewals", "POST"),
        (f"{prefix}/renewals", "GET"),
        (f"{prefix}/renewals/{{renewal_id}}", "PUT"),
        (f"{prefix}/alerts", "GET"),
    ]
    for path, method in expectations:
        assert path in collected, f"missing path: {path}"
        assert method in collected[path], f"missing method {method} on {path}: got {collected[path]}"
