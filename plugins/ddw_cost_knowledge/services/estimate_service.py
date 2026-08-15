"""造价估算：基于历史项目 + 工程参数 → 单方造价 + 总价 + 置信度。"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_cost_knowledge.models import CostDocument, CostEstimate

logger = logging.getLogger(__name__)


class EstimateService:
    """基于历史 DB 数据做造价估算。"""

    async def create(
        self,
        session: AsyncSession,
        payload: Dict[str, Any],
    ) -> CostEstimate:
        # 1. 找参考文档
        refs = await self._find_references(session, payload)
        # 2. 计算单方造价
        result = self._compute_estimate(payload, refs)
        # 3. 算置信度
        confidence = self._compute_confidence(refs, payload)

        est = CostEstimate(
            tenant_id=payload.get("tenant_id", 1),
            project_name=payload["project_name"],
            project_type=payload["project_type"],
            area=payload["area"],
            floor_count=payload.get("floor_count"),
            structure_type=payload.get("structure_type"),
            estimate_result=result,
            reference_docs=[r["id"] for r in refs],
            confidence=round(confidence, 3),
            notes=payload.get("notes"),
        )
        session.add(est)
        await session.flush()
        await session.refresh(est)
        return est

    async def get(self, session: AsyncSession, est_id: int) -> Optional[CostEstimate]:
        return (
            await session.execute(select(CostEstimate).where(CostEstimate.id == est_id))
        ).scalar_one_or_none()

    async def list(
        self,
        session: AsyncSession,
        limit: int = 50,
    ) -> List[CostEstimate]:
        return (
            await session.execute(
                select(CostEstimate).order_by(CostEstimate.id.desc()).limit(limit)
            )
        ).scalars().all()

    # ----------------- 内部算法 ----------------- #

    async def _find_references(
        self, session: AsyncSession, payload: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """按 project_type + structure_type 匹配，状态=processed 优先。"""
        q = select(CostDocument).where(CostDocument.status == "processed")
        if payload.get("project_type"):
            q = q.where(CostDocument.project_type == payload["project_type"])
        rows = (await session.execute(q)).scalars().all()
        out: List[Dict[str, Any]] = []
        for r in rows:
            unit_price = r.unit_price or (r.total_cost / r.area if r.area and r.total_cost else None)
            if not unit_price:
                continue
            out.append({
                "id": r.id,
                "file_name": r.file_name,
                "project_name": r.project_name,
                "project_type": r.project_type,
                "area": r.area,
                "total_cost": r.total_cost,
                "unit_price": unit_price,
            })
        return out

    def _compute_estimate(
        self, payload: Dict[str, Any], refs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not refs:
            return {
                "unit_price": 0.0,
                "total_cost": 0.0,
                "method": "fallback",
                "message": "无历史参考数据；请补充后再估算",
            }
        unit_prices = sorted(r["unit_price"] for r in refs if r.get("unit_price"))
        if not unit_prices:
            return {
                "unit_price": 0.0,
                "total_cost": 0.0,
                "method": "fallback",
                "message": "参考数据无单方造价",
            }
        # 加权：中位数 0.4 + 25/75 分位 0.3 + 0.3
        n = len(unit_prices)
        median = unit_prices[n // 2]
        q1 = unit_prices[max(0, n // 4)]
        q3 = unit_prices[min(n - 1, 3 * n // 4)]
        blended = round(median * 0.4 + q1 * 0.3 + q3 * 0.3, 2)
        # 结构类型修正（粗略）
        struct_adj = {"钢结构": 1.08, "框架": 1.0, "框剪": 1.05, "砖混": 0.92}.get(
            payload.get("structure_type", "框架"), 1.0
        )
        unit_price_est = round(blended * struct_adj, 2)
        total_cost = round(unit_price_est * payload["area"], 2)
        return {
            "unit_price": unit_price_est,
            "total_cost": total_cost,
            "method": "weighted_median",
            "breakdown": {
                "median": median,
                "q1": q1,
                "q3": q3,
                "structure_adj": struct_adj,
            },
            "samples": len(unit_prices),
        }

    @staticmethod
    def _compute_confidence(refs: List[Dict[str, Any]], payload: Dict[str, Any]) -> float:
        """置信度：样本数越多越稳；项目类型匹配更稳。"""
        n = len(refs)
        if n == 0:
            return 0.0
        base = 0.4 + 0.1 * min(n, 6)  # 1 个样本 0.5，6 个 1.0
        if n >= 10:
            base = min(1.0, base)
        # 离散度修正：单方造价的相对标准差
        ups = [r["unit_price"] for r in refs if r.get("unit_price")]
        if len(ups) >= 2:
            mean = sum(ups) / len(ups)
            var = sum((u - mean) ** 2 for u in ups) / len(ups)
            std = math.sqrt(var)
            cv = std / mean if mean else 1.0
            base *= max(0.5, 1.0 - cv)  # cv 越大，置信度越低
        return max(0.0, min(1.0, base))


__all__ = ["EstimateService"]
