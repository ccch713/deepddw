# TASK_SPEC: 数字员工体系 P3 — 跨部门联审机制

> **前置条件**：P0+P1+P2 已完成  
> **开发工具**：MiMo Code CLI

---

## P3.1 功能概述

在 P2 的 input/output spec 基础上，新增跨部门长流程的多负责人联审机制。跨部门流程必须经所有涉及部门负责人审核通过后才能 published。

## P3.2 数据模型（已由 P0 迁移，P3 使用）

FlowReview 新增字段已在 P0 添加：checklist_results, skill_merger_approved, review_deadline, remind_count
FlowDefinition 新增字段已在 P0 添加：cross_dept_review_config

## P3.3 新增 API 端点

在 `plugins/ddw_flow_designer/router.py` 中新增：

| 方法 | 路径 | 说明 |
|:-----|:-----|:-----|
| POST | `/api/v1/flows/{id}/submit-review` | 提交跨部门审核 |
| POST | `/api/v1/flows/{id}/reviews/{dept_id}` | 提交部门审核结果（含 checklist） |
| GET | `/api/v1/flows/{id}/review-status` | 查看联审进度 |

## P3.4 核心逻辑

### submit-review
1. 验证 flow.status == "draft"
2. 解析 cross_dept_review_config
3. 按 sequential_order 创建 FlowReview 记录（每个部门一条，第一个 status="pending"，其余 "waiting"）
4. flow.status → "pending_review"
5. 通知第一个部门负责人

### reviews/{dept_id}
1. 验证当前用户是该部门 manager_user_id
2. 接收 checklist_results（逐项 approved/comment）
3. 验证所有 mandatory checklist 项都已 approved
4. 如果 require_all_approve 且有 rejected → 整体 rejected，通知发起人
5. 如果全部 approved → 流转到下一个部门（设下一个 FlowReview 为 pending）
6. 如果是最后一个部门 → flow.status → "published"

### review-status
1. 返回所有部门的审核状态、checklist 完成度、剩余部门数

## P3.5 测试用例（5 条）
1. 提交跨部门审核 → flow 状态变为 pending_review
2. 第一个部门通过 → 流转到第二个部门
3. 任一部门拒绝 → 整体 rejected（require_all_approve=true）
4. 非部门负责人提交审核 → 403
5. review-status 返回完整进度

## P3.6 验收标准
- 跨部门流程 3 部门需依次审核，全部通过才 published
- 审核超时（48h）自动提醒（预留接口）
- 全量测试不回归
- ruff clean

## 禁止事项
- 禁止修改 P0-P2 已完成的文件
- 禁止 push
- 禁止引入新依赖
