"""造价文件导入：单文件上传 + 文件夹批量导入。"""

from __future__ import annotations

import base64
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_cost_knowledge.models import CostDocument

logger = logging.getLogger(__name__)


# 文件名安全化
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-一-龥]")


def _safe_filename(name: str) -> str:
    return _SAFE_NAME.sub("_", name)[:200]


class ImportService:
    """导入服务：负责文件落盘 + DB 记录。"""

    def __init__(self, upload_dir: str = "./data/uploads/cost") -> None:
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- 单文件 ---------------- #

    async def upload(
        self,
        session: AsyncSession,
        payload: Dict[str, Any],
        save_binary: bool = True,
    ) -> CostDocument:
        """上传一个文件：保存到磁盘 + 写入 DB 记录。"""
        file_name = payload["file_name"]
        safe = _safe_filename(file_name)
        file_path: Optional[str] = None

        if save_binary and payload.get("file_content_b64"):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = self.upload_dir / f"{ts}_{safe}"
            try:
                content = base64.b64decode(payload["file_content_b64"])
                target.write_bytes(content)
                file_path = str(target)
            except Exception as e:  # noqa: BLE001
                logger.warning("save binary failed: %s", e)
                file_path = None

        doc = CostDocument(
            tenant_id=payload.get("tenant_id", 1),
            file_name=file_name,
            file_path=file_path,
            doc_type=payload.get("doc_type", "历史造价文件"),
            project_name=payload.get("project_name"),
            project_type=payload.get("project_type"),
            total_cost=payload.get("total_cost"),
            area=payload.get("area"),
            unit_price=payload.get("unit_price"),
            notes=payload.get("notes"),
            status="pending",
        )
        session.add(doc)
        await session.flush()
        await session.refresh(doc)
        return doc

    # ---------------- 批量 ---------------- #

    async def batch_import(
        self,
        session: AsyncSession,
        items: List[Dict[str, Any]],
        tenant_id: int = 1,
        auto_extract: bool = False,
    ) -> Dict[str, Any]:
        success = 0
        failed = 0
        errors: List[Dict[str, Any]] = []
        doc_ids: List[int] = []
        for idx, item in enumerate(items):
            try:
                item = {**item, "tenant_id": tenant_id, "doc_type": item.get("doc_type", "历史造价文件")}
                doc = await self.upload(session, item, save_binary=False)
                doc_ids.append(doc.id)
                success += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                errors.append({"index": idx, "error": str(e), "item": item})
        if success:
            await session.flush()
        return {
            "success": success,
            "failed": failed,
            "document_ids": doc_ids,
            "errors": errors,
        }

    # ---------------- 列表 / 获取 / 删除 ---------------- #

    async def list(
        self,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        doc_type: Optional[str] = None,
        project_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[int, List[CostDocument]]:
        from sqlalchemy import and_, func

        where = []
        if doc_type:
            where.append(CostDocument.doc_type == doc_type)
        if project_type:
            where.append(CostDocument.project_type == project_type)
        if status:
            where.append(CostDocument.status == status)

        count_q = select(func.count(CostDocument.id))
        list_q = select(CostDocument).order_by(CostDocument.id.desc())
        if where:
            count_q = count_q.where(and_(*where))
            list_q = list_q.where(and_(*where))

        total = (await session.execute(count_q)).scalar_one()
        items = (
            await session.execute(list_q.offset((page - 1) * page_size).limit(page_size))
        ).scalars().all()
        return total, list(items)

    async def get(self, session: AsyncSession, doc_id: int) -> Optional[CostDocument]:
        return (
            await session.execute(select(CostDocument).where(CostDocument.id == doc_id))
        ).scalar_one_or_none()

    async def delete(self, session: AsyncSession, doc_id: int) -> bool:
        doc = await self.get(session, doc_id)
        if doc is None:
            return False
        # 文件也删
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
            except Exception:  # noqa: BLE001
                pass
        await session.delete(doc)
        await session.flush()
        return True


__all__ = ["ImportService"]
