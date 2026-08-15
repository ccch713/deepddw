# TASK_SPEC: 财务 ACL（套餐/账单/发票 隔离）

> 优先级：P0
> 预计工时：1 天
> 状态：待确认

---

## 1. 概述

财务模块仅对 owner 和 owner 指定的 1-3 个 finance 角色员工可见。
其他所有角色（包括 dept admin 和普通 member）看不到财务菜单。

## 2. 实现方案

### 2.1 后端 -- 新增 finance 角色

在 User 模型的 role 枚举中新增 finance：
现有角色：superadmin / owner / admin / member / partner
新增：finance / chairman

### 2.2 后端 -- ACL 中间件

def require_finance_role(user: dict) -> bool:
    return user["role"] in ("superadmin", "owner", "finance")

### 2.3 前端 -- 菜单隐藏

if (USER.role !== 'owner' && USER.role !== 'finance' && USER.role !== 'superadmin') {
  document.querySelector('[data-route="billing"]').style.display = 'none';
}

### 2.4 后端 -- 指定财务员工

owner 可在"成员管理"中将某员工角色设为 finance：
PUT /api/v1/admin/users/{id}
body: { role: "finance" }

## 3. API 端点

GET    /api/v1/admin/billing                       # 套餐信息
GET    /api/v1/admin/invoices                      # 发票列表
POST   /api/v1/admin/invoices                      # 申请发票
PUT    /api/v1/admin/users/{id}/role               # 修改角色（owner 可设 finance）

## 4. 验收标准

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | owner 登录 | 财务菜单可见 |
| 2 | finance 角色登录 | 财务菜单可见 |
| 3 | member 登录 | 财务菜单不可见 |
| 4 | dept admin 登录 | 财务菜单不可见 |
| 5 | owner 设 finance | 成员角色变为 finance，刷新后可见财务菜单 |

## 5. 依赖

- 登录+侧栏（TASK_SPEC_LOGIN_SIDEBAR）需先就绪
