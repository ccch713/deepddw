# DDW 冒烟测试规范

> 铁律1 落地：**83 项 pytest 全过 ≠ 客户能登录**。三层冒烟补齐"端到端可走查"环节。

---

## 背景

83 项 pytest 测试的是"插件能跑、模型能调"，但以下场景不会被覆盖：

- 健康检查 `/` 是否真的 200（CDN/反代/数据库三层是否都正常）
- 登录页是否能被未登录用户访问
- API 根路径是否注册成功
- 滑块端点是否返回有效 captcha_id
- 登录 API 是否接受空 body 并返回 422（说明端点在线）
- 5 种角色 (superadmin/owner/admin/member/partner) 是否能各自登录并跳到正确页面
- 客户真实使用路径 10 步是否有任何一步断链

故引入 **L1（基础 5 场景）+ L2（5 角色登录矩阵）+ L3（客户定制 10 步剧本）** 三层冒烟。

---

## L1 — 部署后自动跑（铁门禁）

| 项 | 值 |
|---|---|
| 命令 | `bash scripts/smoke_demo.sh` |
| 触发 | `deploy_to_ecs.sh` 第 7 步健康检查之后、退出前 |
| 场景 | 健康检查 / / 登录页 /login.html / API 根 /api/v1 / 滑块 /api/v1/auth/slider / 登录 API /api/v1/auth/login-password |
| 通过标准 | 5/5 PASS，FAIL 立即禁止进入 L2/L3 |
| 退出码 | 0=PASS，1=FAIL |
| 超时 | 每个请求 10s（可通过 `SMOKE_TIMEOUT` 调整） |
| Mock 模式 | `MOCK_MODE=1 bash scripts/smoke_demo.sh`（仅验证脚本语法和逻辑，不连后端） |

### L1 与 deploy_to_ecs.sh 的耦合

`scripts/deploy_to_ecs.sh` 的第 7 步 `健康检查` 之后追加 L1 调用：

```bash
log "L1 冒烟开始..."
if ! bash scripts/smoke_demo.sh; then
    err "L1 冒烟失败 → 回滚部署"
    exit 1
fi
log "L1 冒烟通过 ✓"
```

---

## L2 — Demo 前 1 天手动

| 项 | 值 |
|---|---|
| 命令 | `bash scripts/smoke_l2_roles.sh` |
| 触发 | Demo 前 24 小时内手动跑（不是 CI 自动） |
| 场景 | superadmin / owner / admin / member / partner 5 角色各登录一次 |
| 通过标准 | 5/5 PASS，FAIL 立即取消 Demo 改期 |
| 证据 | 截图 + 输出留存到 `dev-log/smoke/L2-YYYYMMDD-HHMM.log` |
| 测试账号 | 推荐每个角色独立租户一个 demo 账号，配置 `TEST_ACCOUNTS_FILE=accounts.txt` 覆盖默认占位 |

### accounts.txt 格式（每行一个）

```
superadmin|13800000001|Test@2026|/admin/super|true
owner|13800000002|Test@2026|/saas-admin|true
admin|13800000003|Test@2026|/saas-admin|true
member|13800000004|Test@2026|/saas-admin|false
partner|13800000005|Test@2026|/partner-portal|true
```

格式：`role|account|password|expected_redirect|can_access_admin(true/false)`

### Mock 模式

`MOCK_MODE=1 bash scripts/smoke_l2_roles.sh` 跳过真实登录，假装 5 角色全部 PASS（仅验证脚本逻辑）。

---

## L3 — Demo 前 4 小时手动（客户定制）

