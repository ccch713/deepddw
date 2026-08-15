# TASK_SPEC · G · 用户管理栏目改版（角色管理 + 用户分类 + 独立部署客户档案 + 授权码 + 收款凭证）

> 来源：用户测试反馈（2026-08-10 深夜，用户管理栏目需求）
> 状态：**待开发**（F 项 8-11 0 点开发；G 项排 8-11 晚 0 点，错开同一工作区）
> 作者：Hermes（架构）· 执行：MiMo Code CLI · 质量：AHE Loop

## 一、需求清单（用户原话拆解）

1. 用户管理栏目 = **角色管理** + **用户管理** 两个子频道
2. 角色管理：角色名称 + 角色权限（**能看到哪些频道的勾选单**）
3. 用户管理：近期登录用户列表
4. 用户角色分类（可筛选）：**demo用户**（标"活跃/超15天未登录"）、**经销商用户**、**SaaS用户**、**独立部署用户**
5. 独立部署用户：点开用户名 → 档案页：
   - 公司信息说明、客户联系人姓名、电话、建立用户日期、首次授权码日期
   - **授权码管理**（历史授权完整记录）
   - 每个历史授权记录点开 → 该次授权期内**新增/删减插件**的记录
6. 权限体系：只有 **superadmin 和子管理员** 能进用户管理；子管理员**只能由 superadmin 建立并勾选授权**（禁止其他途径）
7. 新增独立部署用户：**必须上传收款记录凭证**，否则保存按钮无法点击
8. **授权码更新**（补充）：离线客户（独立部署）档案页有「授权码更新」按钮 → 弹出插件市场已上架的全部插件列表；该用户**已安装插件绿色显示（不可选）**，**未安装插件灰色显示（可多选）**；勾选后底部实时显示**增补差价金额 = 所选新增插件单价之和**
9. **僵尸用户**（补充）：用户列表每行显示"最后一次登录距今 X天X时"；**超过 60 天高亮提醒"僵尸用户"**
10. **批量停用**（补充）：管理员可勾选多用户**批量停用**（禁登录）；users 表记录停用时间
11. **停用用户列表**（补充）：独立 Tab/筛选显示停用用户：停用时间 + 距今多少天，**按停用时长升序排列**

## 二、验收标准

- A. 用户管理页顶部两个子频道 Tab：角色管理 / 用户管理（+ 停用用户 Tab 或筛选）
- B. 角色管理：角色列表（名称+权限勾选单=频道清单），superadmin 可建/改/删自定义角色
- C. 用户管理：分类筛选（全部/demo/经销商/SaaS/独立部署）+ 最近登录排序 + demo 用户显示"活跃/超15天未登录"
- D. 独立部署用户档案：公司/联系人/电话/建户日期/首授权日期 + 授权码历史列表 + 每授权码点开显示插件增删记录
- E. 新建用户弹窗：选用户类型；选"独立部署"时必须有凭证上传（文件），未上传则保存按钮 disabled；凭证类型校验（图片/PDF）
- F. 子管理员：仅 superadmin 可见"新建子管理员"入口；子管理员创建时勾选频道权限；子管理员登录后只见被授权频道
- G. **授权码更新**：弹窗列出全部已上架插件（/admin/plugins 目录），已装=绿色禁用、未装=灰色可多选；勾选后显示增补差价（单价之和）；提交后写入 LicensePluginChange 批量 add 记录
- H. **僵尸用户**：每行"最后登录 X天X时"，>60 天高亮"僵尸用户"徽标
- I. **批量停用**：多选+批量停用按钮 → status=disabled + disabled_at 记录；停用用户登录被拒
- J. **停用用户列表**：显示停用时间+距今天数，按停用时长升序
- K. pytest ≥16 条；全量回归；部署 ECS 浏览器实测

## 三、数据模型

### users 表扩展（core/database/models.py）
```python
# 新增字段（ALTER 兼容：SQLite 加列）
user_type: str = "saas"    # demo / dealer / saas / onpremise
channel_perms: JSON = None # 子管理员频道权限勾选 ["dashboard","plugins","users","llm",...]；None=全部
disabled_at: datetime = None  # 停用时间（批量停用/停用列表用）
last_login_at 已有（用于"超15天未登录"和"僵尸用户"判断）
```

