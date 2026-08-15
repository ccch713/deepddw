from __future__ import annotations

"""DDW 录音与语音输入插件测试用例（7 个，覆盖上传/关联/列表/筛选/详情/软删除/统计）。"""

import pytest
from pydantic import ValidationError

from plugins.ddw_voice_capture.models import VoiceRecord
from plugins.ddw_voice_capture.schemas import VoiceRecordCreateReq

# ===========================================================================
# 1. 上传录音（最小字段）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_voice_record(service):
    """最小字段上传：file_url/file_size/duration_seconds 必填；默认 status=uploaded。"""
    req = VoiceRecordCreateReq(
        file_url="https://cdn.example.com/voice/2026-08-15/abc123.m4a",
        file_size=1024 * 512,  # 512 KB
        duration_seconds=180,  # 3 分钟
        source_type="local",
        user_id=1,
        notes="拜访后随手记",
        created_by=1,
    )
    result = await service.create(req)

    assert result["id"] is not None
    assert result["tenant_id"] == 1
    assert result["user_id"] == 1
    assert result["file_url"] == "https://cdn.example.com/voice/2026-08-15/abc123.m4a"
    assert result["file_size"] == 1024 * 512
    assert result["duration_seconds"] == 180
    assert result["source_type"] == "local"
    assert result["notes"] == "拜访后随手记"
    assert result["status"] == "uploaded"  # 默认
    assert result["created_by"] == 1
    # 关联字段未传 → 全部 None
    assert result["company_id"] is None
    assert result["contact_id"] is None
    assert result["opportunity_id"] is None
    assert result["created_at"] is not None


# ===========================================================================
# 2. 上传录音（关联企业/联系人/商机）
# ===========================================================================


@pytest.mark.asyncio
async def test_create_voice_record_with_associations(service_with_assoc):
    """关联企业 + 联系人 + 商机：company_id/contact_id/opportunity_id 正确落库。"""
    company_id, contact_id, opportunity_id = 100, 200, 300
    req = VoiceRecordCreateReq(
        file_url="https://cdn.example.com/voice/2026-08-15/call-001.mp3",
        file_size=1024 * 1024 * 2,  # 2 MB
        duration_seconds=600,  # 10 分钟
        source_type="phone",
        user_id=1,
        company_id=company_id,
        contact_id=contact_id,
        opportunity_id=opportunity_id,
        notes="与客户张三电话沟通需求",
        created_by=1,
    )
    result = await service_with_assoc.create(req)

    assert result["company_id"] == company_id
    assert result["contact_id"] == contact_id
    assert result["opportunity_id"] == opportunity_id
    assert result["source_type"] == "phone"
    assert result["duration_seconds"] == 600
    assert result["file_size"] == 1024 * 1024 * 2


# ===========================================================================
# 3. 列表（分页 + 默认排序）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_voice_records(service):
    """分页：插入 5 条，验证 total/page/page_size/items + 默认按 id DESC 排序。"""
    created_ids = []
    for i in range(5):
        result = await service.create(
            VoiceRecordCreateReq(
                file_url=f"https://cdn.example.com/voice/{i}.m4a",
                file_size=1000 * (i + 1),
                duration_seconds=60 * (i + 1),
                source_type="local",
            )
        )
        created_ids.append(result["id"])

    page1 = await service.list(page=1, page_size=3)
    assert page1.total == 5
    assert page1.page == 1
    assert page1.page_size == 3
    assert len(page1.items) == 3
    # id DESC 排序：page1[0] 是最后插入的（id 最大）
    assert page1.items[0].id == created_ids[-1]
    assert page1.items[1].id == created_ids[-2]
    assert page1.items[2].id == created_ids[-3]

    page2 = await service.list(page=2, page_size=3)
    assert len(page2.items) == 2
    # id DESC 排序：page2[0] 是 created_ids[1]
    assert page2.items[0].id == created_ids[1]
    assert page2.items[1].id == created_ids[0]


# ===========================================================================
# 4. 列表（按 source_type 筛选）
# ===========================================================================


