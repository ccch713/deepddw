# Changelog

DDW-AI Hub 的版本变更记录。

---

## [Unreleased] - 2026-08-14

### Fixed

- **全量 pytest 归零**（三模型审计阶段 0-1）：
  - pytest.ini 新增（`pythonpath=.` + `--import-mode=importlib` + `norecursedirs` 排除 `_archived/_template`）
  - 修复 228 collection errors：plugins 包路径、同名 test_plugin.py 模块冲突、归档插件污染
  - 依赖补齐：bcrypt/redis/itsdangerous/python-multipart/reportlab/matplotlib（requirements.txt 同步）
  - `plugins/ddw_esg_knowledge` DELETE 路由 204 + `response_model=None`（FastAPI 0.115 对 `-> None` 注解的 204 断言）
  - `plugins/ddw_esg_knowledge` / `ddw_esg_chatbot` 测试改绝对导入（防裸 import 模块劫持）
  - `tests/conftest.py` session engine 幂等化（drop_all + create_all，防 pytest-asyncio 多次实例化）
  - `plugins/ddw_aggregated_pay`（已终止）归档至 `_archived/`
- **版本号统一**（阶段 0-2）：新增仓库根 `VERSION` 单文件，`core/main.py` 三处（FastAPI 元信息 / /health / /api/v1/version）统一读取
- **compose 健康检查修复**（阶段 0-3）：`/api/v1/health` → `/health`
- **online_cs 版本统一**（阶段 0-4）：manifest / plugin / health 端点 / 测试断言统一为 v2.0.0

---

## [Unreleased] - 2026-08-11

### Added

- **插件市场改版 + 内部插件论坛**（F 项）：
  - PluginMarketItem / ForumThread / ForumReply / PluginStar 4 个数据模型
  - 论坛 API（/api/v1/forum）10 个端点：插件列表、论坛首页、打分（upsert）、帖子列表/发帖/详情/回复、管理员置顶、搜索
  - /admin/plugins 扩展：每项联合 title/category/installs/stars/star_count/updated_at/thread_count
  - 插件市场页面（plugin-market.html）：分类筛选、搜索、卡片网格
  - 插件子论坛页面（plugin-forum.html）：说明/版本/反馈 Tab、发帖/回复/打分
  - scripts/init_plugin_meta.py 幂等初始化脚本（75 个插件按关键词归类）
  - 测试用例 14 条（tests/test_forum.py）

---

## [V0.3.3] - 2026-08-10

### 用户管理栏目改版（G 项）

#### 新增

- **角色管理**：Role 模型 + CRUD 端点（/api/v1/admin/roles），支持频道权限勾选（10 个频道），系统内置角色不可删除
- **用户分类**：User 模型扩展 user_type（demo/dealer/saas/onpremise），列表支持分类筛选
- **僵尸用户**：每行显示"最后登录 X天X时"，>60 天高亮"僵尸用户"徽标
- **批量停用**：多选 + 批量停用按钮，status=disabled + disabled_at 记录
- **停用用户列表**：独立 Tab，按停用时长升序排列
- **独立部署档案**：OnPremiseCustomer 模型 + 档案端点（公司/联系人/电话/建户日期/首授权日期）
- **授权码管理**：LicenseKey 模型 + 发放/详情/插件增删记录端点
- **授权码更新差价**：PluginMeta 模型（price_cny）+ quote 端点（不落库，返回 total_cny）
- **凭证上传**：/api/v1/admin/upload-proof（multipart，图片/PDF ≤5MB）
- **子管理员**：superadmin 专属创建 + 频道权限勾选，登录后按 channel_perms 渲染侧边栏
- **登录拦截**：disabled 用户登录返回 403

#### 改动

- `core/database/models.py`：User 加 user_type/channel_perms/disabled_at 列 + 5 新表
- `core/api/admin.py`：+14 个新端点（裸数组铁律）
- `core/api/auth.py`：登录端点增加 status=disabled 检查
- `frontend/admin.html`：users 频道全面改版（三 Tab + 档案抽屉 + 授权码更新弹窗 + 凭证上传 + 子管理员弹窗）
- `scripts/init_user_mgmt.py`：系统内置角色 + user_type 初始化 + plugin_meta 默认单价（幂等）
- `tests/test_admin_users.py`：23 条测试用例

---

## [V0.3.2] - 2026-08-03

### 🎉 重大变更：DDW-AI 培训全量开发完成

