from __future__ import annotations

"""DDW 许可证管理插件测试用例（13 个）。

覆盖核心 CRUD + 自动过期检查 + 状态机 + 续费 + 统计 + 筛选。
"""

from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc

import pytest

from plugins.ddw_license_core.schemas import (
    LicenseCreateReq,
    LicenseRenewalReq,
    LicenseUpdateReq,
)


def _today() -> date:
    """今天（UTC）。"""
    return datetime.now(UTC).date()


# ===========================================================================
# 1. 新建许可证
# ===========================================================================


@pytest.mark.asyncio
async def test_create_license(service):
    """正常创建许可证：自动 license_no，状态默认 active。"""
    req = LicenseCreateReq(
        license_type="formal",
        plugin_entitlements=["ddw-crm-core", "ddw-voice-capture"],
        max_users=20,
        max_nodes=2,
        valid_from=_today(),
        valid_to=_today() + timedelta(days=365),
        notes="2026 智造项目正式授权",
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["license_no"].startswith("LIC-")
    assert result["license_type"] == "formal"
    assert result["status"] == "active"
    assert result["max_users"] == 20
    assert result["max_nodes"] == 2
    assert result["plugin_entitlements"] == ["ddw-crm-core", "ddw-voice-capture"]


# ===========================================================================
# 2. license_no 自动生成（同日递增）
# ===========================================================================


@pytest.mark.asyncio
async def test_license_no_auto_generation(service):
    """同日创建的 license_no 必须自增（LIC-YYYYMMDD-001, 002, ...）。"""
    for _ in range(3):
        await service.create(
            LicenseCreateReq(
                license_type="trial",
                valid_from=_today(),
                valid_to=_today() + timedelta(days=30),
            )
        )

    page = await service.list(page=1, page_size=20)
    nos = [item.license_no for item in page.items]
    # 全部以 LIC-YYYYMMDD- 开头
    assert all(n.startswith("LIC-") for n in nos)
    # 末段序号必须唯一
    suffixes = [n.rsplit("-", 1)[-1] for n in nos]
    assert len(set(suffixes)) == 3
    # 自增：解析为整数后排序
    seqs = sorted(int(s) for s in suffixes)
    assert seqs == [1, 2, 3]


# ===========================================================================
# 3. 列表（分页）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_licenses_paginated(service):
    """分页：插入 25 条，page=1/2/3 验证。"""
    for i in range(25):
        await service.create(
            LicenseCreateReq(
                license_type="trial" if i % 2 == 0 else "formal",
                max_users=10 + i,
                valid_from=_today(),
                valid_to=_today() + timedelta(days=30 + i),
            )
        )

    p1 = await service.list(page=1, page_size=10)
    p2 = await service.list(page=2, page_size=10)
    p3 = await service.list(page=3, page_size=10)

    assert p1.total == 25
    assert len(p1.items) == 10
    assert len(p2.items) == 10
    assert p3.page == 3
    assert len(p3.items) == 5  # 最后一页只有 5 条


# ===========================================================================
# 4. 列表（按状态筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_licenses_filter_by_status(service):
    """按 status 筛选：suspend 一个，验证列表中能正确筛出。"""
    a = await service.create(
        LicenseCreateReq(
            license_type="formal",
            valid_from=_today(),
            valid_to=_today() + timedelta(days=30),
        )
    )
    b = await service.create(
        LicenseCreateReq(
            license_type="formal",
            valid_from=_today(),
            valid_to=_today() + timedelta(days=30),
        )
    )
    await service.suspend(b["id"])  # b -> suspended

    only_suspended = await service.list(page=1, page_size=20, status="suspended")
    assert only_suspended.total == 1
    assert only_suspended.items[0].id == b["id"]

    only_active = await service.list(page=1, page_size=20, status="active")
    assert only_active.total == 1
    assert only_active.items[0].id == a["id"]


# ===========================================================================
# 5. 许可证详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_license_detail(service):
    """获取详情。"""
    created = await service.create(
        LicenseCreateReq(
            license_type="formal",
            product_ids=[101, 102],
            plugin_entitlements=["ddw-crm-core"],
            max_users=50,
            max_nodes=3,
            valid_from=_today(),
            valid_to=_today() + timedelta(days=365),
        )
    )
    lid = created["id"]
    detail = await service.get(lid)
    assert detail is not None
    assert detail["id"] == lid
    assert detail["license_type"] == "formal"
    assert detail["product_ids"] == [101, 102]
    assert detail["max_users"] == 50

    # 不存在
    assert await service.get(99999) is None


# ===========================================================================
# 6. 更新许可证
# ===========================================================================


@pytest.mark.asyncio
async def test_update_license(service):
    """更新许可证：调整 max_users / notes / plugin_entitlements。"""
    created = await service.create(
        LicenseCreateReq(
            license_type="formal",
            max_users=10,
            valid_from=_today(),
            valid_to=_today() + timedelta(days=365),
            notes="初版",
        )
    )
    lid = created["id"]

    upd = LicenseUpdateReq(
        max_users=50,
        notes="扩容到 50 用户",
        plugin_entitlements=["ddw-crm-core", "ddw-voice-capture", "ddw-license-core"],
    )
    result = await service.update(lid, upd)
    assert result is not None
    assert result["max_users"] == 50
    assert result["notes"] == "扩容到 50 用户"
    assert len(result["plugin_entitlements"]) == 3


@pytest.mark.asyncio
async def test_update_license_blocked_for_revoked(service):
    """已吊销的许可证不能再 update（保护审计链）。"""
    created = await service.create(
        LicenseCreateReq(
            license_type="formal",
            valid_from=_today(),
            valid_to=_today() + timedelta(days=365),
        )
    )
    lid = created["id"]
    await service.revoke(lid)

    with pytest.raises(ValueError, match="不允许修改"):
        await service.update(lid, LicenseUpdateReq(notes="试图修改"))


# ===========================================================================
# 7. 状态机：suspend / resume
# ===========================================================================


@pytest.mark.asyncio
async def test_suspend_resume(service):
    """active -> suspended -> active 状态机迁移。"""
    created = await service.create(
        LicenseCreateReq(
            license_type="formal",
            valid_from=_today(),
            valid_to=_today() + timedelta(days=30),
        )
    )
    lid = created["id"]
    assert created["status"] == "active"

    suspended = await service.suspend(lid)
    assert suspended is not None
    assert suspended["status"] == "suspended"

    resumed = await service.resume(lid)
    assert resumed is not None
    assert resumed["status"] == "active"

    # suspended -> renewed 是非法迁移（suspended 只能 active 或 revoked）
    await service.suspend(lid)  # 重新 suspend
    with pytest.raises(ValueError, match="invalid transition"):
        await service._transition(lid, "renewed")


# ===========================================================================
# 8. 状态机：revoke（终态）
# ===========================================================================


@pytest.mark.asyncio
async def test_revoke_license(service):
    """revoke 后许可证进入终态：不能再 suspend / resume / update。"""
    created = await service.create(
        LicenseCreateReq(
            license_type="formal",
            valid_from=_today(),
            valid_to=_today() + timedelta(days=30),
        )
    )
    lid = created["id"]

    revoked = await service.revoke(lid)
    assert revoked is not None
    assert revoked["status"] == "revoked"

    # 终态不能 resume
    with pytest.raises(ValueError, match="invalid transition"):
        await service.resume(lid)

    # 终态不能再次 revoke
    with pytest.raises(ValueError, match="invalid transition"):
        await service.revoke(lid)


@pytest.mark.asyncio
async def test_revoke_from_suspended(service):
    """suspended 状态的许可证也可以被 revoke。"""
    created = await service.create(
        LicenseCreateReq(
            license_type="formal",
            valid_from=_today(),
            valid_to=_today() + timedelta(days=30),
        )
    )
    lid = created["id"]
    await service.suspend(lid)
    revoked = await service.revoke(lid)
    assert revoked["status"] == "revoked"


# ===========================================================================
# 9. 自动过期检查（核心业务规则）
# ===========================================================================


@pytest.mark.asyncio
async def test_expired_auto_mark(service):
    """造 valid_to < today 的许可证，验证 list 时自动标记为 expired。

    这是核心业务规则：read 类操作（list / get / stats）前会先
    _auto_mark_expired 批量把 active 且 valid_to<today 的标记为 expired。
    """
    # 直接插入一个早已过期的 active 许可证
    expired = await service.create(
        LicenseCreateReq(
            license_type="trial",
            valid_from=_today() - timedelta(days=60),
            valid_to=_today() - timedelta(days=10),  # 10 天前到期
        )
    )
    lid = expired["id"]
    # create 后仍是 active（不在 create 时改，避免并发问题）
    assert expired["status"] == "active"

    # 触发 list —— 内部会先 _auto_mark_expired
    page = await service.list(page=1, page_size=20)
    refreshed = next(x for x in page.items if x.id == lid)
    assert refreshed.status == "expired"

    # get 也会触发
    detail = await service.get(lid)
    assert detail["status"] == "expired"

    # stats 中也应是 expired
    stats = await service.stats()
    assert stats.expired == 1
    assert stats.active == 0


# ===========================================================================
# 10. 续费
# ===========================================================================


@pytest.mark.asyncio
async def test_renewal_creates_new_license(service_with_company):
    """续费：创建新许可证，旧许可证变 renewed，新许可证 type=renewal。

    新许可证的 parent_license_id 指向旧许可证。
    """
    svc = service_with_company
    old = await svc.create(
        LicenseCreateReq(
            company_id=100,
            license_type="formal",
            plugin_entitlements=["ddw-crm-core"],
            max_users=10,
            valid_from=_today() - timedelta(days=30),
            valid_to=_today() + timedelta(days=30),
        )
    )
    old_id = old["id"]
    old_no = old["license_no"]
    assert old["status"] == "active"

    # 续费请求
    renew_req = LicenseRenewalReq(
        max_users=20,
        notes="2027 续费",
    )
    new = await svc.renewal(old_id, renew_req)
    assert new is not None
    assert new["id"] != old_id
    assert new["license_type"] == "renewal"
    assert new["parent_license_id"] == old_id
    assert new["max_users"] == 20  # 使用 renew_req 传的
    assert new["plugin_entitlements"] == ["ddw-crm-core"]  # 继承旧的
    assert new["company_id"] == 100
    assert new["status"] == "active"
    # 单号必须不同
    assert new["license_no"] != old_no

    # 旧许可证状态变更为 renewed
    old_after = await svc.get(old_id)
    assert old_after["status"] == "renewed"


@pytest.mark.asyncio
async def test_renewal_blocked_for_revoked(service):
    """已吊销（revoked）的许可证不能再续费。"""
    created = await service.create(
        LicenseCreateReq(
            license_type="formal",
            valid_from=_today(),
            valid_to=_today() + timedelta(days=30),
        )
    )
    lid = created["id"]
    await service.revoke(lid)

    with pytest.raises(ValueError, match="不允许续费"):
        await service.renewal(lid, LicenseRenewalReq())


# ===========================================================================
# 11. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service_with_company):
    """统计：total / 各状态计数 / by_license_type / active 容量合计。

    构造场景：
    - 2 active formal（max_users 10+20=30, max_nodes 1+2=3）
    - 1 active trial
    - 1 suspended
    - 1 revoked
    - 1 已过期（valid_to<today，list 时被自动标记）
    """
    svc = service_with_company
    # 2 active formal
    await svc.create(
        LicenseCreateReq(
            license_type="formal", max_users=10, max_nodes=1,
            company_id=100,
            valid_from=_today(), valid_to=_today() + timedelta(days=30),
        )
    )
    await svc.create(
        LicenseCreateReq(
            license_type="formal", max_users=20, max_nodes=2,
            company_id=100,
            valid_from=_today(), valid_to=_today() + timedelta(days=30),
        )
    )
    # 1 active trial
    await svc.create(
        LicenseCreateReq(
            license_type="trial", max_users=5, max_nodes=1,
            valid_from=_today(), valid_to=_today() + timedelta(days=7),
        )
    )
    # 1 suspended
    s = await svc.create(
        LicenseCreateReq(
            license_type="formal", max_users=8, max_nodes=1,
            valid_from=_today(), valid_to=_today() + timedelta(days=30),
        )
    )
    await svc.suspend(s["id"])
    # 1 revoked
    r = await svc.create(
        LicenseCreateReq(
            license_type="formal", max_users=8, max_nodes=1,
            valid_from=_today(), valid_to=_today() + timedelta(days=30),
        )
    )
    await svc.revoke(r["id"])
    # 1 已过期（list 时被自动标记）
    await svc.create(
        LicenseCreateReq(
            license_type="trial", max_users=3, max_nodes=1,
            valid_from=_today() - timedelta(days=60),
            valid_to=_today() - timedelta(days=10),
        )
    )

    stats = await svc.stats()
    assert stats.total == 6
    assert stats.active == 3  # 2 formal + 1 trial
    assert stats.suspended == 1
    assert stats.revoked == 1
    assert stats.expired == 1
    # by_license_type: formal=4 (2 active + 1 suspended + 1 revoked), trial=2
    assert stats.by_license_type.get("formal") == 4
    assert stats.by_license_type.get("trial") == 2
    # active 容量合计：2 active formal (10+20=30) + 1 active trial (5) = 35 users, 1+2+1=4 nodes
    assert stats.active_total_users == 35
    assert stats.active_total_nodes == 4


# ===========================================================================
# 12. 按企业筛选
# ===========================================================================


@pytest.mark.asyncio
async def test_filter_by_company(service_with_company):
    """按 company_id 筛选：只返回该企业的许可证。"""
    svc = service_with_company
    # 关联企业 100（已 seed）
    await svc.create(
        LicenseCreateReq(
            company_id=100, license_type="formal",
            valid_from=_today(), valid_to=_today() + timedelta(days=30),
        )
    )
    await svc.create(
        LicenseCreateReq(
            company_id=100, license_type="trial",
            valid_from=_today(), valid_to=_today() + timedelta(days=7),
        )
    )
    # 无关联企业的许可证
    await svc.create(
        LicenseCreateReq(
            license_type="trial",
            valid_from=_today(), valid_to=_today() + timedelta(days=7),
        )
    )

    p = await svc.list(page=1, page_size=20, company_id=100)
    assert p.total == 2
    assert {x.license_type for x in p.items} == {"formal", "trial"}

    # 无 company_id 筛选：3 条全返回
    p_all = await svc.list(page=1, page_size=20)
    assert p_all.total == 3

    # 显式传 company_id=None 等同于无筛选（这里用 status 反证）
    p_active = await svc.list(page=1, page_size=20, status="active")
    assert p_active.total == 3


@pytest.mark.asyncio
async def test_filter_by_valid_to_range(service):
    """按 valid_to 范围筛选。"""
    await service.create(
        LicenseCreateReq(
            license_type="trial",
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 3, 31),
        )
    )
    await service.create(
        LicenseCreateReq(
            license_type="trial",
            valid_from=date(2026, 4, 1),
            valid_to=date(2026, 6, 30),
        )
    )
    await service.create(
        LicenseCreateReq(
            license_type="trial",
            valid_from=date(2026, 7, 1),
            valid_to=date(2026, 12, 31),
        )
    )

    # valid_to 在 2026-04-01 ~ 2026-09-30 之间：只命中"中期"（6/30）
    p = await service.list(
        page=1, page_size=20,
        valid_to_after=date(2026, 4, 1),
        valid_to_before=date(2026, 9, 30),
    )
    assert p.total == 1


# ===========================================================================
# 13. 创建校验：valid_to < valid_from
# ===========================================================================


@pytest.mark.asyncio
async def test_create_license_invalid_date_range(service):
    """valid_to 早于 valid_from 应抛 ValueError。"""
    req = LicenseCreateReq(
        license_type="trial",
        valid_from=date(2026, 6, 1),
        valid_to=date(2026, 1, 1),  # 早于 valid_from
    )
    with pytest.raises(ValueError, match="早于"):
        await service.create(req)
