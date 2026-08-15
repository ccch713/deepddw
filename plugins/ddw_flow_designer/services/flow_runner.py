"""碳硅协作流程执行器（增强版）。

在执行每个 node 前，先检查 input_spec。
执行完成后，检查 output_spec。
"""
from __future__ import annotations

import json
from typing import Any, Dict

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_flow_designer.models import FlowDefinition, FlowRun
from plugins.ddw_flow_designer.services.spec_checker import (
    InputSpecChecker,
    OutputSpecChecker,
)


class FlowRunner:
    """流程执行器。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.input_checker = InputSpecChecker()
        self.output_checker = OutputSpecChecker()

    async def execute_flow(
        self, flow_id: int, tenant_id: int,
        input_data: Dict[str, Any], created_by: int
    ) -> Dict[str, Any]:
        """执行流程。

        1. 加载 FlowDefinition
        2. 解析 dag_json
        3. 逐 node 检查 input_spec → 执行 → 检查 output_spec
        """
        flow = await self.db.get(FlowDefinition, flow_id)
        if not flow or flow.tenant_id != tenant_id:
            return {"error": "流程不存在", "status": "failed"}

        dag = json.loads(flow.dag_json) if isinstance(flow.dag_json, str) else flow.dag_json
        nodes = dag.get("nodes", [])

        # 创建 FlowRun 记录
        run = FlowRun(
            flow_id=flow_id,
            version=flow.version,
            status="running",
            result="{}",
            created_by=created_by,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        # 逐 node 检查 input_spec
        node_results = {}
        for node in nodes:
            node_id = node.get("id", "unknown")
            input_spec = node.get("input_spec")

            if input_spec:
                check_report = self.input_checker.check(input_spec, input_data)
                if not check_report.passed:
                    # 拒绝执行
                    await self._update_run_status(
                        run.id, "input_rejected",
                        json.dumps({
                            "rejected_node": node_id,
                            "check_report": check_report.to_dict(),
                        })
                    )
                    return {
                        "run_id": run.id,
                        "status": "input_rejected",
                        "rejected_node": node_id,
                        "check_report": check_report.to_dict(),
                    }

            # 输入检查通过，执行 node（实际 LLM 调用由插件完成）
            node_results[node_id] = {"status": "pending_execution"}

        # 检查 output_spec（如有）
        output_spec_text = flow.output_spec
        if output_spec_text:
            output_spec = json.loads(output_spec_text) if isinstance(output_spec_text, str) else output_spec_text
            output_report = self.output_checker.check(output_spec, input_data)

            if not output_report.passed:
                approval_gating = output_spec.get("approval_gating", {})
                if approval_gating.get("allow_partial_save", True):
                    await self._update_run_status(
                        run.id, "draft_incomplete",
                        json.dumps({
                            "output_report": output_report.to_dict(),
                            "message": approval_gating.get(
                                "incomplete_save_message",
                                "流程产出不完整，已保存为草稿"
                            ),
                        })
                    )
                    return {
                        "run_id": run.id,
                        "status": "draft_incomplete",
                        "output_report": output_report.to_dict(),
                    }

        # 全部检查通过
        await self._update_run_status(run.id, "success", json.dumps(node_results))
        return {
            "run_id": run.id,
            "status": "success",
            "node_results": node_results,
        }

    async def _update_run_status(self, run_id: int, status: str, result: str) -> None:
        await self.db.execute(
            update(FlowRun).where(FlowRun.id == run_id).values(
                status=status, result=result
            )
        )
        await self.db.commit()
