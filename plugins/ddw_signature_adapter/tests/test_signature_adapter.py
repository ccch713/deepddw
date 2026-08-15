from __future__ import annotations

"""DDW 电子签章适配器插件测试用例（8 个）。

覆盖：创建 / 列表分页 / 筛选 / 详情 / 更新 / 回调 / 人工上传 / 统计。
"""

import pytest

from plugins.ddw_signature_adapter.schemas import (
    CallbackReq,
    ManualUploadReq,
    SignatureRequestCreateReq,
    SignatureRequestUpdateReq,
    SignerItem,
)

# ===========================================================================
# 1. 新建签署请求
# ===========================================================================


@pytest.mark.asyncio
async def test_create_signature_request(service_with_contract):
    """正常创建签署请求：状态默认 pending，signers 自动转 dict 列表。"""
    svc = service_with_contract
    req = SignatureRequestCreateReq(
        contract_id=200,
        provider="tencent",
        signers=[
            SignerItem(name="张三", phone="13800000001", role="buyer"),
            SignerItem(name="李四", phone="13800000002", role="seller"),
        ],
        document_url="https://example.com/contract-200.pdf",
        notes="2026 Q1 框架合同",
        created_by=42,
    )
    result = await svc.create(req)
    assert result["id"] is not None
    assert result["provider"] == "tencent"
    assert result["contract_id"] == 200
    assert result["status"] == "pending"
    assert result["signed_at"] is None
    assert result["signed_document_url"] is None
    assert result["created_by"] == 42
    # signers 应被序列化为 dict 列表
    assert len(result["signers"]) == 2
    assert result["signers"][0]["name"] == "张三"
    assert result["signers"][0]["role"] == "buyer"
    assert result["signers"][0]["status"] == "pending"  # 默认


# ===========================================================================
# 2. 列表分页
# ===========================================================================


@pytest.mark.asyncio
async def test_list_signature_requests_paginated(service):
    """分页：插入 25 条，page=1/2/3 验证。"""
    svc = service
    for i in range(25):
        await svc.create(
            SignatureRequestCreateReq(
                provider="tencent" if i % 2 == 0 else "esign",
                document_url=f"https://example.com/doc-{i:02d}.pdf",
            )
        )

    p1 = await svc.list(page=1, page_size=10)
    p2 = await svc.list(page=2, page_size=10)
    p3 = await svc.list(page=3, page_size=10)

    assert p1.total == 25
    assert len(p1.items) == 10
    assert p1.page == 1
    assert len(p2.items) == 10
    assert p3.page == 3
    assert len(p3.items) == 5  # 最后一页只有 5 条


# ===========================================================================
# 3. 列表按 provider 筛选
# ===========================================================================


@pytest.mark.asyncio
async def test_list_signature_requests_filter_by_provider(service):
    """按 provider 筛选：插入多种 provider，验证筛选正确。"""
    svc = service
    for _ in range(3):
        await svc.create(SignatureRequestCreateReq(provider="tencent"))
    for _ in range(2):
        await svc.create(SignatureRequestCreateReq(provider="esign"))
    await svc.create(SignatureRequestCreateReq(provider="manual"))

    p_tencent = await svc.list(page=1, page_size=20, provider="tencent")
    assert p_tencent.total == 3
    assert all(r.provider == "tencent" for r in p_tencent.items)

    p_esign = await svc.list(page=1, page_size=20, provider="esign")
    assert p_esign.total == 2
    assert all(r.provider == "esign" for r in p_esign.items)

    p_manual = await svc.list(page=1, page_size=20, provider="manual")
    assert p_manual.total == 1

    # 无 provider 筛选：全部 6 条
    p_all = await svc.list(page=1, page_size=20)
    assert p_all.total == 6


