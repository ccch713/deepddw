"""碳硅协作 P3 测试用例：跨部门联审服务。"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from plugins.ddw_flow_designer.services.cross_dept_review import CrossDeptReviewService


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_flow(flow_id=1, status="draft", config=None):
    """创建 mock FlowDefinition。"""
    flow = MagicMock()
    flow.id = flow_id
    flow.status = status
    flow.cross_dept_review_config = json.dumps(config) if config else None
    flow.updated_at = None
    return flow


def _make_review(review_id=1, flow_id=1, dept_id=1, status="pending"):
    """创建 mock FlowReview。"""
    rv = MagicMock()
    rv.id = review_id
    rv.flow_id = flow_id
    rv.department_id = dept_id
    rv.status = status
    rv.checklist_results = "[]"
    rv.reviewer_id = None
    rv.comment = ""
    rv.reviewed_at = None
    rv.review_deadline = None
    rv.remind_count = 0
    return rv


DEFAULT_CONFIG = {
    "departments": [
        {
            "dept_id": 1,
            "manager_user_id": 101,
            "checklist": [
                {"id": "c1", "label": "数据完整性", "mandatory": True},
                {"id": "c2", "label": "格式规范", "mandatory": False},
            ],
        },
        {
            "dept_id": 2,
            "manager_user_id": 102,
            "checklist": [
                {"id": "c3", "label": "安全审查", "mandatory": True},
            ],
        },
        {
            "dept_id": 3,
            "manager_user_id": 103,
            "checklist": [],
        },
    ],
    "sequential_order": True,
    "require_all_approve": True,
    "review_deadline_hours": 48,
}


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestCrossDeptReviewService:
    """P3: 跨部门联审服务测试。"""

    def setup_method(self):
        self.session = AsyncMock()

    # ---- Test 1: 提交跨部门审核 → flow 状态变为 pending_review ----

    @pytest.mark.asyncio
    async def test_p3_t1_submit_review_creates_reviews(self):
        """提交跨部门审核 → 创建 3 条 FlowReview，flow 状态变为 pending_review。

        第一条 status=pending，其余 status=waiting（sequential_order=true）。
        """
        flow = _make_flow(config=DEFAULT_CONFIG)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        self.session.execute = AsyncMock(return_value=mock_result)

        service = CrossDeptReviewService(self.session)
        reviews = await service.submit_review(flow, user_id=100)

        assert flow.status == "pending_review"
        assert len(reviews) == 3
        assert reviews[0]["status"] == "pending"
        assert reviews[0]["department_id"] == 1
        assert reviews[1]["status"] == "waiting"
        assert reviews[1]["department_id"] == 2
        assert reviews[2]["status"] == "waiting"
        assert reviews[2]["department_id"] == 3

    # ---- Test 2: 第一个部门通过 → 流转到第二个部门 ----

    @pytest.mark.asyncio
    async def test_p3_t2_first_dept_approve_flows_to_next(self):
        """第一个部门通过 → 第二个部门 FlowReview 变为 pending。"""
        flow = _make_flow(status="pending_review", config=DEFAULT_CONFIG)

        review1 = _make_review(review_id=1, dept_id=1, status="pending")
        review2 = _make_review(review_id=2, dept_id=2, status="waiting")

        # 第一次 execute: 查找 dept_id=1 的审核记录
        mock_find = MagicMock()
        mock_find.scalar_one_or_none.return_value = review1
        # 第二次 execute: 查找下一个 waiting 的审核
        mock_next = MagicMock()
        mock_next.scalars.return_value.first.return_value = review2

        self.session.execute = AsyncMock(side_effect=[mock_find, mock_next])

        service = CrossDeptReviewService(self.session)
        result = await service.submit_dept_review(
            flow=flow,
            dept_id=1,
            user_id=101,
            checklist_results=[{"checklist_id": "c1", "approved": True}],
            action="approve",
        )

        assert review1.status == "approved"
        assert review2.status == "pending"
        assert result["status"] == "approved"
        assert result["next_dept"] == 2

    # ---- Test 3: 任一部门拒绝 → 整体 rejected（require_all_approve=true）----

    @pytest.mark.asyncio
    async def test_p3_t3_dept_reject_overall_rejected(self):
        """部门拒绝 + require_all_approve=true → flow 回退到 draft。"""
        flow = _make_flow(status="pending_review", config=DEFAULT_CONFIG)

        review1 = _make_review(review_id=1, dept_id=1, status="pending")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = review1
        self.session.execute = AsyncMock(return_value=mock_result)

        service = CrossDeptReviewService(self.session)
        result = await service.submit_dept_review(
            flow=flow,
            dept_id=1,
            user_id=101,
            checklist_results=[{"checklist_id": "c1", "approved": True}],
            action="reject",
        )

        assert review1.status == "rejected"
        assert flow.status == "draft"
        assert result["status"] == "rejected"
        assert "整体驳回" in result["reason"]

    # ---- Test 4: 非部门负责人提交审核 → PermissionError ----

    @pytest.mark.asyncio
    async def test_p3_t4_non_manager_cannot_review(self):
        """非部门负责人提交审核 → PermissionError。"""
        flow = _make_flow(status="pending_review", config=DEFAULT_CONFIG)

        service = CrossDeptReviewService(self.session)

        with pytest.raises(PermissionError, match="仅部门负责人"):
            await service.submit_dept_review(
                flow=flow,
                dept_id=1,
                user_id=999,  # manager_user_id=101
                checklist_results=[{"checklist_id": "c1", "approved": True}],
                action="approve",
            )

    # ---- Test 5: review-status 返回完整进度 ----

    @pytest.mark.asyncio
    async def test_p3_t5_review_status_returns_progress(self):
        """review-status 返回完整进度信息：部门状态、checklist 完成度、剩余数。"""
        review1 = _make_review(review_id=1, dept_id=1, status="approved")
        review1.checklist_results = json.dumps(
            [{"checklist_id": "c1", "approved": True}]
        )
        review1.reviewer_id = 101

        review2 = _make_review(review_id=2, dept_id=2, status="pending")
        review3 = _make_review(review_id=3, dept_id=3, status="waiting")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            review1, review2, review3,
        ]
        self.session.execute = AsyncMock(return_value=mock_result)

        service = CrossDeptReviewService(self.session)
        status = await service.get_review_status(flow_id=1)

        assert status["total_departments"] == 3
        assert status["approved"] == 1
        assert status["rejected"] == 0
        assert status["remaining"] == 2
        assert len(status["departments"]) == 3
        # 第一个部门的 checklist 完成度
        d1 = status["departments"][0]
        assert d1["checklist_count"] == 1
        assert d1["checklist_approved"] == 1
        assert d1["reviewer_id"] == 101
