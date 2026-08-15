"""DDW 岗位设计器 - 岗位 CRUD 测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from plugins.ddw_position_designer.schemas import (
    DecisionRightBase,
    PositionDesignCreateReq,
    PositionDesignUpdateReq,
)


# ===========================================================================
# Schema 校验
# ===========================================================================


def test_create_position_requires_name():
    """岗位名称必填。"""
    with pytest.raises(ValidationError):
        PositionDesignCreateReq(tenant_id=1)


def test_decision_type_enum_validates():
    """决策类型必须是合法枚举。"""
    with pytest.raises(ValidationError):
        DecisionRightBase(
            scenario="测试", human_right="审批", agent_right="执行",
            decision_type="invalid",
        )


def test_create_position_with_all_fields():
    """构造完整岗位请求。"""
    req = PositionDesignCreateReq(
        tenant_id=1,
        name="大客户销售经理",
        department="销售部",
        report_to="销售总监",
        company="测试公司",
        outcomes=["年度新签≥20家", "续约率≥85%"],
        human_responsibilities=["高层关系维护", "商务谈判"],
        agent_stack=["CRM Agent", "数据分析 Agent"],
        decision_rights=[
            DecisionRightBase(
                scenario="常规报价", human_right="审批",
                agent_right="自动生成", decision_type="auto",
            ),
            DecisionRightBase(
                scenario="合同签署", human_right="最终签署",
                agent_right="草拟", decision_type="human",
            ),
        ],
        human_capability="谈判力、客户关系",
        agent_capability="数据分析、文档生成",
        handoff_protocol="Agent 草拟→人审核→Agent 发布",
        risk_controls=["Agent 报价需人工确认后才能发送"],
    )
    assert req.name == "大客户销售经理"
    assert len(req.decision_rights) == 2
    assert req.decision_rights[0].decision_type == "auto"


# ===========================================================================
# CRUD
# ===========================================================================


@pytest.mark.asyncio
async def test_create_position_success(service):
    """正常创建岗位。"""
    req = PositionDesignCreateReq(
        tenant_id=1,
        name="测试岗位",
        department="销售部",
        outcomes=["签 10 个客户"],
        human_responsibilities=["谈客户"],
        agent_stack=["CRM Agent"],
        decision_rights=[
            DecisionRightBase(
                scenario="报价", human_right="审", agent_right="生成",
                decision_type="suggest",
            ),
        ],
    )
    result = await service.create(req)
    assert result["id"] is not None
    assert result["name"] == "测试岗位"
    assert result["version"] == 1
    assert result["status"] == "draft"
    assert len(result["outcomes"]) == 1
    assert len(result["decision_rights"]) == 1
    assert result["decision_rights"][0]["scenario"] == "报价"


@pytest.mark.asyncio
async def test_update_increments_version(service):
    """更新时 version 自动 +1。"""
    req = PositionDesignCreateReq(tenant_id=1, name="A")
    created = await service.create(req)
    assert created["version"] == 1

    updated = await service.update(
        created["id"],
        PositionDesignUpdateReq(name="A Renamed", outcomes=["新结果"]),
        tenant_id=1,
    )
    assert updated["version"] == 2
    assert updated["name"] == "A Renamed"
    assert updated["outcomes"] == ["新结果"]


@pytest.mark.asyncio
async def test_get_by_id(service):
    """按 ID 查询。"""
    req = PositionDesignCreateReq(tenant_id=1, name="B")
    created = await service.create(req)
    found = await service.get(created["id"], tenant_id=1)
    assert found is not None
    assert found["name"] == "B"


@pytest.mark.asyncio
async def test_get_not_found(service):
    """不存在返回 None。"""
    found = await service.get(9999, tenant_id=1)
    assert found is None


@pytest.mark.asyncio
async def test_list_paginated(service):
    """分页。"""
    for i in range(25):
        await service.create(PositionDesignCreateReq(tenant_id=1, name=f"P{i:02d}"))
    items, total = await service.list(tenant_id=1, page=2, page_size=10)
    assert total == 25
    assert len(items) == 10


@pytest.mark.asyncio
async def test_list_filter_by_department(service):
    """按部门过滤。"""
    await service.create(PositionDesignCreateReq(tenant_id=1, name="销售 1", department="销售部"))
    await service.create(PositionDesignCreateReq(tenant_id=1, name="客服 1", department="客服部"))
    items, total = await service.list(tenant_id=1, department="销售部")
    assert total == 1
    assert items[0]["name"] == "销售 1"


@pytest.mark.asyncio
async def test_list_search_by_name(service):
    """按名称搜索。"""
    await service.create(PositionDesignCreateReq(tenant_id=1, name="大客户经理"))
    await service.create(PositionDesignCreateReq(tenant_id=1, name="小客户代表"))
    items, _ = await service.list(tenant_id=1, search="大客户")
    assert len(items) == 1
    assert "大客户" in items[0]["name"]


@pytest.mark.asyncio
async def test_list_by_department(service):
    """按部门列出（联动 OPC 用）。"""
    for i in range(3):
        await service.create(PositionDesignCreateReq(tenant_id=1, name=f"X{i}", department="客服部"))
    await service.create(PositionDesignCreateReq(tenant_id=1, name="Y", department="销售部"))
    items = await service.list_by_department("客服部", tenant_id=1)
    assert len(items) == 3
    assert all(d["department"] == "客服部" for d in items)


@pytest.mark.asyncio
async def test_list_by_department_excludes_archived(service):
    """list_by_department 排除已归档的。"""
    p1 = await service.create(PositionDesignCreateReq(tenant_id=1, name="A", department="IT 部"))
    p2 = await service.create(PositionDesignCreateReq(tenant_id=1, name="B", department="IT 部"))
    await service.archive(p2["id"], tenant_id=1)
    items = await service.list_by_department("IT 部", tenant_id=1)
    assert len(items) == 1
    assert items[0]["id"] == p1["id"]


@pytest.mark.asyncio
async def test_archive_position(service):
    """归档 = status=archived。"""
    p = await service.create(PositionDesignCreateReq(tenant_id=1, name="Z"))
    archived = await service.archive(p["id"], tenant_id=1)
    assert archived["status"] == "archived"


@pytest.mark.asyncio
async def test_count(service):
    """count 返回总岗位数。"""
    for i in range(5):
        await service.create(PositionDesignCreateReq(tenant_id=1, name=f"N{i}"))
    total = await service.count(tenant_id=1)
    assert total == 5