### plugin_meta 补充字段（单价——授权码更新差价计算用）
```python
price_cny: float = 0.0   # 插件单价（元），授权码增补差价=新增插件单价之和
```
- 初始化脚本为已有插件设置默认单价（如 0 或按目录分类预设；可在 DB 手工调整）
- /admin/plugins 返回每项 price_cny

### Role（自定义角色表，新）
```python
class Role(Base):
    __tablename__ = "roles"
    id, name(唯一), description,
    channel_perms: JSON = []   # 可见频道清单（空=全部）
    is_system: bool = False     # 系统内置角色不可删
    created_by, created_at
```

### OnPremiseCustomer（独立部署客户档案，新）
```python
class OnPremiseCustomer(Base):
    __tablename__ = "onpremise_customers"
    id, user_id(唯一, FK users.id), company_name, contact_name, contact_phone,
    notes, payment_proof_path(凭证文件路径), payment_amount(收款金额, 可选),
    first_license_date(首次授权码日期), created_at, updated_at
```

### LicenseKey（授权码，新）
```python
class LicenseKey(Base):
    __tablename__ = "license_keys"
    id, customer_id(FK onpremise_customers), license_code(唯一), issued_at, expires_at,
    status(active/expired/revoked), created_by, notes, created_at
```

### LicensePluginChange（授权期内插件增删记录，新）
```python
class LicensePluginChange(Base):
    __tablename__ = "license_plugin_changes"
    id, license_id(FK license_keys), action(add/remove), plugin_name,
    changed_at, changed_by, reason(备注)
```

## 四、API 端点表

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/v1/admin/roles | 角色列表（含权限勾选） | superadmin/子管理员 |
| POST | /api/v1/admin/roles | 新建角色 {name, description, channel_perms} | superadmin |
| PUT | /api/v1/admin/roles/{id} | 改角色/权限 | superadmin |
| DELETE | /api/v1/admin/roles/{id} | 删角色（is_system 禁删） | superadmin |
| GET | /api/v1/admin/users?user_type=&recent= | 用户列表（分类筛选+最近登录排序，裸数组） | superadmin/子管理员 |
| POST | /api/v1/admin/users | 新建用户 {phone,password,name,user_type,...}；onpremise 必带 payment_proof_path | superadmin/子管理员 |
| GET | /api/v1/admin/users/{id} | 用户详情（档案+最近登录） | superadmin/子管理员 |
| GET | /api/v1/admin/onpremise/{user_id} | 独立部署档案（公司/联系人/授权码历史） | superadmin/子管理员 |
| POST | /api/v1/admin/onpremise/{user_id}/license-keys | 发授权码 {license_code, expires_at} | superadmin/子管理员 |
| POST | /api/v1/admin/license-keys/{kid}/plugins | 记录插件增删 {action, plugin_name, reason}（支持批量 plugin_names） | superadmin/子管理员 |
| POST | /api/v1/admin/license-keys/{kid}/quote | 授权码更新差价计算 {plugin_names:[...]} → {total_cny}（不落库） | superadmin/子管理员 |
| GET | /api/v1/admin/license-keys/{kid} | 授权码详情+插件变更记录列表 | superadmin/子管理员 |
| POST | /api/v1/admin/users/batch-disable | 批量停用 {ids:[...]} → status=disabled + disabled_at=now | superadmin/子管理员 |
| GET | /api/v1/admin/users/disabled | 停用用户列表（含 disabled_at，按停用时长升序，裸数组） | superadmin/子管理员 |
| POST | /api/v1/admin/upload-proof | 凭证文件上传（multipart，图片/PDF ≤5MB）→ 返回路径 | 登录 |
| POST | /api/v1/admin/sub-admins | superadmin 建子管理员 {phone,password,name,channel_perms} | superadmin 专属 |

**权限铁律**：
- /admin/users* 全部端点：仅 superadmin + 子管理员（角色含 channel_perms 含 "users"）
- /admin/roles*、/admin/sub-admins：仅 superadmin
- 子管理员登录后：前端按 channel_perms 渲染侧边栏（未授权频道隐藏+后端 403 双重校验）

**返回规范**：列表裸数组（禁 items 信封）。

## 五、前端设计

