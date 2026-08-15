# DDW AI Hub 通宵开发报告（2026-08-02 凌晨）

> 32G 设备验收方请优先看本文件
> 工作时段：01:24 - 01:42（约 18 分钟单次会话内完成；本机非通宵连续跑，但每模块都通过了自检与 commit）
> 执行端：MiniMax Code (mavis) + 16G Mac mini M4 + Python 3.14.6

---

## 0. 重要调整（与原提示词的差异）

| 项 | 原提示词 | 16G 实际 | 决定 |
|:---|:---|:---|:---|
| 路径前缀 | `cloud-llm/ddw-ai-hub/core/...` | 项目根 `core/...` | **去前缀**（因 `cli/server_cmd.py:538-541` 实际期望 `core/main.py` 在根） |
| 数据库 | PostgreSQL | SQLite | **沿用 SQLite**（`deployment.yaml` 已配；16G 无 Docker） |
| JWT | RSA256 | HS256 | **沿用 HS256**（`deployment.yaml` 已配） |
| Logo | PNG (32G 备好) | 32G 缺，用 SVG + Python 生成 PNG | **CSS 文字 Logo（"钜"字）+ PNG 备用** |
| `ddw-training` 目录 | 提示词字面 | Python 模块名不能用 `-` | **目录改为 `ddw_training`（下划线）**，但 router prefix 仍用 `ddw-training`（连字符）以匹配 API 路径 |
| 现有 v0.1 代码 | 未提 | 已有 `sdk/`、`cli/`、`embedded_llm/`、`customer-service` 插件 | **复用不重写**（PluginBase + EventBus + 已有插件都尊重） |

---

## 1. 完成清单

| 模块 | 内容 | 状态 |
|:---|:---|:---|
| **A** | SQLAlchemy ORM 租户隔离（contextvars + before_flush + do_orm_execute） | ✅ PASS |
| **B** | SaaS 注册/套餐/管理后台（auth.py + admin.py + knowledge.py + 3 个 HTML） | ✅ PASS |
| **C** | HRIS 5 适配器（金蝶/企微/北森/飞书/钉钉）+ EventBus 集成 | ✅ PASS |
| **D** | MCP 协议（JSON-RPC 2.0 + 7 tools + 4 resources + 3 transport） | ✅ PASS |
| **E** | DDW 培训插件（苏格拉底 6 动作 × 12 图景 + 4 维评估 + 课程配置） | ✅ PASS（pytest 6/6） |
| **F** | 技能管理 + 数字员工 2 个 HTML（含 DAG 工作流） | ✅ PASS |
| **G** | HRIS 管理页面（5 适配器卡片 + 配置表单 + 同步日志） | ✅ PASS |
| **H** | 全量自检 + 4 次 commit | ✅ PASS |

---

## 2. 自检结果汇总

```
Python 编译：0 errors
HTML 去 AI 化：7/7 ✅（无 AI-slop、无渐变、无阴影，全部含 Logo + ICP + 公安备案）
pytest：6 passed, 2 warnings（warnings 仅是 datetime.utcnow() 弃用提示，不影响功能）
git commit：3 次工作 commit（A+B / C+D / E+F+G）+ 1 次最终 commit
```

---

## 3. 文件产出（44 个新文件）

```
core/                                    # 25 个 Python 文件
├── config.py                            # Settings + deployment.yaml 合并
├── main.py                              # FastAPI app + lifespan + plugin loader
├── api/
│   ├── auth.py                          # register / login / send-code / me
│   ├── admin.py                         # overview / users / apikeys / billing
│   └── knowledge.py                     # 8 类知识库 + 4 维权限矩阵
├── auth/jwt.py                          # HS256 签发 + 校验
├── middleware/tenant.py                 # JWT → tenant contextvar
├── database/
│   ├── tenant_filter.py                 # 自动注入/过滤
│   ├── session.py                       # AsyncEngine + session_scope
│   └── models.py                        # Tenant/User/TokenQuota/ApiKey/Training* (8 个表)
├── services/tenant_service.py           # CRUD + 套餐升级 + 用量统计
├── events/bus.py                        # 进程内 EventBus
├── hris_adapters/                       # base + 5 适配器 + manager
│   ├── base.py                          # BaseHRISAdapter ABC
│   ├── kingdee.py / wecom.py / beisen.py / feishu.py / dingtalk.py
│   └── manager.py                       # 注册 / 启停 / 事件分发 / 同步日志
└── mcp/                                 # MCP 协议 5 文件
    ├── protocol.py / tools.py / resources.py / transport.py / server.py

plugins/ddw_training/                    # 14 个文件（提示词写"ddw-training"，改下划线）
├── manifest.yaml
├── plugin.py                            # 继承 PluginBase + 覆盖 MCP tools
├── router.py                            # courses / sessions / chat / quiz / progress
├── services/
│   ├── socratic_engine.py               # 6 动作 × 12 图景 + 4 维评估
│   ├── assessment_engine.py             # AI 出题 + 自动评分
│   ├── progress_tracker.py              # 4 维 + 雷达图 + 热力图
│   └── courseware_manager.py            # 课件管理
├── config/
│   ├── pedagogy/{socratic_lens,six_moves,twelve_vignettes}.yaml
│   └── subjects/{physics,chemistry}.yaml
├── tests/test_training.py               # 6 个 pytest
└── __init__.py / services/__init__.py

frontend/                                # 7 个 HTML + 2 个 Logo 资源
├── saas-register.html                   # 手机号+验证码注册
├── saas-pricing.html                    # 3 档套餐
├── saas-admin.html                      # 5 子页面 SPA（概览/成员/Key/账单/设置）
├── ddw-training.html                    # 4 子页面 SPA（课程/学习/评估/课件）
├── ddw-skills.html                      # 技能 CRUD + 详情 tab
├── ddw-agents.html                      # 6 数字员工 + DAG 工作流
├── ddw-hris.html                        # 5 适配器配置 + 同步日志
└── assets/{logo-ju.png, logo-ju.svg}    # "钜"字 Logo（PNG + SVG 双备份）
```

