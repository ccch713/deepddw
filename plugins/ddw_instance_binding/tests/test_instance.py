from __future__ import annotations

"""DDW 实例绑定插件测试用例（8 个 + 扩展）。

覆盖核心 CRUD + 软删除 + 心跳 + 统计 + 校验。
"""

from datetime import datetime, timedelta, timezone

import pytest

from plugins.ddw_instance_binding.schemas import (
    InstanceCreateReq,
    InstanceHeartbeatReq,
    InstanceUpdateReq,
)

# ===========================================================================
# 1. 创建 SaaS 实例
# ===========================================================================


@pytest.mark.asyncio
async def test_create_instance_saas(service_with_deps):
    """创建 SaaS 实例：必填 instance_type=saas + instance_id + company_id。"""
    req = InstanceCreateReq(
        instance_type="saas",
        instance_id="tenant-abc-001",
        instance_name="武汉锐果 - SaaS 租户",
        environment="production",
        endpoint="https://acme.ddw-ai-hub.com",
        company_id=100,
        license_id=200,
    )
    result = await service_with_deps.create(req)
    assert result["id"] is not None
    assert result["instance_type"] == "saas"
    assert result["instance_id"] == "tenant-abc-001"
    assert result["environment"] == "production"
    assert result["status"] == "active"
    assert result["company_id"] == 100
    assert result["license_id"] == 200
    assert result["endpoint"] == "https://acme.ddw-ai-hub.com"
    # 心跳初始为 None
    assert result["last_heartbeat"] is None


# ===========================================================================
# 2. 创建 On-Premise 实例
# ===========================================================================


@pytest.mark.asyncio
async def test_create_instance_on_premise(service_with_deps):
    """创建 On-Premise 实例：staging 环境 + fingerprint。"""
    req = InstanceCreateReq(
        instance_type="on-premise",
        instance_id="onprem-uuid-7f3a-9c2e",
        instance_name="客户内网 - 预发",
        environment="staging",
        fingerprint="sha256:abcd1234efgh5678",
        endpoint="https://10.0.0.50:8443",
        company_id=100,
    )
    result = await service_with_deps.create(req)
    assert result["id"] is not None
    assert result["instance_type"] == "on-premise"
    assert result["instance_id"] == "onprem-uuid-7f3a-9c2e"
    assert result["environment"] == "staging"
    assert result["fingerprint"] == "sha256:abcd1234efgh5678"
    assert result["status"] == "active"
    assert result["license_id"] is None  # 只传 company_id


# ===========================================================================
# 3. 列表筛选：按 instance_type
# ===========================================================================


@pytest.mark.asyncio
async def test_list_instances_filter_by_type(service_with_deps):
    """列表筛选：按 instance_type=saas 过滤。"""
    # 3 saas + 2 on-premise
    for i in range(3):
        await service_with_deps.create(
            InstanceCreateReq(
                instance_type="saas",
                instance_id=f"saas-{i:03d}",
                company_id=100,
            )
        )
    for i in range(2):
        await service_with_deps.create(
            InstanceCreateReq(
                instance_type="on-premise",
                instance_id=f"onprem-{i:03d}",
                company_id=100,
            )
        )

    only_saas = await service_with_deps.list(
        page=1, page_size=20, instance_type="saas"
    )
    assert only_saas.total == 3
    assert all(x.instance_type == "saas" for x in only_saas.items)

    only_on_prem = await service_with_deps.list(
        page=1, page_size=20, instance_type="on-premise"
    )
    assert only_on_prem.total == 2
    assert all(x.instance_type == "on-premise" for x in only_on_prem.items)

    all_inst = await service_with_deps.list(page=1, page_size=20)
    assert all_inst.total == 5