| 项 | 值 |
|---|---|
| 命令 | `bash scripts/smoke_l3_customer.sh` |
| 触发 | Demo 前 4 小时手动跑（铁律1） |
| 场景 | 10 步客户剧本（默认基于嘉必优万永刚脱敏模板） |
| 通过标准 | 10/10 PASS，任一 FAIL → **取消 Demo 改期** |
| 证据 | 截图 + 输出留存到 `dev-log/smoke/L3-YYYYMMDD-HHMM.log` |
| Mock 模式 | `MOCK_MODE=1 bash scripts/smoke_l3_customer.sh`（仅验证脚本） |

### 10 步剧本

| # | 步骤 | 检查点 |
|---|------|--------|
| 1 | 登录（滑块+密码） | `/api/v1/auth/login-password` 返回 200/201 |
| 2 | 右上角用户名 | `/api/v1/auth/me` 返回 200（端点可达） |
| 3 | saas-admin 数据概览 | `/api/v1/admin/overview` 返回 200 |
| 4 | LLM 网关双轨 | `/api/v1/llm/providers` + `/api/v1/llm/gateway/health` 双 200 |
| 5 | 成员管理 | `/api/v1/users/` 返回 200 |
| 6 | saas-admin.html 侧栏可达 | `/saas-admin.html` 返回 200 |
| 7 | 退出登录 | `/api/v1/auth/logout` 返回 200/204 |
| 8 | 经销商登录+选租户 | 登录接口 + `/api/v1/partners/tenants` 双 200 |
| 9 | 客户 Demo 账号列表 | `/api/v1/admin/demo-accounts` 返回 200 |
| 10 | 一键进入 | `/api/v1/admin/demo-accounts/enter` 返回 200/201 |

---

## 环境变量汇总

| 变量 | 默认 | 用途 |
|---|---|---|
| `BASE_URL` | `https://ddw.9cio.com` | 测试目标地址 |
| `SMOKE_TIMEOUT` | `10` (L1) / `15` (L2) / `20` (L3) | 单请求超时秒数 |
| `MOCK_MODE` | `0` | `1`=mock 模式（不连后端） |
| `TEST_ACCOUNTS_FILE` | 默认占位 | L2 测试账号配置文件路径 |
| `CUSTOMER_NAME` | `嘉必优生物` | L3 客户名（仅展示用） |

---

## 调用矩阵

| 阶段 | 触发方 | 自动/手动 | 失败处置 |
|---|---|---|---|
| 部署后 | `deploy_to_ecs.sh` | 自动 | 回滚部署 |
| Demo 前 1 天 | 操作员 | 手动 | 取消 Demo 改期 |
| Demo 前 4 小时 | 操作员 | 手动 | 取消 Demo 改期 |

---

## 红线

1. 脚本中不放真实密码（用环境变量 / `TEST_ACCOUNTS_FILE` 配置）
2. 不依赖特定网络（每个请求 10-20s 超时 + 可重试）
3. 不动 ECS 上的文件
4. 客户名 / 账号走脱敏占位（`嘉必优` 仅作脚本默认展示文案，真跑时通过 `CUSTOMER_NAME` 覆盖）
5. L1 必须接入 `deploy_to_ecs.sh`；否则视为铁律1 未落地

---

## 测试用例（铁律1 自检 5 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | `bash -n scripts/smoke_demo.sh` | 退出码 0 |
| 2 | `bash -n scripts/smoke_l2_roles.sh` | 退出码 0 |
| 3 | `bash -n scripts/smoke_l3_customer.sh` | 退出码 0 |
| 4 | `MOCK_MODE=1 bash scripts/smoke_demo.sh` | 5/5 PASS |
| 5 | `MOCK_MODE=1 bash scripts/smoke_l3_customer.sh` | 10/10 PASS |

---

## 维护

- 文件位置：`scripts/smoke_demo.sh` / `scripts/smoke_l2_roles.sh` / `scripts/smoke_l3_customer.sh`
- 文档位置：`docs/SMOKE_SPEC.md`
- 关联铁律：铁律1（部署必跑 + Demo 前必跑）
- 关联 PRD：`docs/PRD_FTL1_冒烟脚本.md`