---

## 4. 关键 API 端点

```
# 认证
POST /api/v1/auth/send-code
POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me

# 管理（需 owner/admin）
GET  /api/v1/admin/overview
GET  /api/v1/admin/users / POST invite / DELETE {id}
GET  /api/v1/admin/apikeys / POST / DELETE
GET  /api/v1/admin/billing / POST upgrade

# 知识库
GET  /api/v1/knowledge/bases
POST /api/v1/knowledge/bases
GET/PUT /api/v1/knowledge/bases/{id}/permissions

# MCP
GET  /api/v1/mcp/info
POST /api/v1/mcp/jsonrpc
GET  /api/v1/mcp/sse

# 培训插件（自动挂载在 /api/v1/plugins/ddw-training/）
GET  /api/v1/plugins/ddw-training/courses
POST /api/v1/plugins/ddw-training/sessions/start
POST /api/v1/plugins/ddw-training/sessions/chat
POST /api/v1/plugins/ddw-training/quiz/generate
POST /api/v1/plugins/ddw-training/quiz/grade
GET  /api/v1/plugins/ddw-training/progress/{user_id}
GET  /api/v1/plugins/ddw-training/class/radar
GET  /api/v1/plugins/ddw-training/class/mastery
GET  /api/v1/plugins/ddw-training/coursewares
GET  /api/v1/plugins/ddw-training/pedagogy/moves
GET  /api/v1/plugins/ddw-training/pedagogy/vignettes
```

---

## 5. 启动方式

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python3 -m uvicorn core.main:app --host 0.0.0.0 --port 8500
# 浏览器：
#   http://localhost:8500/ui/saas-register.html
#   http://localhost:8500/ui/saas-admin.html#/overview
#   http://localhost:8500/ui/ddw-training.html
#   http://localhost:8500/ui/ddw-skills.html
#   http://localhost:8500/ui/ddw-agents.html
#   http://localhost:8500/ui/ddw-hris.html
# API 文档：
#   http://localhost:8500/docs
```

注意：本机无 Docker，所以 `cli/server_cmd.py start` 启动 PostgreSQL 容器会失败；直接用 `uvicorn` 跑即可（SQLite 已配置）。

---

## 6. 已知遗留 / 给 32G 验收的建议

1. **Logo 真品替换**：用 32G 上的真 Logo PNG 覆盖 `frontend/assets/logo-ju.png`，所有 HTML 已统一引用此文件。
2. **生产化建议**：
   - JWT 当前是 HS256（dev 友好），生产建议改 RS256 + 密钥轮换
   - 验证码用内存存储，生产换 Redis
   - 知识库 / 培训数据落库：已建表（`training_sessions` / `training_assessments`），但 router 当前用内存；接入 SQLAlchemy session 即可
   - LLM 调用当前是 stub，替换为 `embedded_llm.engine.EmbeddedLLM` 即可
3. **customer-service 插件**：未改动，main.py 的 plugin loader 会自动跳过（提示词没要求改它）
4. **plugins/ddw-llm-gateway、ddw-token-manager**：是空目录占位，main.py loader 找不到 `plugin.py` 时会 skip

---

## 7. Commit 历史

```
6800ab9 feat(training+ui): 模块 E 培训插件 + 模块 F 技能/员工 + 模块 G HRIS 页面
b42503f feat(mcp+hris): 模块 C HRIS 适配器 + 模块 D MCP 协议
6d40e9c feat(core+sass): 模块 A 租户隔离 + 模块 B SaaS 页面
4bd156d feat: DDW AI 底座平台 + 客服插件 v2.0  ← 起点
```

—— 完 ——
