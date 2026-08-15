"""跨部门联审服务（P3）。

职责：
- 解析 cross_dept_review_config
- 提交跨部门审核（创建 FlowReview 记录，按 sequential_order 设置状态）
- 处理部门审核结果（checklist 校验、顺序流转、整体驳回）
- 查询联审进度
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import select

from ..models import FlowDefinition, FlowReview

logger = logging.getLogger(__name__)


class CrossDeptReviewService:
    """跨部门联审业务逻辑。"""

    def __init__(self, session):
        self.session = session

    # ------------------------------------------------------------------ #
    # Config
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_review_config(flow: FlowDefinition) -> Dict[str, Any]:
        """解析 cross_dept_review_config，返回配置字典。

        预期结构：
        {
            "departments": [
                {"dept_id": 1, "manager_user_id": 101, "checklist": [
                    {"id": "c1", "label": "...", "mandatory": true}
                ]},
                ...
            ],
            "sequential_order": true,
            "require_all_approve": true,
            "review_deadline_hours": 48
        }
        """
        if not flow.cross_dept_review_config:
            raise ValueError("流程未配置跨部门审核")
        config = (
            json.loads(flow.cross_dept_review_config)
            if isinstance(flow.cross_dept_review_config, str)
            else flow.cross_dept_review_config
        )
        if not config.get("departments"):
            raise ValueError("跨部门审核配置缺少 departments")
        return config

    # ------------------------------------------------------------------ #
    # Submit
    # ------------------------------------------------------------------ #

    async def submit_review(
        self, flow: FlowDefinition, user_id: int
    ) -> List[Dict[str, Any]]:
        """提交跨部门审核，按 sequential_order 创建 FlowReview 记录。

        Returns:
            新创建的审核记录列表
        """
        if flow.status != "draft":
            raise ValueError("仅草稿状态可提交审核")

        config = self.parse_review_config(flow)
        departments = config["departments"]
        sequential = config.get("sequential_order", True)
        deadline_hours = config.get("review_deadline_hours", 48)

        now = datetime.utcnow()
        reviews: List[Dict[str, Any]] = []

        for i, dept_config in enumerate(departments):
            dept_id = dept_config["dept_id"]
            manager_user_id = dept_config.get("manager_user_id")

            status = "pending" if (not sequential or i == 0) else "waiting"
            deadline = now + timedelta(hours=deadline_hours)

            rmax = (
                await self.session.execute(
                    select(FlowReview.id).order_by(FlowReview.id.desc()).limit(1)
                )
            ).scalar() or 0

            review = FlowReview(
                id=rmax + 1 + i,
                flow_id=flow.id,
                department_id=dept_id,
                status=status,
                review_deadline=deadline,
            )
            self.session.add(review)
            reviews.append(
                {
                    "review_id": review.id,
                    "department_id": dept_id,
                    "manager_user_id": manager_user_id,
                    "status": status,
                    "deadline": deadline.isoformat(),
                }
            )

        flow.status = "pending_review"
        flow.updated_at = now
        return reviews

    # ------------------------------------------------------------------ #
    # Dept review
    # ------------------------------------------------------------------ #

    async def submit_dept_review(
        self,
        flow: FlowDefinition,
        dept_id: int,
        user_id: int,
        checklist_results: List[Dict[str, Any]],
        action: str,
        comment: str = "",
    ) -> Dict[str, Any]:
        """提交部门审核结果。

        Args:
            flow: 流程定义
            dept_id: 部门 ID
            user_id: 当前用户 ID
            checklist_results: [{checklist_id, approved, comment?}, ...]
            action: "approve" / "reject"
            comment: 审核意见

        Returns:
            {"status": ..., "next_dept"?: int, "reason"?: str}
        """
        if action not in ("approve", "reject"):
            raise ValueError("action 必须为 approve/reject")

        config = self.parse_review_config(flow)

        # 查找部门配置
        dept_config = None
        for d in config["departments"]:
            if d["dept_id"] == dept_id:
                dept_config = d
                break
        if dept_config is None:
            raise ValueError(f"部门 {dept_id} 不在审核配置中")

        # 验证用户是部门负责人
        manager_user_id = dept_config.get("manager_user_id")
        if manager_user_id is not None and user_id != manager_user_id:
            raise PermissionError("仅部门负责人可提交审核")

        # 查找该部门的审核记录
        review = (
            await self.session.execute(
                select(FlowReview).where(
                    FlowReview.flow_id == flow.id,
                    FlowReview.department_id == dept_id,
                )
            )
        ).scalar_one_or_none()

        if review is None:
            raise ValueError(f"未找到部门 {dept_id} 的审核记录")
        if review.status != "pending":
            raise ValueError(f"该部门审核状态为 {review.status}，无法提交")

        # 校验必填 checklist 项
        dept_checklist = dept_config.get("checklist", [])
        mandatory_ids = {c["id"] for c in dept_checklist if c.get("mandatory")}
        approved_ids = {
            r["checklist_id"] for r in checklist_results if r.get("approved")
        }
        missing = mandatory_ids - approved_ids
        if missing:
            raise ValueError(f"必填检查项未通过: {missing}")

        # 更新审核记录
        review.checklist_results = json.dumps(
            checklist_results, ensure_ascii=False
        )
        review.reviewer_id = user_id
        review.comment = comment
        review.reviewed_at = datetime.utcnow()

        require_all = config.get("require_all_approve", True)

        # 拒绝
        if action == "reject":
            review.status = "rejected"
            if require_all:
                flow.status = "draft"
                flow.updated_at = datetime.utcnow()
                return {"status": "rejected", "reason": "部门拒绝，整体驳回"}

        # 通过
        review.status = "approved"

        sequential = config.get("sequential_order", True)
        if sequential:
            # 找到下一个 waiting 的审核
            next_review = (
                await self.session.execute(
                    select(FlowReview)
                    .where(
                        FlowReview.flow_id == flow.id,
                        FlowReview.status == "waiting",
                    )
                    .order_by(FlowReview.id)
                )
            ).scalars().first()

            if next_review:
                next_review.status = "pending"
                flow.updated_at = datetime.utcnow()
                return {"status": "approved", "next_dept": next_review.department_id}

            # 最后一个部门 → 发布
            flow.status = "published"
            flow.updated_at = datetime.utcnow()
            return {"status": "published"}
        else:
            # 并行审核：检查是否全部完成
            remaining = (
                await self.session.execute(
                    select(FlowReview).where(
                        FlowReview.flow_id == flow.id,
                        FlowReview.status.in_(["pending", "waiting"]),
                    )
                )
            ).scalars().all()

            if not remaining:
                flow.status = "published"
                flow.updated_at = datetime.utcnow()
                return {"status": "published"}
            return {"status": "approved", "remaining": len(remaining)}

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #

    async def get_review_status(self, flow_id: int) -> Dict[str, Any]:
        """获取联审进度。"""
        reviews = (
            await self.session.execute(
                select(FlowReview)
                .where(FlowReview.flow_id == flow_id)
                .order_by(FlowReview.id)
            )
        ).scalars().all()

        dept_statuses = []
        for rv in reviews:
            checklist = (
                json.loads(rv.checklist_results)
                if rv.checklist_results
                else []
            )
            dept_statuses.append(
                {
                    "review_id": rv.id,
                    "department_id": rv.department_id,
                    "status": rv.status,
                    "reviewer_id": rv.reviewer_id,
                    "checklist_count": len(checklist),
                    "checklist_approved": sum(
                        1 for c in checklist if c.get("approved")
                    ),
                    "comment": rv.comment,
                    "deadline": (
                        rv.review_deadline.isoformat()
                        if rv.review_deadline
                        else None
                    ),
                    "remind_count": rv.remind_count,
                    "reviewed_at": (
                        rv.reviewed_at.isoformat() if rv.reviewed_at else None
                    ),
                }
            )

        remaining = sum(
            1 for r in reviews if r.status in ("pending", "waiting")
        )
        total = len(reviews)
        approved = sum(1 for r in reviews if r.status == "approved")
        rejected = sum(1 for r in reviews if r.status == "rejected")

        return {
            "flow_id": flow_id,
            "total_departments": total,
            "approved": approved,
            "rejected": rejected,
            "remaining": remaining,
            "departments": dept_statuses,
        }