@pytest.mark.asyncio
async def test_list_voice_records_filter_by_source(service):
    """source_type 精确筛选：local × 2 + phone × 3 + meeting × 1 → 各自筛选正确。"""
    # local × 2
    for i in range(2):
        await service.create(
            VoiceRecordCreateReq(
                file_url=f"https://cdn.example.com/voice/local-{i}.m4a",
                file_size=1000,
                duration_seconds=60,
                source_type="local",
            )
        )
    # phone × 3
    for i in range(3):
        await service.create(
            VoiceRecordCreateReq(
                file_url=f"https://cdn.example.com/voice/phone-{i}.mp3",
                file_size=2000,
                duration_seconds=120,
                source_type="phone",
            )
        )
    # meeting × 1
    await service.create(
        VoiceRecordCreateReq(
            file_url="https://cdn.example.com/voice/meeting.wav",
            file_size=5000,
            duration_seconds=300,
            source_type="meeting",
        )
    )

    local = await service.list(page=1, page_size=20, source_type="local")
    assert local.total == 2
    assert all(r.source_type == "local" for r in local.items)

    phone = await service.list(page=1, page_size=20, source_type="phone")
    assert phone.total == 3
    assert all(r.source_type == "phone" for r in phone.items)

    meeting = await service.list(page=1, page_size=20, source_type="meeting")
    assert meeting.total == 1
    assert meeting.items[0].source_type == "meeting"

    memo = await service.list(page=1, page_size=20, source_type="memo")
    assert memo.total == 0


# ===========================================================================
# 5. 详情
# ===========================================================================


@pytest.mark.asyncio
async def test_get_voice_record_detail(service):
    """get 返回的详情完整；不存在的 id 返回 None。"""
    created = await service.create(
        VoiceRecordCreateReq(
            file_url="https://cdn.example.com/voice/detail.m4a",
            file_size=4096,
            duration_seconds=240,
            source_type="meeting",
            notes="周会录音",
            user_id=42,
        )
    )
    rid = created["id"]

    detail = await service.get(rid)
    assert detail is not None
    assert detail["id"] == rid
    assert detail["file_url"] == "https://cdn.example.com/voice/detail.m4a"
    assert detail["file_size"] == 4096
    assert detail["duration_seconds"] == 240
    assert detail["source_type"] == "meeting"
    assert detail["notes"] == "周会录音"
    assert detail["user_id"] == 42
    assert detail["status"] == "uploaded"

    # 不存在
    assert await service.get(99999) is None


# ===========================================================================
# 6. 软删除
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_voice_record(service):
    """DELETE 走软删除：status=failed，notes 追加 'deleted by user'，原 notes 保留。"""
    created = await service.create(
        VoiceRecordCreateReq(
            file_url="https://cdn.example.com/voice/to-delete.m4a",
            file_size=2048,
            duration_seconds=120,
            source_type="local",
            notes="原始备注",
        )
    )
    rid = created["id"]
    assert created["status"] == "uploaded"
    assert created["notes"] == "原始备注"

    # 软删除
    result = await service.soft_delete(rid)
    assert result is not None
    assert result["id"] == rid
    assert result["status"] == "failed"  # 软删除态
    # 原 notes 保留 + 追加 marker
    assert "原始备注" in result["notes"]
    assert "deleted by user" in result["notes"]

    # 二次软删除 → None（视为已删除）
    assert await service.soft_delete(rid) is None

    # 不存在的 id → None
    assert await service.soft_delete(99999) is None

    # 列表筛选 status=failed 能找到该条
    failed_list = await service.list(page=1, page_size=20, status="failed")
    assert failed_list.total == 1
    assert failed_list.items[0].id == rid


# ===========================================================================
# 7. 统计
# ===========================================================================


