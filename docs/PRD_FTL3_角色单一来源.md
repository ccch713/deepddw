# PRD: 角色白名单单一来源（铁律3落地）

> 编号：PRD-FTL3-ROLES
> 版本：v1.0
> 日期：2026-08-11
> 优先级：P1（Demo 后第一批，防角色守卫 bug 复发）
> 关联铁律：铁律3（角色白名单单一来源 enum）
> 关联规范：DDW-代码命名规范与入库规范-20260811.md

---

## 1. 背景与目标

### 1.1 问题
角色在 5 处独立定义，每次改一处漏改另外四处必踩坑：
1. 数据库 users.role 列（自由文本）
2. 后端 core/api/auth.py current_admin 白名单（硬编码字符串）
3. 前端 frontend/admin.html 守卫（硬编码 admin/superadmin）
4. 前端 frontend/js/auth.js 跳转逻辑（硬编码）
5. 渠道授权体系 tenant_id 校验（独立逻辑）

2026-08-10 实测事故：超管 role 存为 owner → 登录秒跳首页；万永刚（owner）登录也被守卫踢回首页。

### 1.2 目标
- 角色定义收敛为 1 处：`core/constants/roles.py`
- 后端所有角色判断引用 enum
- 前端不判断角色，只消费后端 `/api/v1/auth/me` 返回的 `can_access_admin` / `redirect_target`

---

## 2. 目录结构

```
ddw-ai-hub/
├── core/
│   ├── constants/
│   │   ├── __init__.py
│   │   └── roles.py          # 新增：角色单一权威来源
│   ├── api/
│   │   ├── auth.py           # 修改：current_admin 引用 roles.py
│   │   └── me.py             # 新增：/api/v1/auth/me 端点（或并入 auth.py）
│   └── middleware/
│       └── tenant.py         # 修改：角色判断引用 roles.py
├── frontend/
│   ├── js/
│   │   └── auth.js           # 修改：登录后跳转用后端 redirect_target
│   └── admin.html            # 修改：守卫用 can_access_admin
└── tests/
    └── test_roles_single_source.py   # 新增：5 处一致性测试
```

## 3. Pydantic 模型 / 数据模型

```python
# core/constants/roles.py
from enum import StrEnum

class Role(StrEnum):
    SUPERADMIN = "superadmin"
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    PARTNER = "partner"
    FINANCE = "finance"
    AUDITOR = "auditor"

# 角色集合（用于后端判断）
ADMIN_ROLES = {Role.SUPERADMIN, Role.OWNER, Role.ADMIN}
PLUGIN_MANAGE_ROLES = {Role.SUPERADMIN, Role.OWNER}
FINANCE_ROLES = {Role.SUPERADMIN, Role.OWNER, Role.FINANCE}

# 数据库合法值（CHECK constraint 用）
ROLE_VALUES = [r.value for r in Role]

# /auth/me 返回模型
class MeResponse(BaseModel):
    user_id: int
    phone: str
    name: str
    role: str
    tenant_id: int
    can_access_admin: bool
    redirect_target: str  # "/saas-admin.html" 或 "/index.html"
```

## 4. API 端点

| 方法 | 路径 | 说明 | 返回 |
|------|------|------|------|
| GET | /api/v1/auth/me | 当前登录用户信息 + 权限判断 | MeResponse（裸对象，铁律2） |
| GET | /api/v1/auth/me/roles | 角色枚举列表（调试/前端展示用） | {items:[...], total:N} |

## 5. 核心逻辑

### 5.1 后端 current_admin 改造
```python
# core/api/auth.py
from core.constants.roles import ADMIN_ROLES

async def current_admin(claims: dict = Depends(verify_token)):
    if claims.get("role") not in ADMIN_ROLES:
        raise HTTPException(403, "需要管理员权限")
    return claims
```

### 5.2 /auth/me 逻辑
```python
@router.get("/me")
async def me(claims: dict = Depends(verify_token)):
    role = claims.get("role", "")
    can_access_admin = role in ADMIN_ROLES
    return MeResponse(
        user_id=claims["sub"],
        phone=claims.get("phone", ""),
        name=claims.get("name", ""),
        role=role,
        tenant_id=claims.get("tenant_id", 0),
        can_access_admin=can_access_admin,
        redirect_target="/saas-admin.html" if can_access_admin else "/index.html",
    )
```

### 5.3 前端改造
```js
// frontend/js/auth.js — 登录成功回调
const me = await DDW.api.get('/auth/me');
if (me.ok && me.data.can_access_admin) {
    window.location.href = me.data.redirect_target;
} else {
    window.location.href = '/index.html';
}

// frontend/admin.html 守卫 — 不再硬编码角色
DDW.auth.requireAdmin = async function() {
    const me = await DDW.api.get('/auth/me');
    if (!me.ok || !me.data.can_access_admin) {
        setTimeout(() => window.location.href = '/login.html', 800);
        return false;
    }
    return true;
};
```

### 5.4 DB CHECK constraint（迁移脚本）
```sql
-- 已有表无法直接加 CHECK（SQLite），用应用层校验替代：
-- core/database/models.py 中 User.role 字段加 validator
-- 或建表时加 CheckConstraint
```

## 6. 测试用例（8 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | superadmin 调 /auth/me | can_access_admin=true, redirect=/saas-admin.html |
| 2 | owner 调 /auth/me | can_access_admin=true |
| 3 | admin 调 /auth/me | can_access_admin=true |
| 4 | member 调 /auth/me | can_access_admin=false, redirect=/index.html |
| 5 | partner 调 /auth/me | can_access_admin=false |
| 6 | 5 处角色定义一致性 | roles.py 的 ROLE_VALUES == 数据库中 role 去重值 |
| 7 | current_admin 拒绝 member | 403 |
| 8 | current_admin 拒绝 partner | 403 |

## 7. 验收标准（DeepSeek 新标准 6 维）

| # | 维度 | 标准 |
|---|------|------|
| 1 | pytest | 新增 8 条测试全过，全量回归无破坏 |
| 2 | ruff | 零新增 error |
| 3 | 铁律2 | /auth/me 返回裸对象，/me/roles 返回信封 |
| 4 | 铁律3 | grep 无硬编码 role 判断（core/ 下） |
| 5 | 安全 | 无硬编码 key；401/403 正确 |
| 6 | 冒烟 | 5 角色登录各自跳转正确（L2 角色矩阵） |

## 8. 风险

- 前端大量页面可能硬编码角色判断 → 本次只改 admin.html + auth.js，其余页面后续迭代
- 现有用户 role 值（owner/admin/superadmin/member/partner）需与 enum 对齐 → 检查 DB 实际值

## 9. 依赖

- 无（纯后端+前端改造）
