# TASK_SPEC：冒烟测试脚本（铁律1落地）

> 优先级：P1（Demo 后第一批）
> 执行者：MiMo Code CLI（mimo run headless）
> 验收者：Hermes（DeepSeek 新标准 6 维验收）
> 关联 PRD：docs/PRD_FTL1_冒烟脚本.md
> 关联铁律：铁律1

---

## 一、背景与目标

83 项 pytest 全过但 Demo 翻车——pytest 测的是"插件能跑"，不是"万永刚能登录"。需要 L1 冒烟脚本 + L2 角色矩阵 + L3 客户剧本三层冒烟体系。

## 二、目录结构

```
ddw-ai-hub/
├── scripts/
│   ├── smoke_demo.sh            # 新增：L1 冒烟脚本（5 场景）
│   ├── smoke_l2_roles.sh        # 新增：L2 角色矩阵（5 角色登录）
│   └── smoke_l3_customer.sh     # 新增：L3 客户剧本（嘉必优模板）
└── docs/
    └── SMOKE_SPEC.md            # 新增：冒烟测试规范文档
```

## 三、核心代码

### 3.1 scripts/smoke_demo.sh

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
check "健康检查 /" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 $BASE/)"
check "登录页 /login.html" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 $BASE/login.html)"
check "API 根 /api/v1" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 $BASE/api/v1)"
check "滑块端点 /api/v1/auth/slider" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 $BASE/api/v1/auth/slider)"
check "登录 API /api/v1/auth/login-password" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST -H 'Content-Type: application/json' -d '{}' $BASE/api/v1/auth/login-password)"

echo ""
echo "=== 结果: PASS=$PASS FAIL=$FAIL ==="
[ $FAIL -eq 0 ] || exit 1
```

### 3.2 scripts/smoke_l2_roles.sh（模板）

```bash
#!/usr/bin/env bash
# L2 角色矩阵：5 角色各登录一次，验证跳转正确
# 用法：先配置 TEST_ACCOUNTS 数组（superadmin/owner/admin/member/partner 各一个测试账号）
# 每个角色：登录 → 获取 JWT → 调 /auth/me → 断言 can_access_admin + redirect_target
# 输出：每个角色 PASS/FAIL，任一 FAIL exit 1
```

### 3.3 scripts/smoke_l3_customer.sh（模板）

```bash
#!/usr/bin/env bash
# L3 客户剧本：嘉必优万永刚 10 步走查（Demo 前 4 小时必跑）
# 1. 登录（滑块+密码） → 2. 右上角用户名 → 3. saas-admin 侧栏可见
# 4. LLM 网关双轨 → 5. 成员管理 → 6. demo账号页有侧栏
# 7. 退出 → 8. 江昆鹏登录选嘉必优租户 → 9. demo账号列表 → 10. 一键进入
# 每步一个 echo "[n/10] PASS/FAIL"，FAIL 即 exit 1
```

### 3.4 docs/SMOKE_SPEC.md

```markdown
# DDW 冒烟测试规范

## L1（部署后自动跑）
- 命令：bash scripts/smoke_demo.sh
- 场景：健康检查/登录页/API根/滑块/登录API
- 触发：deploy_to_ecs.sh 最后一行，失败禁止继续

## L2（Demo 前 1 天手动）
- 命令：bash scripts/smoke_l2_roles.sh
- 场景：5 角色登录跳转验证
- 证据：截图 + 输出留存

## L3（Demo 前 4 小时手动）
- 命令：bash scripts/smoke_l3_customer.sh
- 场景：客户定制 10 步走查
- 铁律：任一步失败 → 取消 Demo 改期
```

## 四、测试用例（5 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | smoke_demo.sh 本地 mock 模式可跑 | exit 0 |
| 2 | 5 个场景 curl 命令语法正确 | bash -n 通过 |
| 3 | L2 脚本包含 5 角色定义 | grep 5 个 role |
| 4 | L3 脚本包含 10 步 | grep 10 个 step |
| 5 | 部署脚本引用 smoke_demo.sh | deploy_to_ecs.sh 含调用 |

## 五、验收标准

| # | 维度 | 标准 |
|---|------|------|
| A | bash -n | 3 个脚本语法通过 |
| B | 本地执行 | mock 模式 PASS |
| C | 文档 | SMOKE_SPEC.md 完整 |
| D | 铁律1 | 部署耦合到位 |

## 六、红线

1. 脚本中不放真实密码（用环境变量/测试账号配置）
2. 不依赖特定网络（超时 10s + 可重试）
3. commit：`feat(scripts): 冒烟测试三层体系+部署耦合 [LLM: mimo-code]`，不 push
4. 不要动 ECS 上的文件
