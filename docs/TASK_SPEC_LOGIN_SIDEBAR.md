# TASK_SPEC: 登录修复 + 侧栏 v3 重构

> 优先级：P0（今晚立即做）  
> 预计工时：2 小时  
> 状态：待确认

---

## 1. 问题背景

18571998165（万永刚，嘉必优 owner）登录后被踢回首页。  
根因：`login.html` 没有写 `localStorage.ddw_user`，saas-admin 读到 null → USER.name='?'。  
另外 saas-admin 侧栏只有 6 项，缺少大量新频道。

## 2. 修改清单

### 2.1 login.html — 登录成功后写 localStorage

```javascript
// 登录成功后（access_token 已获取），写入 ddw_user 和 ddw_tenant
DDW.api.setToken(resp.data.access_token);

// 新增：写入用户信息
const meResp = await DDW.api.get('/auth/me');
if (meResp.ok && meResp.data) {
  const u = meResp.data.user || meResp.data;
  const t = meResp.data.tenant || {};
  localStorage.setItem('ddw_user', JSON.stringify({
    id: u.id,
    name: u.name || u.phone,
    phone: u.phone,
    role: u.role,
    tenant_id: u.tenant_id
  }));
  localStorage.setItem('ddw_tenant', JSON.stringify({
    id: t.id,
    name: t.name,
    plan: t.plan || 'free'
  }));
}
```

### 2.2 login.html — 按角色智能跳转（已完成，保留）

| 角色 | 跳转 |
|------|------|
| admin / superadmin | /admin.html |
| partner | /partner-demo-accounts.html |
| owner / user / finance / chairman | /saas-admin.html#pal（DDW Pal） |

### 2.3 saas-admin.html — 侧栏 v3 重构

```
saas-admin 侧栏 v3
├─ 🤖 DDW Pal（data-route="pal"）← 默认首页
├─ 🏢 AI 组织（data-route="org"）
│   ├─ 部门管理（data-route="org-departments"）
│   ├─ 数字员工（data-route="org-agents"）
│   └─ 员工管理（data-route="org-employees"）
├─ 📚 知识库（data-route="kb"）
├─ 🪙 Token 广场（data-route="token"）
│   ├─ LLM 配置（data-route="token-llm"）
│   ├─ 消耗统计（data-route="token-usage"）
│   └─ API Key（data-route="token-apikeys"）
├─ 🔌 插件市场（data-route="plugins"）
├─ 💬 论坛（data-route="forum"）
├─ 🌊 碳硅协作空间（data-route="carbon"）
├─ 👥 成员管理（data-route="users"）← 仅 admin/owner
├─ 💰 财务（data-route="billing"）← ACL: owner + finance
│   ├─ 套餐与账单
│   └─ 发票管理
└─ ⚙️ 设置（data-route="settings"）
```

### 2.4 saas-admin.html — 右上角 USER 显示

```javascript
// 当前（错误）：
$('#userChip').innerHTML = '...<span>' + (USER.name || USER.phone || '?') + '</span>...';

// 修改为：
const displayPhone = USER.phone ? '···' + USER.phone.slice(-6) : '';
$('#userChip').innerHTML = '<span class="user-avatar">' + (USER.name || '?').charAt(0) + '</span>' +
  '<span>' + (USER.name || '?') + '</span>' +
  '<span style="color:var(--text-muted);font-size:12px;margin-left:4px">' + displayPhone + '</span>' +
  '<a href="javascript:void(0)" id="btnLogout">退出</a>';
```

### 2.5 财务 ACL

```javascript
// 财务菜单仅对 owner + finance 角色可见
if (USER.role !== 'owner' && USER.role !== 'finance') {
  document.querySelector('[data-route="billing"]').style.display = 'none';
}
// 注：finance 角色需要后端在 /auth/me 中返回
```

## 3. 验收标准

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | 用 18571998165 登录 | 右上角显示"万永刚 ···998165" |
| 2 | 登录后跳转 | 进入 saas-admin.html#pal（DDW Pal 页面） |
| 3 | 侧栏 | 显示 9 个一级菜单 + AI 组织和 Token 广场有子菜单 |
| 4 | 财务菜单 | owner 可见，member 不可见 |
| 5 | Gitea 推送 | commit + push 到 main |

## 4. 依赖

- 无外部依赖，纯前端修改
- 后端 /auth/me 已存在，返回 user + tenant 对象
