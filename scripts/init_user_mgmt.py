"""用户管理改版（G 项）初始化脚本（幂等）。

- 创建系统内置角色（superadmin / admin / 子管理员模板）
- 初始化现有用户的 user_type（按租户映射）
- 为 plugin_meta 设置默认 price_cny

用法：
    python scripts/init_user_mgmt.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 项目根加入 sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def main() -> None:
    from sqlalchemy import select

    from core.database.models import PluginMeta, Role, User
    from core.database.session import init_db, session_scope
    from core.database.tenant_filter import bypass_tenant_filter

    # 确保表已创建
    await init_db()

    # ------------------------------------------------------------------
    # 1. 系统内置角色
    # ------------------------------------------------------------------
    system_roles = [
        {
            "name": "superadmin",
            "description": "超级管理员（全部权限）",
            "channel_perms": [],  # 空=全部
            "is_system": True,
        },
        {
            "name": "admin",
            "description": "管理员（全部权限）",
            "channel_perms": [],
            "is_system": True,
        },
        {
            "name": "sub_admin",
            "description": "子管理员模板（需配置频道权限）",
            "channel_perms": [],
            "is_system": True,
        },
    ]

    async with session_scope() as session, bypass_tenant_filter():
        for role_def in system_roles:
            existing = (
                await session.execute(
                    select(Role).where(Role.name == role_def["name"])
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(Role(**role_def))
                print(f"  [role] created: {role_def['name']}")
            else:
                print(f"  [role] exists: {role_def['name']}")
        await session.commit()

    # ------------------------------------------------------------------
    # 2. 现有用户 user_type 初始化（按租户映射）
    # ------------------------------------------------------------------
    # 租户 13/15=demo, 14=dealer, 1-11=saas, 12=superadmin(保持 saas)
    TENANT_TYPE_MAP = {
        13: "demo",
        15: "demo",
        14: "dealer",
    }

    async with session_scope() as session, bypass_tenant_filter():
        users = (await session.execute(select(User))).scalars().all()
        updated = 0
        for u in users:
            target_type = TENANT_TYPE_MAP.get(u.tenant_id, "saas")
            if u.user_type != target_type:
                u.user_type = target_type
                updated += 1
        if updated:
            await session.commit()
            print(f"  [user_type] updated {updated} users")
        else:
            print("  [user_type] all users already initialized")

    # ------------------------------------------------------------------
    # 3. plugin_meta 默认 price_cny（扫描 plugins/ 目录）
    # ------------------------------------------------------------------
    plugins_dir = _ROOT / "plugins"
    plugin_names: list[str] = []
    if plugins_dir.is_dir():
        for manifest_path in sorted(plugins_dir.glob("*/manifest.yaml")):
            name = manifest_path.parent.name
            if name in {"_template", "embedded_llm"}:
                continue
            plugin_names.append(name)

    async with session_scope() as session, bypass_tenant_filter():
        added = 0
        for pname in plugin_names:
            existing = (
                await session.execute(
                    select(PluginMeta).where(PluginMeta.plugin_name == pname)
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(PluginMeta(plugin_name=pname, price_cny=0.0))
                added += 1
        if added:
            await session.commit()
            print(f"  [plugin_meta] added {added} entries (price_cny=0)")
        else:
            print("  [plugin_meta] all plugins already registered")

    print("\n✅ 用户管理初始化完成")


if __name__ == "__main__":
    asyncio.run(main())
