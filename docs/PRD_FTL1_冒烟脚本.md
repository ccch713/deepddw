# PRD: 客户视角冒烟测试脚本（铁律1落地）

> 编号：PRD-FTL1-SMOKE
> 版本：v1.0
> 日期：2026-08-11
> 优先级：P1（Demo 后第一批，防"pytest 过了但 Demo 翻车"）
> 关联铁律：铁律1（客户视角冒烟测试剧本）
> 关联规范：DDW-代码命名规范与入库规范-20260811.md

---

## 1. 背景与目标

### 1.1 问题
83 项 pytest 全过但 Demo 翻车——pytest 测的是"插件能跑"，不是"万永刚能登录"。2026-08-10 当天 30+ 个问题全部是 Demo 现场才暴露。

### 1.2 目标
- `scripts/smoke_demo.sh`：部署后自动跑的核心冒烟（L1）
- L2 角色矩阵清单（5 角色登录验证）
- L3 客户剧本模板（嘉必优万永刚 10 步走查）
- 部署脚本强制耦合：`deploy_to_ecs.sh` 最后一行必须冒烟 PASS 才能继续

---

## 2. 目录结构

```
ddw-ai-hub/
├── scripts/
│   ├── smoke_demo.sh            # 新增：L1 冒烟脚本（5 场景）
│   ├── smoke_l2_roles.sh        # 新增：L2 角色矩阵（5 角色登录）
│   └── smoke_l3_customer.sh     # 新增：L3 客户剧本（嘉必优模板）
└── docs/
    └── SMOKE_SPEC.md            # 冒烟测试规范文档
```

## 3. 核心逻辑

### 3.1 smoke_demo.sh（L1，5 场景）

```bash
#!/usr/bin/env bash
# DDW 冒烟测试 L1：部署后必跑
set -e
BASE="${BASE_URL:-https://ddw.9cio.com}"
PASS=0; FAIL=0

check() {
  local name="$1"; local code="$2"
  if [ "$code" = "200" ] || [ "$code" = "201" ] || [ "$code" = "302" ] || [ "$code" = "308" ]; then
    echo "  ✅ $name (HTTP $code)"; PASS=$((PASS+1))
  else
    echo "  ❌ $name (HTTP $code)"; FAIL=$((FAIL+1))
  fi
}

echo "=== DDW 冒烟测试 L1 ==="
# 场景1：健康检查
check "健康检查 /" "$(curl -s -o /dev/null -w '%{http_code}' $BASE/)"
# 场景2：登录页
check "登录页 /login.html" "$(curl -s -o /dev/null -w '%{http_code}' $BASE/login.html)"
# 场景3：API 根
check "API 根 /api/v1" "$(curl -s -o /dev/null -w '%{http_code}' $BASE/api/v1)"
# 场景4：滑块验证码端点
check "滑块验证码 /api/v1/auth/slider-captcha" "$(curl -s -o /dev/null -w '%{http_code}' -X POST $BASE/api/v1/auth/slider-captcha)"
# 场景5：登录 API（带空 body 应 422，证明路由在）
check "登录 API /api/v1/auth/login-password" "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' $BASE/api/v1/auth/login-password)"

echo ""
echo "=== 结果: PASS=$PASS FAIL=$FAIL ==="
[ $FAIL -eq 0 ] || exit 1
```

### 3.2 smoke_l2_roles.sh（L2，5 角色矩阵）

```bash
#!/usr/bin/env bash
# L2 角色矩阵：5 角色各登录一次，验证跳转正确
# 账号来源：ECS 数据库（测试账号，不用真实客户）
# superadmin → /saas-admin.html
# owner     → /saas-admin.html
# admin     → /saas-admin.html
# member    → /index.html
# partner   → /partner-dashboard.html
# 每个角色：登录 → 获取 JWT → 调 /auth/me → 断言 can_access_admin + redirect_target
```

### 3.3 smoke_l3_customer.sh（L3，客户剧本模板）

```bash
#!/usr/bin/env bash
# 嘉必优万永刚 10 步走查（Demo 前 4 小时必跑）
# 1. 登录（滑块+密码+多租户弹窗）
# 2. 右上角显示"万永刚"+"xxxx"
# 3. 进入 saas-admin 侧栏 6 项可见
# 4. 数据概览 LLM 网关双轨显示
# 5. 成员管理列表可见
# 6. 经销商 demo 账号页有侧栏
# 7. 退出登录
# 8. 江昆鹏登录选嘉必优租户
# 9. 江昆鹏进客户 demo 账号页
# 10. 一键进入嘉必优 demo
```

## 4. 部署耦合

```bash
# deploy_to_ecs.sh 末尾
echo "=== 部署完成，跑冒烟 ==="
ssh ruiguo "bash /opt/ddw/ddw-ai-hub/scripts/smoke_demo.sh" || {
  echo "❌ 冒烟失败，禁止继续！回滚或修复";
  exit 1;
}
```

## 5. 测试用例

| # | 场景 | 断言 |
|---|------|------|
| 1 | 健康检查 | 200 |
| 2 | 登录页 | 200 |
| 3 | API 根 | 200 |
| 4 | 滑块端点 | 200 |
| 5 | 登录 API | 422（空 body，路由存在） |
| 6 | L2 角色矩阵 | 5 角色各自跳转正确 |

## 6. 验收标准

| # | 维度 | 标准 |
|---|------|------|
| 1 | 脚本可执行 | bash scripts/smoke_demo.sh 本地可跑（mock 模式） |
| 2 | ECS 执行 | 部署后自动跑，PASS 才继续 |
| 3 | 铁律1 | 任何部署不过冒烟 = 禁止通知客户 |
| 4 | 文档 | SMOKE_SPEC.md 含 L1/L2/L3 说明 |

## 7. 风险

- ECS 带宽/公网抖动导致误报 → 超时设置 10s，可重试 1 次
- 滑块验证码端点需要 POST 才能生成 token → 已验证存在

## 8. 依赖

- ECS 端有 scripts/ 目录可写