# ===========================================================================
# 4. 详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_signature_request_detail(service_with_contract):
    """获取详情：验证全部字段。"""
    svc = service_with_contract
    created = await svc.create(
        SignatureRequestCreateReq(
            contract_id=200,
            provider="dianxiaoyu",
            external_request_id="DXY-2026-001",
            signers=[SignerItem(name="王五", phone="13900000001", role="buyer")],
            document_url="https://example.com/c200.pdf",
        )
    )
    rid = created["id"]

    detail = await svc.get(rid)
    assert detail is not None
    assert detail["id"] == rid
    assert detail["contract_id"] == 200
    assert detail["provider"] == "dianxiaoyu"
    assert detail["external_request_id"] == "DXY-2026-001"
    assert detail["document_url"] == "https://example.com/c200.pdf"
    assert detail["status"] == "pending"
    assert detail["signed_at"] is None
    assert detail["signers"][0]["name"] == "王五"

    # 不存在
    assert await svc.get(99999) is None


# ===========================================================================
# 5. 更新（仅 pending 状态可改）
# ===========================================================================


@pytest.mark.asyncio
async def test_update_signature_request(service):
    """更新 pending 状态的签署请求：可改 signers / notes / document_url。"""
    svc = service
    created = await svc.create(
        SignatureRequestCreateReq(
            provider="tencent",
            signers=[SignerItem(name="张三", phone="13800000001")],
            notes="初版",
        )
    )
    rid = created["id"]

    upd = SignatureRequestUpdateReq(
        document_url="https://example.com/new.pdf",
        notes="更新到 2026 版本",
        signers=[SignerItem(name="张三", phone="13800000099", role="buyer")],
    )
    result = await svc.update(rid, upd)
    assert result is not None
    assert result["document_url"] == "https://example.com/new.pdf"
    assert result["notes"] == "更新到 2026 版本"
    assert result["signers"][0]["phone"] == "13800000099"


@pytest.mark.asyncio
async def test_update_blocked_when_signing(service):
    """已非 pending 状态不能再 update。"""
    svc = service
    created = await svc.create(
        SignatureRequestCreateReq(provider="esign")
    )
    rid = created["id"]
    # 通过 callback 把状态推进到 signing 之外的状态
    await svc.callback(rid, CallbackReq(status="rejected", notes="拒绝签署"))

    # 此时 status=rejected，update 应抛 ValueError
    with pytest.raises(ValueError, match="不允许修改"):
        await svc.update(rid, SignatureRequestUpdateReq(notes="试图修改"))


# ===========================================================================
# 6. 第三方异步回调
# ===========================================================================


@pytest.mark.asyncio
async def test_callback_update_status(service):
    """第三方回调：pending -> signed，记录 signed_at + signed_document_url。"""
    svc = service
    created = await svc.create(
        SignatureRequestCreateReq(
            provider="tencent",
            external_request_id="TX-2026-001",
        )
    )
    rid = created["id"]
    assert created["status"] == "pending"

    # 回调：signed
    cb = CallbackReq(
        status="signed",
        signed_document_url="https://signed.example.com/c200-signed.pdf",
        external_request_id="TX-2026-001-FINAL",
        notes="已签署",
    )
    result = await svc.callback(rid, cb)
    assert result["status"] == "signed"
    assert result["signed_at"] is not None
    assert result["signed_document_url"] == "https://signed.example.com/c200-signed.pdf"
    assert result["external_request_id"] == "TX-2026-001-FINAL"
    assert "已签署" in result["notes"]

    # 幂等：再回调相同 status 不应抛错
    again = await svc.callback(rid, cb)
    assert again["status"] == "signed"


@pytest.mark.asyncio
async def test_callback_rejected(service):
    """回调 rejected：不设置 signed_at，signed_document_url 可空。"""
    svc = service
    created = await svc.create(SignatureRequestCreateReq(provider="esign"))
    rid = created["id"]

    cb = CallbackReq(status="rejected", notes="对方拒绝签署")
    result = await svc.callback(rid, cb)
    assert result["status"] == "rejected"
    assert result["signed_at"] is None
    assert "对方拒绝签署" in result["notes"]


@pytest.mark.asyncio
async def test_callback_invalid_status(service):
    """非法 status 应抛 ValueError。"""
    svc = service
    created = await svc.create(SignatureRequestCreateReq(provider="tencent"))
    rid = created["id"]

    with pytest.raises(ValueError, match="白名单"):
        await svc.callback(rid, CallbackReq(status="invalid_status"))


