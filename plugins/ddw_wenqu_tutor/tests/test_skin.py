"""皮肤商店测试（2026-08-14 移植自 wenquK12）。"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from core.database.models import Tenant
from core.database.tenant_filter import tenant_scope

from plugins.ddw_wenqu_tutor.models import WenquBase
from plugins.ddw_wenqu_tutor.router import (
    skin_active,
    skin_activate,
    skin_list,
    skin_seed_presets,
)


@pytest.fixture
async def skin_maker():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(WenquBase.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        db.add(Tenant(id=1, name="家庭一"))
        await db.commit()
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_presets_and_list(skin_maker):
    """初始化 5 个预设皮肤，列表可见。"""
    async with skin_maker() as db:
        with tenant_scope(1):
            seed = await skin_seed_presets(db=db)
            assert seed["created"] == 5

            resp = await skin_list(db=db)
            assert resp["total"] == 5
            names = {t["name"] for t in resp["themes"]}
            assert "朱砂经典" in names
            assert "深夜紫" in names
            # 全部免费
            assert all(t["price_cents"] == 0 for t in resp["themes"])
            # css_vars 是学习台变量体系
            vars0 = resp["themes"][0]["css_vars"]
            assert "--accent" in vars0 and "--sidebar" in vars0


@pytest.mark.asyncio
async def test_seed_idempotent(skin_maker):
    """重复 seed 不重复创建。"""
    async with skin_maker() as db:
        with tenant_scope(1):
            await skin_seed_presets(db=db)
            again = await skin_seed_presets(db=db)
            assert again["created"] == 0


@pytest.mark.asyncio
async def test_activate_and_active(skin_maker):
    """激活皮肤 → active 查询返回。"""
    async with skin_maker() as db:
        with tenant_scope(1):
            await skin_seed_presets(db=db)
            resp = await skin_list(db=db)
            theme_id = resp["themes"][0]["id"]

            act = await skin_activate(
                {"student_name": "CXY", "theme_id": theme_id}, db=db,
            )
            assert act["activated"] is True
            assert act["theme_id"] == theme_id
            assert "--accent" in act["css_vars"]

            active = await skin_active(student_name="CXY", db=db)
            assert active["theme_id"] == theme_id

            # 未激活的学生返回 None
            none_active = await skin_active(student_name="OTHER", db=db)
            assert none_active["theme_id"] is None


@pytest.mark.asyncio
async def test_activate_unknown_theme(skin_maker):
    """激活不存在的皮肤 → 404。"""
    async with skin_maker() as db:
        with tenant_scope(1):
            with pytest.raises(Exception):
                await skin_activate(
                    {"student_name": "CXY", "theme_id": "TH_NOPE"}, db=db,
                )