# ===========================================================================
# 4. 实例详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_instance_detail(service_with_deps):
    """获取实例详情。"""
    created = await service_with_deps.create(
        InstanceCreateReq(
            instance_type="saas",
            instance_id="detail-test-001",
            instance_name="详情测试",
            company_id=100,
        )
    )
    iid = created["id"]

    detail = await service_with_deps.get(iid)
    assert detail is not None
    assert detail["id"] == iid
    assert detail["instance_id"] == "detail-test-001"
    assert detail["instance_name"] == "详情测试"
    assert detail["company_id"] == 100

    # 不存在
    assert await service_with_deps.get(99999) is None


# ===========================================================================
# 5. 更新实例
# ===========================================================================


@pytest.mark.asyncio
async def test_update_instance(service_with_deps):
    """更新实例：改名 / 改环境 / 改 endpoint / 改 status。"""
    created = await service_with_deps.create(
        InstanceCreateReq(
            instance_type="saas",
            instance_id="upd-001",
            instance_name="旧名",
            environment="test",
            company_id=100,
        )
    )
    iid = created["id"]

    upd = InstanceUpdateReq(
        instance_name="新名",
        environment="production",
        endpoint="https://prod.ddw-ai-hub.com",
        status="active",
    )
    result = await service_with_deps.update(iid, upd)
    assert result is not None
    assert result["instance_name"] == "新名"
    assert result["environment"] == "production"
    assert result["endpoint"] == "https://prod.ddw-ai-hub.com"
    # 不可改字段保持原值
    assert result["instance_id"] == "upd-001"
    assert result["company_id"] == 100


# ===========================================================================
# 6. 心跳：更新 last_heartbeat
# ===========================================================================


@pytest.mark.asyncio
async def test_heartbeat_updates_last_heartbeat(service_with_deps):
    """心跳上报：last_heartbeat 被更新为 now()。"""
    created = await service_with_deps.create(
        InstanceCreateReq(
            instance_type="saas",
            instance_id="hb-001",
            company_id=100,
        )
    )
    iid = created["id"]
    assert created["last_heartbeat"] is None

    before = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await service_with_deps.heartbeat(iid)
    after = datetime.now(timezone.utc).replace(tzinfo=None)

    assert result is not None
    assert result["last_heartbeat"] is not None
    # last_heartbeat 在 before/after 区间内
    assert before - timedelta(seconds=1) <= result["last_heartbeat"] <= after + timedelta(seconds=1)


@pytest.mark.asyncio
async def test_heartbeat_with_status_change(service_with_deps):
    """心跳可同时更新 status（active <-> inactive 切换，suspended 拒绝）。"""
    created = await service_with_deps.create(
        InstanceCreateReq(
            instance_type="saas",
            instance_id="hb-002",
            company_id=100,
        )
    )
    iid = created["id"]
    assert created["status"] == "active"

    # 切到 inactive
    result = await service_with_deps.heartbeat(
        iid, InstanceHeartbeatReq(status="inactive")
    )
    assert result["status"] == "inactive"
    assert result["last_heartbeat"] is not None

    # 切回 active
    result = await service_with_deps.heartbeat(
        iid, InstanceHeartbeatReq(status="active")
    )
    assert result["status"] == "active"

    # 不允许通过心跳变 suspended
    with pytest.raises(ValueError, match="不允许改为 suspended"):
        await service_with_deps.heartbeat(
            iid, InstanceHeartbeatReq(status="suspended")
        )


# ===========================================================================
# 7. 软删除（suspend）
# ===========================================================================


@pytest.mark.asyncio
async def test_suspend_instance(service_with_deps):
    """软删除：status 变 suspended，DB 中仍存在。"""
    created = await service_with_deps.create(
        InstanceCreateReq(
            instance_type="saas",
            instance_id="susp-001",
            company_id=100,
        )
    )
    iid = created["id"]
    assert created["status"] == "active"

    result = await service_with_deps.suspend(iid)
    assert result is not None
    assert result["status"] == "suspended"

    # DB 中仍存在（get 能查到）
    detail = await service_with_deps.get(iid)
    assert detail is not None
    assert detail["status"] == "suspended"

    # 从默认列表（status=active）中找不到
    page = await service_with_deps.list(page=1, page_size=20, status="active")
    assert all(x.id != iid for x in page.items)

    # 但 status=suspended 能找到
    only_susp = await service_with_deps.list(page=1, page_size=20, status="suspended")
    assert any(x.id == iid for x in only_susp.items)


