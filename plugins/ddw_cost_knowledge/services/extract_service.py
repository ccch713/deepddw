"""LLM 提炼：把造价文件（结构化字段）解析为更细的指标。

注意：实际生产应调用平台 LLM Gateway（minimax provider）。本服务封装：
1. 字段级规则提炼（无 LLM 也能跑，作为 baseline）
2. 预留 llm_extract() 接口（异步、占位实现）
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_cost_knowledge.models import CostDocument

logger = logging.getLogger(__name__)


class ExtractService:
    """从原始字段里提炼结构化指标。"""

    async def extract(
        self,
        session: AsyncSession,
        doc: CostDocument,
        use_llm: bool = False,
    ) -> Dict[str, Any]:
        """触发提炼：返回结构化结果 + 写回 doc.extracted_data + status=processed。"""
        try:
            data = self._rule_based_extract(doc)
            if use_llm:
                llm_part = await self._llm_extract(doc)
                data = {**data, "llm": llm_part}
            doc.extracted_data = data
            doc.status = "processed"
            await session.flush()
            return data
        except Exception as e:  # noqa: BLE001
            doc.status = "failed"
            doc.extracted_data = {"error": str(e)}
            await session.flush()
            logger.exception("extract failed for doc %s", doc.id)
            raise

    def _rule_based_extract(self, doc: CostDocument) -> Dict[str, Any]:
        """规则化提炼：单方造价、面积分类、造价档位。"""
        result: Dict[str, Any] = {
            "doc_type": doc.doc_type,
            "project_name": doc.project_name,
            "project_type": doc.project_type,
        }
        if doc.area and doc.area > 0:
            result["area_sqm"] = doc.area
            if doc.area < 5000:
                result["scale"] = "small"
            elif doc.area < 50000:
                result["scale"] = "medium"
            else:
                result["scale"] = "large"
        if doc.total_cost is not None and doc.area:
            result["unit_price"] = round(doc.total_cost / doc.area, 2)
            result["cost_tier"] = self._cost_tier(result["unit_price"], doc.project_type)
        if doc.unit_price is not None:
            result["unit_price_recorded"] = doc.unit_price
        # 简单从 file_name 推断关键词
        if doc.file_name:
            result["file_keywords"] = re.findall(r"[\u4e00-\u9fa5A-Za-z]+", doc.file_name)[:10]
        return result

    @staticmethod
    def _cost_tier(unit_price: float, project_type: Optional[str]) -> str:
        # 简化档位（元/㎡）
        thresholds = {
            "住宅": (1500, 3500, 6000),
            "商业": (2500, 5000, 9000),
            "工业": (1200, 2500, 4500),
            "市政": (800, 2000, 4000),
        }
        t = thresholds.get(project_type or "住宅", (1500, 3500, 6000))
        if unit_price < t[0]:
            return "low"
        if unit_price < t[1]:
            return "medium"
        if unit_price < t[2]:
            return "high"
        return "premium"

    async def _llm_extract(self, doc: CostDocument) -> Dict[str, Any]:
        """LLM 提炼：调用平台 LLM Gateway。

        占位实现：直接返回空 dict。生产环境替换为：
        ```
        from plugins.embedded_llm.engine import EmbeddedLLM
        llm = EmbeddedLLM(...)
        prompt = f"提炼以下造价文件的结构化指标：..."
        return await llm.extract_json(prompt)
        ```
        """
        logger.info("llm_extract placeholder for doc=%s", doc.id)
        return {"_placeholder": True, "_note": "请接入 platform LLM gateway"}


__all__ = ["ExtractService"]
