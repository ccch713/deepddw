# TASK_SPEC：角色白名单单一来源（铁律3落地）

> 优先级：P1（Demo 后第一批）
> 执行者：MiMo Code CLI（mimo run headless）
> 验收者：Hermes（DeepSeek 新标准 6 维验收）
> 关联 PRD：docs/PRD_FTL3_角色单一来源.md
> 关联铁律：铁律3

---

## 一、背景与目标

角色在 5 处独立定义，每次改一处漏改另外四处必踩坑：
1. 数据库 users.role 列（自由文本）
2. 后端 core/api/auth.py current_admin 白名单（硬编码字符串）
3. 前端 frontend/admin.html 守卫（硬编码 admin/superadmin）
4. 前端 frontend/js/auth.js 跳转逻辑（硬编码）
5. 渠道授权体系 tenant_id 校验（独立逻辑）

目标：角色定义收敛为 1 处 `core/constants/roles.py`；前端不判角色，消费后端 /auth/me 返回。

## 二、目录结构

```
ddw-ai-hub/
├── core/
│   ├── constants/
│   │   ├── __init__.py
│   │   └── roles.py          # 新增：角色单一权威来源
│   ├── api/
│   │   └── auth.py           # 修改：current_admin 引用 roles.py；新增 /me 端点
│   └── middleware/
│       └── tenant.py         # 修改：角色判断引用 roles.py
├── frontend/
│   ├── js/
│   │   └── auth.js           # 修改：跳转用后端 redirect_target
│   └── admin.html            # 修改：守卫用 can_access_admin
└── tests/
    └── test_roles_single_source.py   # 新增：8 条测试
```

## 三、核心代码

### 3.1 core/constants/roles.py（新增）

```python
"""角色单一权威来源。所有角色判断必须引用本文件，禁止硬编码。"""
from enum import StrEnum

class Role(StrEnum):
    SUPERADMIN = "superadmin"
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    PARTNER = "partner"
    FINANCE = "finance"
    AUDITOR = "auditor"

ADMIN_ROLES = {Role.SUPERADMIN, Role.OWNER, Role.ADMIN}
PLUGIN_MANAGE_ROLES = {Role.SUPERADMIN, Role.OWNER}
FINANCE_ROLES = {Role.SUPERADMIN, Role.OWNER, Role.FINANCE}
ROLE_VALUES = [r.value for r in Role]
```

### 3.2 core/api/auth.py 改造

```python
from core.constants.roles import ADMIN_ROLES

# current_admin 依赖改造（原硬编码 ("admin", "superadmin")）
async def current_admin(claims: dict = Depends(verify_token)):
    if claims.get("role") not in ADMIN_ROLES:
        raise HTTPException(403, "需要管理员权限")
    return claims

# 新增 /me 端点
@router.get("/me")
async def me(claims: dict = Depends(verify_token)):
    role = claims.get("role", "")
    can_admin = role in ADMIN_ROLES
    return {
        "user_id": claims.get("sub"),
        "phone": claims.get("phone", ""),
        "name": claims.get("name", ""),
        "role": role,
        "tenant_id": claims.get("tenant_id", 0),
        "can_access_admin": can_admin,
        "redirect_target": "/saas-admin.html" if can_admin else "/index.html",
    }
```

### 3.3 前端改造

```js
// frontend/js/auth.js 登录回调
const me = await DDW.api.get('/auth/me');
if (me.ok && me.data.can_access_admin) {
    window.location.href = me.data.redirect_target;
} else {
    window.location.href = '/index.html';
}

// frontend/admin.html 守卫
DDW.auth.requireAdmin = async function () {
    const me = await DDW.api.get('/auth/me');
    if (!me.ok || !me.data.can_access_admin) {
        setTimeout(() => (window.location.href = '/login.html'), 800);
        return false;
    }
    return true;
};
```

## 四、测试用例（8 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | superadmin 调 /auth/me | can_access_admin=true, redirect=/saas-admin.html |
| 2 | owner 调 /auth/me | can_access_admin=true |
| 3 | admin 调 /auth/me | can_access_admin=true |
| 4 | member 调 /auth/me | can_access_admin=false, redirect=/index.html |
| 5 | partner 调 /auth/me | can_access_admin=false |
| 6 | ROLE_VALUES 与数据库 role 去重值一致 | 集合相等 |
| 7 | current_admin 拒绝 member | 403 |
| 8 | current_admin 拒绝 partner | 403 |

## 五、验收标准（DeepSeek 新标准）

| # | 维度 | 标准 |
|---|------|------|
| A | pytest | 新增 8 条全过，全量回归 123+ 无破坏 |
| B | ruff | 零新增 error |
| C | 铁律2 | /auth/me 返回裸对象 |
| D | 铁律3 | grep core/ 无硬编码 role 判断 |
| E | 安全 | 401/403 正确 |
| F | 冒烟 | 5 角色登录各自跳转正确 |

## 六、红线

1. 只改 auth.py 的 current_admin + 新增 /me；不动 login-password 主逻辑
2. 不硬编码任何角色字符串在 core/ 其他文件
3. 前端只消费 /auth/me，不自己判断 role
4. commit：`feat(auth): 角色白名单单一来源enum+me端点 [LLM: mimo-code]`，不 push
5. 不要动 ECS 上的文件（本地开发，Hermes 负责部署）