@pytest.mark.asyncio
async def test_stats_overview(service, seeded_db):
    """统计：各状态计数 + total_duration + total_size + by_source_type。

    状态语义：
    - uploaded：本插件创建默认（× 3）
    - transcribed：模拟 P3-3 已转写（× 2）
    - processed：模拟 P3-3 已处理（× 1）
    - failed：模拟 P3-3 转写失败 / 本插件软删除（× 1）
    """
    # uploaded × 3（local=2, phone=1）
    uploaded_ids = []
    for i in range(2):
        r = await service.create(
            VoiceRecordCreateReq(
                file_url=f"https://cdn.example.com/voice/up-local-{i}.m4a",
                file_size=1000,
                duration_seconds=60,
                source_type="local",
            )
        )
        uploaded_ids.append(r["id"])
    r = await service.create(
        VoiceRecordCreateReq(
            file_url="https://cdn.example.com/voice/up-phone-0.mp3",
            file_size=2000,
            duration_seconds=120,
            source_type="phone",
        )
    )
    uploaded_ids.append(r["id"])

    # transcribed × 2
    transcribed_ids = []
    for i in range(2):
        r = await service.create(
            VoiceRecordCreateReq(
                file_url=f"https://cdn.example.com/voice/tr-{i}.m4a",
                file_size=3000,
                duration_seconds=180,
                source_type="local",
            )
        )
        transcribed_ids.append(r["id"])

    # processed × 1
    r = await service.create(
        VoiceRecordCreateReq(
            file_url="https://cdn.example.com/voice/proc-0.wav",
            file_size=4000,
            duration_seconds=240,
            source_type="meeting",
        )
    )
    processed_id = r["id"]

    # failed × 1
    r = await service.create(
        VoiceRecordCreateReq(
            file_url="https://cdn.example.com/voice/fail-0.m4a",
            file_size=5000,
            duration_seconds=300,
            source_type="phone",
        )
    )
    failed_id = r["id"]

    # 直接 ORM 模拟 P3-3 写入状态
    for rid in transcribed_ids:
        rec = await seeded_db.get(VoiceRecord, rid)
        rec.status = "transcribed"
    rec = await seeded_db.get(VoiceRecord, processed_id)
    rec.status = "processed"
    rec = await seeded_db.get(VoiceRecord, failed_id)
    rec.status = "failed"
    await seeded_db.commit()

    stats = await service.stats()
    assert stats.total == 7
    assert stats.uploaded == 3
    assert stats.transcribed == 2
    assert stats.processed == 1
    assert stats.failed == 1
    # total_duration = 60+60+120 + 180+180 + 240 + 300 = 1140
    assert stats.total_duration == 60 + 60 + 120 + 180 + 180 + 240 + 300
    # total_size = 1000+1000+2000 + 3000+3000 + 4000 + 5000 = 19000
    assert stats.total_size == 1000 + 1000 + 2000 + 3000 + 3000 + 4000 + 5000
    # by_source_type: local=4 (2 uploaded + 2 transcribed), phone=2 (1 uploaded + 1 failed), meeting=1
    assert stats.by_source_type.get("local") == 4
    assert stats.by_source_type.get("phone") == 2
    assert stats.by_source_type.get("meeting") == 1


# ===========================================================================
# 8. 必填字段校验（file_url / file_size / duration_seconds）
# ===========================================================================


def test_required_fields_validation():
    """file_url/file_size/duration_seconds 缺失应抛 ValidationError。"""
    # 缺 file_url
    with pytest.raises(ValidationError) as exc:
        VoiceRecordCreateReq(
            file_size=1000,
            duration_seconds=60,
        )
    assert "file_url" in str(exc.value)

    # 缺 file_size
    with pytest.raises(ValidationError) as exc:
        VoiceRecordCreateReq(
            file_url="https://x.m4a",
            duration_seconds=60,
        )
    assert "file_size" in str(exc.value)

    # 缺 duration_seconds
    with pytest.raises(ValidationError) as exc:
        VoiceRecordCreateReq(
            file_url="https://x.m4a",
            file_size=1000,
        )
    assert "duration_seconds" in str(exc.value)

    # file_size 负数应抛
    with pytest.raises(ValidationError):
        VoiceRecordCreateReq(
            file_url="https://x.m4a",
            file_size=-1,
            duration_seconds=60,
        )

    # duration_seconds 负数应抛
    with pytest.raises(ValidationError):
        VoiceRecordCreateReq(
            file_url="https://x.m4a",
            file_size=1000,
            duration_seconds=-10,
        )
