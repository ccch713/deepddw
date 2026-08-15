"""DDW AI 组织插件测试用例（8 条）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# 把项目根加入 sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 模块级导入触发模型注册到 Base.metadata
from core.database import models as _core_models  # noqa: E402, F401
from core.database.session import Base  # noqa: E402
from plugins.ddw_org import models as _org_models  # noqa: E402, F401


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def engine():
    """SQLite 内存数据库引擎。"""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    """建表 + 返回 sessionmaker。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def seeded_tenant(session_factory):
    """插入 tenant=1。"""
    from core.database.models import Tenant

    async with session_factory() as s:
        s.add(Tenant(id=1, name="测试租户", plan="pro", status="active"))
        await s.commit()
    return 1


@pytest_asyncio.fixture
async def db(session_factory, seeded_tenant):
    """带种子租户的 session。"""
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def service(db):
    """OrgService 实例。"""
    from plugins.ddw_org.services.org_service import OrgService

    return OrgService(db)


@pytest_asyncio.fixture
async def skill_service(db):
    """AgentSkillService 实例。"""
    from plugins.ddw_org.services.skill_service import AgentSkillService

    return AgentSkillService(db)


# ── 1. seed 创建 11 部门 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_seed_creates_11_departments(db, seeded_tenant):
    """seed 后应有 11 个部门，preset_id 唯一。"""
    from plugins.ddw_org.models import Department
    from plugins.ddw_org.services.seed import seed_org_for_tenant
    from sqlalchemy import select

    result = await seed_org_for_tenant(db, seeded_tenant)
    assert result["departments"] == 11
    assert result["skipped"] is False

    depts = (await db.execute(select(Department).order_by(Department.sort_order))).scalars().all()
    assert len(depts) == 11
    preset_ids = [d.preset_id for d in depts]
    assert len(set(preset_ids)) == 11, "preset_id must be unique"


# ── 2. 笑笑/法海/邮友精确匹配 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_seed_includes_xiaoxiao_fahai_youyou(db, seeded_tenant):
    """断言 dept_01→笑笑、dept_02→法海、dept_03→邮友。"""
    from plugins.ddw_org.models import DigitalAgent
    from plugins.ddw_org.services.seed import seed_org_for_tenant
    from sqlalchemy import select

    await seed_org_for_tenant(db, seeded_tenant)

    agents = (await db.execute(select(DigitalAgent))).scalars().all()
    by_preset = {a.preset_id: a.name for a in agents}

    assert by_preset["dept_01"] == "笑笑"
    assert by_preset["dept_02"] == "法海"
    assert by_preset["dept_03"] == "邮友"


# ── 3. seed 幂等 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_seed_is_idempotent(db, seeded_tenant):
    """调两次 seed，数量仍=11。"""
    from plugins.ddw_org.models import Department
    from plugins.ddw_org.services.seed import seed_org_for_tenant
    from sqlalchemy import select, func

    await seed_org_for_tenant(db, seeded_tenant)
    result2 = await seed_org_for_tenant(db, seeded_tenant)
    assert result2["skipped"] is True

    count = (await db.execute(select(func.count(Department.id)))).scalar_one()
    assert count == 11


# ── 4. 修改部门名 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rename_department_persists(db, seeded_tenant, service):
    """PUT 修改部门名后返回新名。"""
    from plugins.ddw_org.services.seed import seed_org_for_tenant

    await seed_org_for_tenant(db, seeded_tenant)

    depts = await service.list_departments(seeded_tenant)
    first_dept = depts[0]
    dept_id = first_dept["id"]

    updated = await service.update_department(
        dept_id, seeded_tenant, {"name": "新前台部"}
    )
    assert updated is not None
    assert updated["name"] == "新前台部"

    # GET 验证
    detail = await service.get_department(dept_id, seeded_tenant)
    assert detail is not None
    assert detail["name"] == "新前台部"


# ── 5. 修改数字员工名 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rename_digital_agent_persists(db, seeded_tenant, service):
    """PUT 修改数字员工名后返回新名。"""
    from plugins.ddw_org.services.seed import seed_org_for_tenant

    await seed_org_for_tenant(db, seeded_tenant)

    agents = await service.list_agents(seeded_tenant)
    first_agent = agents[0]
    agent_id = first_agent["id"]

    updated = await service.update_agent(
        agent_id, seeded_tenant, {"name": "新名字"}
    )
    assert updated is not None
    assert updated["name"] == "新名字"

    detail = await service.get_agent(agent_id, seeded_tenant)
    assert detail is not None
    assert detail["name"] == "新名字"


# ── 6. 新增员工 + 按部门筛选 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_employee_and_list_by_department(db, seeded_tenant, service):
    """POST 新员工 + GET /employees?department_id=X。"""
    from plugins.ddw_org.services.seed import seed_org_for_tenant

    await seed_org_for_tenant(db, seeded_tenant)
    depts = await service.list_departments(seeded_tenant)
    dept_id = depts[0]["id"]

    emp = await service.create_employee(seeded_tenant, {
        "name": "张三",
        "phone": "13800138000",
        "title": "工程师",
        "department_id": dept_id,
    })
    assert emp["name"] == "张三"
    assert emp["department_id"] == dept_id

    # 按部门筛选
    emps = await service.list_employees(seeded_tenant, department_id=dept_id)
    assert len(emps) == 1
    assert emps[0]["name"] == "张三"


# ── 7. 分配/移除 skill ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assign_and_remove_skill(db, seeded_tenant, service, skill_service):
    """POST /agents/{id}/skills + DELETE 断言增减。"""
    from plugins.ddw_org.models import AgentSkill
    from plugins.ddw_org.services.seed import seed_org_for_tenant
    from sqlalchemy import func, select

    await seed_org_for_tenant(db, seeded_tenant)

    agents = await service.list_agents(seeded_tenant)
    agent_id = agents[0]["id"]

    # 获取一个未分配的 skill
    pool = await skill_service.list_pool()
    # agents[0] 已有默认 skill，找一个不在其中的
    detail = await service.get_agent(agent_id, seeded_tenant)
    assigned_ids = {s["skill_id"] for s in detail["skills"]}
    unassigned = next(sk for sk in pool if sk["id"] not in assigned_ids)

    # 分配
    before_count = (
        await db.execute(
            select(func.count(AgentSkill.id)).where(AgentSkill.agent_id == agent_id)
        )
    ).scalar_one()

    result = await skill_service.assign_skill(agent_id, unassigned["id"])
    assert result["skill_id"] == unassigned["id"]

    after_count = (
        await db.execute(
            select(func.count(AgentSkill.id)).where(AgentSkill.agent_id == agent_id)
        )
    ).scalar_one()
    assert after_count == before_count + 1

    # 移除
    removed = await skill_service.remove_skill(agent_id, unassigned["id"])
    assert removed is True

    final_count = (
        await db.execute(
            select(func.count(AgentSkill.id)).where(AgentSkill.agent_id == agent_id)
        )
    ).scalar_one()
    assert final_count == before_count


# ── 8. skill 池已 seed ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_default_skill_pool_seeded(db, seeded_tenant):
    """seed 后 OrgSkillPool 至少 10 条。"""
    from plugins.ddw_org.models import OrgSkillPool
    from plugins.ddw_org.services.seed import seed_org_for_tenant
    from sqlalchemy import func, select

    await seed_org_for_tenant(db, seeded_tenant)

    count = (await db.execute(select(func.count(OrgSkillPool.id)))).scalar_one()
    assert count >= 10