### admin.html users 频道改版
```
┌─ [Tab: 角色管理] [Tab: 用户管理] ─────────────────┐
│ 角色管理：                                             │
│  [新建角色]                                           │
│  | 角色名 | 描述 | 频道权限(勾选清单) | 操作 |        │
│  频道勾选：仪表盘/插件管理/用户管理/LLM配置/白名单/    │
│            渠道商/网站流量/文档库/插件市场/论坛        │
│                                                      │
│ 用户管理：                                             │
│  筛选: [全部][demo][经销商][SaaS][独立部署]  [+新建用户]│
│  | 用户 | 手机尾号 | 类型 | 角色 | 最近登录 | 状态 |   │
│  demo 用户状态徽标: 🟢活跃 / ⏰超15天未登录             │
│  独立部署用户行: 点用户名 → 右侧抽屉档案               │
└──────────────────────────────────────────────────────┘
```
- 独立部署档案抽屉：公司信息/联系人/电话/建户日期/首授权日期 + 授权码列表 + 「发放授权码」+ 每个授权码展开显示插件增删记录
- 新建用户弹窗：类型下拉（demo/经销商/SaaS/独立部署）；选独立部署时出现【收款凭证上传】(拖拽/点击，图片或PDF) + 公司信息/联系人字段；**未上传凭证 → 保存按钮 disabled + 提示"请上传收款凭证"**
- 子管理员入口（superadmin 可见）：用户管理页「新建子管理员」→ 手机号+密码+频道权限勾选

### 凭证存储
- 上传目录：`data/payment_proofs/{user_id}/`（ECS 本地，rsync 部署时排除 data）
- 前端预览：/api/v1/admin/proof/{path} 静态读取（superadmin/子管理员权限）

## 六、测试用例（≥12 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | superadmin 建角色（含权限勾选） | 200 + roles 列表可见 |
| 2 | 非 superadmin 建角色 | 403 |
| 3 | 删系统内置角色 | 400（is_system 禁删） |
| 4 | 用户列表分类筛选 user_type=dealer | 只返回经销商用户 |
| 5 | demo 用户状态计算 | 超15天未登录标"超15天未登录" |
| 6 | 新建独立部署用户（带凭证路径） | 200 + onpremise 档案创建 |
| 7 | 新建独立部署用户（无凭证） | 422（payment_proof_path 必填） |
| 8 | 发授权码 | 200 + license_keys 历史 +1 |
| 9 | 授权码记录插件增删 | 200 + LicensePluginChange 记录 |
| 10 | 授权码详情含变更记录 | 字段齐全 |
| 11 | 凭证上传（multipart 假文件） | 200 + 路径返回 |
| 12 | 子管理员建子管理员 | 403（仅 superadmin） |
| 13 | superadmin 建子管理员 | 200 + 登录后只见授权频道 |
| 14 | 子管理员访问未授权端点 | 403 |
| 15 | 批量停用 2 用户 | 200 + status=disabled + disabled_at 非空 |
| 16 | 停用用户登录 | 401/403（禁止登录） |
| 17 | 停用用户列表排序 | 按停用时长升序（最早停用在前） |
| 18 | quote 差价计算 | 2 个插件单价 100+50 → total_cny=150 |
| 19 | 僵尸用户判定 | last_login_at > 60 天 → 标记 zombie=true |
| 20 | 用户列表含 last_active_label | "X天X时" 文案正确 |

## 七、开发顺序

1. models：users 加列 + Role/OnPremiseCustomer/LicenseKey/LicensePluginChange 4 表 → init_db
2. 初始化：系统内置角色（superadmin/admin/子管理员模板）+ 现有用户 user_type 初始化脚本（租户 13/15=demo、14=dealer、1-11=saas、12=superadmin）
3. 后端：roles CRUD → users 扩展 → onpremise 档案/授权码/插件变更 → 凭证上传 → sub-admins → 权限中间件（channel_perms 校验）
4. 前端：admin.html users 频道改版（Tab/筛选/档案抽屉/凭证上传/子管理员）
5. 测试 14 条 → ruff + pytest 全量回归
6. AHE Loop → 部署 ECS → curl 验证 → 浏览器实测

## 八、禁止事项

- 禁新依赖（文件上传用 python-multipart——检查 requirements，无则加，属标准库扩展）
- 禁改登录/滑块/租户隔离既有逻辑（只加 channel_perms 校验，不动 current_admin 签名）
- 禁改 partner 插件、插件加载逻辑
- 凭证文件禁入 git（data/ 已 gitignore）
- 列表端点禁 items 信封