# ===========================================================================
# 7. 人工上传签后文件
# ===========================================================================


@pytest.mark.asyncio
async def test_manual_upload(service):
    """人工上传签后文件：status -> signed，signed_at 自动设置。"""
    svc = service
    created = await svc.create(
        SignatureRequestCreateReq(
            provider="manual",
            notes="线下签署",
        )
    )
    rid = created["id"]
    assert created["status"] == "pending"

    upload = ManualUploadReq(
        signed_document_url="https://upload.example.com/signed-c200.pdf",
        notes="已盖合同章",
    )
    result = await svc.manual_upload(rid, upload)
    assert result["status"] == "signed"
    assert result["signed_at"] is not None
    assert result["signed_document_url"] == "https://upload.example.com/signed-c200.pdf"
    assert "线下签署" in result["notes"]
    assert "已盖合同章" in result["notes"]


@pytest.mark.asyncio
async def test_manual_upload_missing_url(service):
    """人工上传必须传 signed_document_url（Pydantic 校验拦截）。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ManualUploadReq()  # type: ignore[call-arg]


# ===========================================================================
# 8. 统计概览
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service):
    """统计：total / 各状态计数 / by_provider。

    构造场景：
    - 3 pending（2 tencent + 1 esign）
    - 1 signing（dianxiaoyu）
    - 2 signed（1 tencent via callback + 1 manual via upload）
    - 1 rejected（esign via callback）
    - 1 expired（tencent via callback）
    """
    svc = service
    # 3 pending
    for _ in range(2):
        await svc.create(SignatureRequestCreateReq(provider="tencent"))
    await svc.create(SignatureRequestCreateReq(provider="esign"))
    # 1 signing：先创建，再用 callback 推进（注意：callback 只能推到 signed/rejected/expired，
    # 不直接支持 pending -> signing 迁移。改用 callback 一次推进到 expired 不影响测试目标。
    # 这里用 rejected 表示非 signing 状态以简化场景）
    #
    # 修正：status=signing 不是 callback 的合法目标。本测试场景中 signing 计数
    # 通过直接 SQL 更新得到（模拟"已发起但未完成"的中间态）。
    s1 = await svc.create(SignatureRequestCreateReq(provider="dianxiaoyu"))
    from sqlalchemy import update as sql_update

    from plugins.ddw_signature_adapter.models import SignatureRequest

    await svc.db.execute(
        sql_update(SignatureRequest).where(SignatureRequest.id == s1["id"]).values(status="signing")
    )
    await svc.db.commit()

    # 2 signed（1 callback + 1 manual）
    s_cb = await svc.create(SignatureRequestCreateReq(provider="tencent"))
    await svc.callback(
        s_cb["id"],
        CallbackReq(
            status="signed",
            signed_document_url="https://signed.example.com/cb.pdf",
        ),
    )
    s_manual = await svc.create(SignatureRequestCreateReq(provider="manual"))
    await svc.manual_upload(
        s_manual["id"],
        ManualUploadReq(signed_document_url="https://upload.example.com/manual.pdf"),
    )
    # 1 rejected
    s_rej = await svc.create(SignatureRequestCreateReq(provider="esign"))
    await svc.callback(s_rej["id"], CallbackReq(status="rejected"))
    # 1 expired
    s_exp = await svc.create(SignatureRequestCreateReq(provider="tencent"))
    await svc.callback(s_exp["id"], CallbackReq(status="expired"))

    stats = await svc.stats()
    assert stats.total == 8
    assert stats.pending == 3
    assert stats.signing == 1
    assert stats.signed == 2
    assert stats.rejected == 1
    assert stats.expired == 1
    # by_provider：tencent=2+1+1=4, esign=1+1=2, dianxiaoyu=1, manual=1
    assert stats.by_provider.get("tencent") == 4
    assert stats.by_provider.get("esign") == 2
    assert stats.by_provider.get("dianxiaoyu") == 1
    assert stats.by_provider.get("manual") == 1