由 Mavis（MiniMax Code）按 `TASK_SPEC_DDW_AI训练_全量开发.md` 一次性完成 8 项任务。

#### 新增（57 文件 / ~250KB / 41 测试）

- **任务 A**：`ddw_training` 多媒体补全（v0.1.0 → v0.1.1）
  - `COURSEWARE_TYPES` 从 5 种 → **10 种**
  - 新增 5 种媒体生成器：`viz3d` / `game` / `tts` / `image` / `video`
  - 学科 YAML（physics/chemistry）增加 `multimedia:` 配置块
  - 8 个新单元测试 → **14/14 测试通过**

- **任务 F**：`core/im_adapters/wechat/` 全新模块
  - 4 个新文件（`__init__.py` / `base.py` / `wechat/__init__.py` / `wechat/adapter.py`）
  - 完整 BaseIMAdapter 抽象层
  - 微信服务号适配器（access_token / 文本消息 / 模板消息 / 入站回调）

- **任务 G**：HRIS 适配器层补全
  - 新增 `sap.py` / `oracle.py` / `workday.py`（3 个国际主流 ERP）
  - HRIS 适配器总数：5 → **8**
  - `BUILTIN_ADAPTERS` 注册更新

- **任务 B**：`ddw_report` 插件（13 文件）
  - 4 个 API 端点：用户汇总 / PDF 导出 / 班级概览 / 成绩趋势
  - `StatsEngine`（4 维度能力 / 趋势聚合 / 能力图谱）
  - `PDFExporter`（reportlab + 中文字体 fallback）
  - 订阅 `training.*` 事件失效缓存
  - **8/8 单元测试通过**

- **任务 C**：`ddw_employee_roster` 插件（12 文件）
  - 7 个 API 端点：员工 CRUD / 培训档案 / 部门聚合
  - 2 张表：`ddw_employees` / `ddw_employee_training_records`
  - 订阅 `training.session.completed` → 写培训档案
  - **4/4 单元测试通过**

- **任务 D**：`ddw_kpi` 插件（12 文件）
  - 7 个 API 端点：规则 CRUD / 看板 / 员工明细
  - 2 张表：`ddw_kpi_rules` / `ddw_kpi_records`
  - `KpiEngine`（加权 / 通过阈值 / 部门排行）
  - 订阅 `training.assessment.completed` → 触发 KPI 重算
  - **8/8 单元测试通过**

- **任务 E**：`ddw_saas_billing` 插件（11 文件）
  - 7 个 API 端点：订阅 / 用量 / 配额 / 微信支付回调
  - 2 张表：`ddw_subscriptions` / `ddw_usage_logs`
  - `PaymentService`（微信支付 v3 + 支付宝桩）
  - **7/7 单元测试通过**

#### 增强

- `SocraticEngine` v0.1.1 升级：聚合 4 个 pedagogy schema
  - 6 思维动作（six_moves）
  - 12 教学图景（twelve_vignettes）
  - 4 维度教学审计（socratic_lens）
  - **6 阶段造书流程（craft_your_textbook.yaml）** ← 新增

- `craft_your_textbook.yaml` schema 落地（6 阶段：extract / analyze / blueprint / generate / narrate / deliver）

- 每个新插件 `tests/conftest.py`（插件可独立跑测试）

#### 集成测试（`tests/integration/`）

新增 8 个端到端集成测试，覆盖：
- 5 插件 service 类无副作用实例化
- EventBus 事件流（session.completed → roster + report；assessment.completed → kpi + billing）
- 5 插件 PluginBase 继承一致性
- 5 插件 manifest 合规性
- HRIS 8 适配器完整性
- IM 适配器注册

**全部通过：8/8** ✅

#### 部署 & 工具

- `scripts/install.sh` — macOS Homebrew 一键安装
- `scripts/deploy.sh` — 启动/停止/重启/状态/日志
- `Makefile` — 统一入口（`make install/dev/test/...`）
- `.env.example` — 25+ 环境变量模板
- 4 个 Web UI 单页 HTML（`templates/*.html`）

#### 文档

- `INVENTORY_2026-08-03.md` — 10KB 完整清单
- `README.md` — 项目总览
- `CHANGELOG.md` — 本文件

#### Git

- 2 个 commit：
  - `cee716c` DDW-AI 培训全量开发 V0.3.2 (2026-08-03)
  - `1bf8798` docs: 补充 2 个遗漏的 README

---

## [V0.3.1] - 2026-08-03（早间）

### 变更