# ===========================================================================
# 8. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service_with_deps):
    """统计：total/active/inactive/suspended + by_type + by_environment + heartbeat_alive。"""
    # 3 active saas production
    for i in range(3):
        await service_with_deps.create(
            InstanceCreateReq(
                instance_type="saas",
                instance_id=f"stats-saas-{i}",
                environment="production",
                company_id=100,
            )
        )
    # 2 active on-premise staging
    for i in range(2):
        await service_with_deps.create(
            InstanceCreateReq(
                instance_type="on-premise",
                instance_id=f"stats-op-{i}",
                environment="staging",
                company_id=100,
            )
        )
    # 1 inactive
    i_inst = await service_with_deps.create(
        InstanceCreateReq(
            instance_type="saas",
            instance_id="stats-inactive",
            environment="test",
            company_id=100,
        )
    )
    await service_with_deps.update(
        i_inst["id"], InstanceUpdateReq(status="inactive")
    )
    # 1 suspended
    s_inst = await service_with_deps.create(
        InstanceCreateReq(
            instance_type="saas",
            instance_id="stats-suspended",
            company_id=100,
        )
    )
    await service_with_deps.suspend(s_inst["id"])
    # 1 active saas production 上报心跳
    hb_inst = await service_with_deps.create(
        InstanceCreateReq(
            instance_type="saas",
            instance_id="stats-hb",
            environment="production",
            company_id=100,
        )
    )
    await service_with_deps.heartbeat(hb_inst["id"])

    stats = await service_with_deps.stats()
    # total: 3 saas production + 2 on-premise staging + 1 inactive + 1 suspended + 1 hb
    #     = 3 + 2 + 1 + 1 + 1 = 8
    assert stats.total == 8
    assert stats.active == 6  # 3 production + 2 staging + 1 hb
    assert stats.inactive == 1
    assert stats.suspended == 1
    # by_instance_type: saas=6, on-premise=2
    assert stats.by_instance_type.get("saas") == 6
    assert stats.by_instance_type.get("on-premise") == 2
    # by_environment: production=5 (3 active saas + 1 suspended saas + 1 hb saas), staging=2, test=1
    assert stats.by_environment.get("production") == 5
    assert stats.by_environment.get("staging") == 2
    assert stats.by_environment.get("test") == 1
    # heartbeat_alive: 24h 内有 1 个（stats-hb）
    assert stats.heartbeat_alive == 1


# ===========================================================================
# 9. 额外：校验（业务规则）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_instance_rejects_missing_company_and_license(service):
    """至少 company_id / license_id 传一个，否则 ValueError。"""
    req = InstanceCreateReq(
        instance_type="saas",
        instance_id="orphan-001",
    )
    with pytest.raises(ValueError, match="至少传一个"):
        await service.create(req)


@pytest.mark.asyncio
async def test_create_instance_rejects_invalid_type(service_with_deps):
    """instance_type 必须在白名单内。"""
    req = InstanceCreateReq(
        instance_type="cloud",  # 非法
        instance_id="bad-type-001",
        company_id=100,
    )
    with pytest.raises(ValueError, match="instance_type"):
        await service_with_deps.create(req)


@pytest.mark.asyncio
async def test_create_instance_rejects_duplicate(service_with_deps):
    """同一 (tenant, instance_id, environment) 不能重复绑定。"""
    req = InstanceCreateReq(
        instance_type="saas",
        instance_id="dup-001",
        company_id=100,
    )
    await service_with_deps.create(req)
    with pytest.raises(ValueError, match="已存在"):
        await service_with_deps.create(req)
