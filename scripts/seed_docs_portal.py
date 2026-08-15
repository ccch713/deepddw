#!/usr/bin/env python3
"""产品文档栏目 · 首批文档入库脚本（M5 种子数据）。

用法（平台管理员执行）：
    .venv/bin/python scripts/seed_docs_portal.py

行为：
1. 建平台级目录：产品资料 / 白皮书 / 客户案例（tenant_id=0，幂等）
2. 入库 docs/seed/*.md 为 public 文档（slug 已存在则跳过，幂等）
3. 全部 publish（联动 enterprise 记忆写入）
4. 打印入库结果与可见性提示

复用 ddw_docs_portal 业务服务（不重复实现入库逻辑）。
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# 平台根目录入 sys.path（脚本可从任意 cwd 执行）
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select

from core.database.session import init_db, session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_docs_portal.models import (
    CategoryCreateReq,
    DocCreateReq,
    DocItem,
)
from plugins.ddw_docs_portal.services import DocsPortalService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_docs_portal")

SUPERADMIN = {"user_id": 1, "tenant_id": 1, "role": "superadmin"}

# 平台级目录（tenant_id=0，superadmin 创建）
CATEGORIES = [
    {"name": "产品资料", "slug": "products", "parent_id": None, "sort_order": 0},
    {"name": "白皮书", "slug": "whitepapers", "parent_id": None, "sort_order": 1},
    {"name": "客户案例", "slug": "cases", "parent_id": None, "sort_order": 2},
]


async def main() -> None:
    seed_dir = _ROOT / "docs" / "seed"
    if not seed_dir.exists():
        logger.error("种子目录不存在: %s", seed_dir)
        sys.exit(1)

    # 幂等补表（与平台启动 init_db 相同机制；插件新增表在重启前由脚本补齐）
    await init_db()
    # doc_assistant 用独立 registry 建 da_* 表（平台 init_db 不覆盖）
    from plugins.ddw_doc_assistant.models import Base as _da_base

    from core.database.session import get_engine

    async with get_engine().begin() as conn:
        await conn.run_sync(_da_base.metadata.create_all)

    async with session_scope() as db, bypass_tenant_filter():
        svc = DocsPortalService(db)

        # 1) 建目录（幂等：slug 已存在则复用）
        cat_ids: dict = {}
        for c in CATEGORIES:
            try:
                created = await svc.create_category(
                    CategoryCreateReq(**c), SUPERADMIN
                )
                cat_ids[c["slug"]] = created["id"]
                logger.info("目录已创建: %s (id=%s)", c["slug"], created["id"])
            except Exception as exc:  # noqa: BLE001  slug 冲突 → 复用现有
                from plugins.ddw_docs_portal.models import DocCategory

                existing = (
                    await db.execute(
                        select(DocCategory).where(
                            DocCategory.tenant_id == 0,
                            DocCategory.slug == c["slug"],
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    cat_ids[c["slug"]] = existing.id
                    logger.info("目录已存在，复用: %s (id=%s)", c["slug"], existing.id)
                else:
                    logger.warning("目录创建失败: %s (%s)", c["slug"], exc)

        # 2) 入库种子 md（幂等：slug 已存在则跳过）
        imported = 0
        for md in sorted(seed_dir.glob("*.md")):
            slug = md.stem
            exists = (
                await db.execute(
                    select(DocItem).where(DocItem.tenant_id == 0, DocItem.slug == slug)
                )
            ).scalar_one_or_none()
            if exists is not None:
                logger.info("文档已存在，跳过: %s", slug)
                continue

            content = md.read_text(encoding="utf-8")
            # 白皮书默认挂"白皮书"分类；其他文档挂"产品资料"
            category_id = cat_ids.get("whitepapers") or cat_ids.get("products")
            if not slug.startswith("whitepaper"):
                category_id = cat_ids.get("products") or category_id

            doc = await svc.create_doc(
                DocCreateReq(
                    title=md.stem,
                    slug=slug,
                    category_id=category_id,
                    doc_type="whitepaper",
                    visibility="public",
                    content=content,
                    summary="DDW AI Hub 产品定位与能力模型（种子数据，正式版待人工替换）",
                ),
                SUPERADMIN,
            )
            await svc.publish_doc(doc["id"], SUPERADMIN)
            imported += 1
            logger.info("已入库并发布: %s (doc_id=%s)", slug, doc["id"])

        # 3) 可见性自检
        from plugins.ddw_docs_portal.services import DocsPortalService as Svc

        svc2 = Svc(db)
        items = await svc2.list_docs(SUPERADMIN)
        logger.info(
            "入库完成：新增 %s 篇，文档栏目当前可见文档 %s 篇",
            imported,
            items["total"],
        )
        logger.info("验证：经销商/客户登录后可见 public 文档；未登录访问返回 401。")


if __name__ == "__main__":
    asyncio.run(main())