- 命名规范化：「DDW 智能培训」→「**DDW-AI 培训**」
- 清理 `_00_Inbox` 老文档（智能辅导 / 智能培训）
- 4 项关键决策自动确认（HRIS 首批 / 孩子反馈 / 商业化 / 开源）
- `SocraticEngine` v0.1.1 升级（聚合 4 schema）
- `craft_your_textbook.yaml` 落地

---

## [V0.3] - 2026-08-01

### 首次发布

- 5 插件组合式架构（1 核心 + 4 配套）
- 6 条架构纠正（vs V0.2 错误）
- 4 客户场景矩阵
- 平台底座能力下沉（HRIS / IM / EventBus v2）
- Socratopia 教学法 4 YAML schema
- 16G Mac mini Homebrew 部署方案

---

*格式基于 [Keep a Changelog](https://keepachangelog.com/)，版本遵循 [Semantic Versioning](https://semver.org/)*

## 2026-08-05 ECS 运维
- docs: ECS安全审计与修复记录（漏洞4包/云备份DNS根因+hosts加固/官网502-docker-bridge-pre-geoip/ddw-core Restart=always 规范化）

## 2026-08-05 AI 客服优化（SSE + 网关统计）
- feat: AI客服SSE流式优化 — 首token ~200ms（4文件 292a8c6）
- feat: LLM网关消耗统计落库 llm_usage_records + GET /api/v1/admin/llm/usage（a51c8fb）
- fix: usage 落库 id 非自增修复（MAX+1）

---

## [V0.4.0] - 2026-08-08

### 🚨 安全修复（紧急，公网实锤）

- **8888万能码账号接管漏洞**：ALWAYS_ACCEPT_CODE 改为环境变量门控（DDW_ENV=production 时禁用），公网 send-code 不再泄露 dev_code
- **密码哈希升级**：SHA256 → bcrypt（SHA256预哈希+rounds=12），verify_password 兼容旧哈希自动降级
- **验证码Redis化**：内存 → Redis 双写+自动降级（DDW_REDIS_URL/DDW_REDIS_PASSWORD），支持多worker扩展
- **Schema修复**：users 表补 password_hash 列（备份 ddw_main.db.bak-20260808）

### 🔧 代码修复

- F821 undefined-name 4处：beisen.py/httpx、bid_writer/json、doc_generator/select、subscription_service/select
- ddw_knowledge_hierarchy 完成 router 接入 services（11端点真实实现，原为占位），73插件加载
- bid_writer 测试端点数 25→26（新增health）

### 🧪 测试

- ddw_clinic_cs/ddw_online_cs 补 17 测试
- ddw_knowledge_hierarchy 补 6 端到端测试
- 重写 test_security_hardening（JWT对齐新API）/ test_ddw_ai_ecosystem（函数式services）
- 清理3个过期测试（test_admin/plugin_market_ui/frontend_backend_integration）→ tests_legacy/
- ECS全量：211/211 通过

### 📦 部署

- systemd 新增环境变量：DDW_ENV=production / DDW_REDIS_URL / DDW_REDIS_PASSWORD
- bcrypt/redis-py 安装至 venv311
- 连字符死代码插件归档 _archived/（customer-service/ddw-smart-cs等）
- Gitea commit: fcdf2bb


---

## [V0.4.1] - 2026-08-08 晚

### 🔐 安全

- **JWT密钥升级**：默认硬编码密钥 → 随机64字符密钥（DDW_JWT_SECRET注入systemd）。旧密钥公开已知=可伪造JWT风险。存量JWT失效（演示环境无存量用户）
- **16G客户服务器模拟部署**：dogfooding验证（无客户现场机会），68插件加载0失败

### 🔧 SDK兼容修复

- knowledge_hierarchy plugin.py：兼容新旧SDK（新版self.router自动prefix / 旧版手动构造，必须include_router拼接prefix）
- token_manager_plugin main.py：state property加setter（SDK v2 __init__赋值兼容）

### 🧪 真实LLM验证

- MiniMax API key环境变量：DDW_MINIMAX_API_KEY
- hierarchical检索（真实MiniMax）：上传设备规程→检索→LLM生成带引用回答（9.5s）✅
- Gitea commit: 4b18136


---

## [V0.4.2] - 2026-08-10 晚

### 🐛 修复：管理后台频道加载失败 + 超管 403（经销商演示链路）

**根因**：上一轮修复中新建/修改的后端列表端点全部返回 `{items:[...]}` 信封格式，而前端 admin.html 6 个频道（用户/白名单/插件/渠道商/LLM providers/LLM rules）全部按裸数组渲染 → 频道显示"加载失败/items 不可达"。同时 `current_admin` 角色白名单不含 `superadmin`，超管（上次 role 从 owner 迁移到 superadmin）调任何管理端点全部 403。

**修复**（commit b601628，已部署）：

| 文件 | 修复 |
|------|------|
| `core/api/llm.py` | `/llm/providers` 返回 gateway 原生 map `{providers:{}}`；`/llm/rules` 返回裸数组 |
| `core/api/users.py` | `/users/`、`/users/whitelist` 返回裸数组 |
| `core/api/admin.py` | `/admin/plugins`、`/admin/billing/channels` 返回裸数组 |
| `core/auth/jwt.py` | `current_admin` 角色白名单 `{owner, admin}` → `{owner, admin, superadmin}` |

**经验铁律**：列表类 API 返回结构必须与前端渲染方式一致（裸数组 vs 信封），改一处必须同步验证另一处；`response_model` 与返回类型不匹配（Dict 声明 + list 返回）会直接 500。

### ✅ 验证

- pytest 86 passed + 1 skipped（无回归）
- ECS 6 端点实测：providers=map（minimax/deepseek ok）、rules=[]、users=真实数据、whitelist/plugins/channels=[]
- ECS 608 条路由在线

---

## [V0.4.3] - 2026-08-10 深夜

### 🐛 修复：插件模型查询 500（with_loader_criteria 传 lambda 崩溃）

**根因**：`core/database/tenant_filter.py` 的 `_do_orm_execute` 中 `with_loader_criteria` 第一个参数错误传了 lambda/function（SQLAlchemy 该参数必须是**单个实体类**）。SQLAlchemy 在 `_all_mappers()` 执行 `root_entity.__subclasses__()` 时对 function/tuple 崩溃 → 所有走全局 tenant 过滤的插件模型查询 500。

**症状**：经销商「客户Demo账号」频道 `GET /api/v1/plugins/ddw-partner-directory/demo-accounts` → 500 Internal Server Error（用户实测触发）。

**修复**（commit b7fd8ed）：从 `Base.registry._class_registry` 动态收集全部 `__tenant_aware__` 实体类，每个类单独注册 `with_loader_criteria()` 后叠加 options。

**验证**：
- ECS demo-accounts 200 + SQL 正确注入 `WHERE tenant_id = ?`（租户过滤仍生效）
- 6 管理端点回归 200 / pytest 86 passed + 1 skipped / ruff 全绿

---

## [V0.4.4] - 2026-08-10 深夜

### ✨ 新功能：经销商一键进入客户 Demo + 付费客户列表（TASK_SPEC_E）

**需求**（用户 08-10）：经销商从自己管理页面免密进入所管理客户的 demo 页面 + 查看已付费客户列表；禁止进入客户正式 SaaS 生产环境。

**实现**（commit bdfbd90，[LLM: mimo-code]，Hermes 验收）：
- `POST /api/v1/plugins/ddw-partner-directory/enter-demo`：经销商 JWT 鉴权 + 归属校验（account.tenant_id == 经销商）+ status=active 校验 → 按 demo_phone 查用户 → 签发 15 分钟 demo_token（scope=demo_enter）
- `POST /api/v1/auth/demo-login`：demo_token 单次兑换正式会话 JWT（tenant=客户 demo 租户，role 沿用 demo 账号）；已用 token 黑名单 → 重复兑换 401
- `GET /api/v1/plugins/ddw-partner-directory/paid-customers`：聚合 partner_demo_accounts + tenants（plan/status/contact_phone），**裸数组**返回
- 前端：partner-demo-accounts.html 每行「进入演示」按钮；auth.js 检测 demo_token 参数自动兑换；新建 partner-paid-customers.html 付费客户列表页

**安全边界**：demo 账号表只录 demo 租户账号（生产租户不在表中）；demo_token 短时+单次；兑换 JWT 只能落在 client_tenant_id 对应租户。

**验证**：pytest 104 passed + 1 skipped（新增 9 测试）；ruff 零新增；ECS 实测 enter-demo→demo-login 全链路（嘉必优租户13/万永刚）+ 重复兑换 401 + paid-customers 裸数组。

---

## [V0.4.5] - 2026-08-10 深夜

### 🐛 修复 + 改进：用户实测 9 条反馈（前 7 条，commit 33840f0）

| # | 反馈 | 修复 |
|---|------|------|
| 1 | 渠道伙伴无佣金账户概念 | 去除佣金余额显示（统计卡+表格列改联系人） |
| 2/8 | 插件管理应显示所有插件+安装状态 | /admin/plugins 改全量清单（扫描 plugins/*/manifest.yaml + app.state.plugins 判定 installed）；侧边栏「插件市场」改「全部插件」频道（marketplace.html 不存在是 404 根源） |
| 3 | 后台不显示当前账号 | welcomeMsg 显示「账号：****尾号4位」 |
| 4 | LLM 配置有 deepseek（不允许用 key） | deepseek key 从 deployment.yaml 清空（mock 模式不再真实调用）；页面显示全部支持模型目录（minimax/deepseek/ollama/qwen/glm/kimi），未配置显示⬜ |
| 5 | 客户Demo/付费客户页无左侧导航 | 两页加左侧导航栏（含退出登录）；admin.html 支持 #hash 频道定位 |
| 6 | 文档库现场演示SOP/部署指南点不开 | 文件缺失（从未部署）→ fde-materials 源文件部署到 ECS frontend/ |
| 7 | SQL Admin 点开是仪表盘 | 根因 /admin 404（sqladmin 从未挂载）→ core/admin setup + 密码认证（DDW_SQLADMIN_PASSWORD）+ views 动态注册 6 个实际模型（原 views 引用不存在的 AuditLog 等死代码） |

### ⚙️ 运维
- ECS systemd 新增 DDW_SQLADMIN_PASSWORD（secrets.token_urlsafe，未入 git）
- ECS venv 安装 itsdangerous（SessionMiddleware 依赖）

---

## [V0.4.6] - 2026-08-10 深夜

### 🐛 修复 + 改进：用户实测反馈 10-13 条（commit b00d0c7）

| # | 反馈 | 修复 |
|---|------|------|
| 10 | demo 首登不强制改密；正式用户弹窗选择 | 后端 `_is_demo_account()` 判定 demo 账号（partner_demo_accounts 表）→ must_change=False；正式用户 login/welcome/saas-register 三处改为弹窗（现在修改/以后再提醒），不再强制跳转改密页 |
| 11 | Demo 弹框显示"嘉必优"（红线）；行业要国标下拉；加截止日期 | placeholder 改"输入客户名称"；行业改 GB/T 4754-2017 20 门类下拉（旧数据动态保留）；测试截止日期默认+30天、最长90天（前端校验+min/max） |
| 12 | 网站流量看板"-"无计数 | 根因：api.js 自动拼 `/api/v1` + 前端写全路径 → 双前缀 404；改短路径。后端实际有数据（PV 1015/UV 35） |
| 13 | 导航栏字号+2、去 icon | admin 侧边栏去 emoji、字号 14→16px；partner 两页同步（13.5→15.5px）；补齐本地缺失 theme.css（从 ECS 拉回） |

### ✅ 验证
- pytest 104 passed + 1 skipped；ruff 全绿
- `_is_demo_account` 实测：万永刚/15990720096=True（豁免）、超管=False（仍提醒）
- 流量 summary：PV 1015 / UV 35 / today 1015

---

## [V0.4.7] - 2026-08-11 00:40

### ✨ P0 全量交付（已部署 ECS + 四库入库）

| # | 内容 | Commit |
|---|------|--------|
| 1 | 拼图滑块验证码（Pillow，多租户死循环修复） | 0190632/a937678 |
| 2 | saas-admin 右上角用户信息 + Demo页侧栏 + LLM 双轨 | 35335a5 |
| 3 | 插件市场 + 内部论坛（forum_threads/plugin_market_items 表已建） | e93ee59 |
| 4 | 从 ECS 补齐 10 个 core 文件 + 5 个前端页面 | 604a18a/56a4d55 |
| 5 | 四条铁律 PRD + 5 份 TASK_SPEC | 1e0f8bc/fa6500b |

### 🛠 Gitea 四库合并（防再造轮子）
- 归档：ddw-ai-hub / ddw-ai-hub-local / ddw-ai-hub-mimo → `-archived-20260811`
- 唯一活跃仓：chenye/ddw-ai-hub-workspace

### ✅ 验证
- pytest 128 passed + 1 skipped；ruff 改动文件全绿
- ECS 公网：login 200 / saas-admin 200 / slider GET 200
- 备份：NAS + EliteXS 外挂盘（428M × 2，sha256 一致）
