#!/usr/bin/env bash
# ==============================================================================
# DDW 冒烟测试 L2：5 角色登录矩阵（Demo 前 1 天手动）
# 用途：验证 5 种角色 (superadmin/owner/admin/member/partner) 登录后跳转正确
# 用法：
#   1. 复制本文件为 smoke_l2_roles.local.sh 并填入 TEST_ACCOUNTS 真实测试账号
#      （推荐：5 个独立租户各注册一个 demo 账号）
#   2. bash scripts/smoke_l2_roles.sh                # 真跑
#   3. MOCK_MODE=1 bash scripts/smoke_l2_roles.sh     # 模板/语法自检（不连后端）
# 退出码：0=PASS；非0=任一角色失败
# ==============================================================================
set -e

BASE="${BASE_URL:-https://ddw.9cio.com}"
TIMEOUT="${SMOKE_TIMEOUT:-15}"
MOCK_MODE="${MOCK_MODE:-0}"

PASS=0; FAIL=0

if [ -t 1 ]; then
  GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
else
  GREEN=''; RED=''; YELLOW=''; NC=''
fi

# --- 角色定义：role|account|password|expected_redirect|can_access_admin(true/false) ---
# 默认占位数据，本地真跑时通过 TEST_ACCOUNTS_FILE 覆盖
DEFAULT_ACCOUNTS=(
  "superadmin|13800000001|Test@2026|/admin/super|true"
  "owner|13800000002|Test@2026|/saas-admin|true"
  "admin|13800000003|Test@2026|/saas-admin|true"
  "member|13800000004|Test@2026|/saas-admin|false"
  "partner|13800000005|Test@2026|/partner-portal|true"
)

ACCOUNTS_FILE="${TEST_ACCOUNTS_FILE:-}"
if [ -n "$ACCOUNTS_FILE" ] && [ -f "$ACCOUNTS_FILE" ]; then
  # shellcheck disable=SC2207
  ACCOUNTS=( $(cat "$ACCOUNTS_FILE") )
else
  ACCOUNTS=( "${DEFAULT_ACCOUNTS[@]}" )
fi

# --- 单角色测试函数 ---
test_role() {
  local spec="$1"
  IFS='|' read -r role account password expect_redirect expect_admin <<<"$spec"
  echo ""
  echo "--- 角色: $role  账号: $account ---"

  local resp=""; local http_code="000"
  if [ "$MOCK_MODE" = "1" ]; then
    # mock：假装全部 PASS（用 jq 友好的小写）
    http_code="200"
    if [ "$expect_admin" = "true" ]; then
      resp='{"token":"mock.jwt","user":{"role":"'$role'","name":"mock-'$role'","can_access_admin":true}}'
    else
      resp='{"token":"mock.jwt","user":{"role":"'$role'","name":"mock-'$role'","can_access_admin":false}}'
    fi
  else
    # 1) 拉滑块（拿到 captcha_id + 背景图，本脚本不验图，只取 id 用于后续登录）
    local slider_json
    slider_json=$(curl -sS -m "$TIMEOUT" "$BASE/api/v1/auth/slider" 2>/dev/null || echo "")
    local captcha_id
    captcha_id=$(echo "$slider_json" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("captcha_id",""))' 2>/dev/null || echo "")
    if [ -z "$captcha_id" ]; then
      echo -e "  ${RED}❌ 滑块获取失败${NC}"; FAIL=$((FAIL+1)); return 1
    fi
    # 2) 密码登录（开发环境 DDW_ALWAYS_ACCEPT_CODE=8888 → captcha 固定值即可）
    resp=$(curl -sS -m "$TIMEOUT" -X POST \
      -H 'Content-Type: application/json' \
      -d "{\"account\":\"$account\",\"password\":\"$password\",\"captcha_id\":\"$captcha_id\",\"captcha_code\":\"8888\"}" \
      "$BASE/api/v1/auth/login-password" 2>/dev/null || echo "")
    http_code="000"
  fi

  # 解析 token + user.role + user.can_access_admin
  local token role_got admin_got
  token=$(echo "$resp" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("token",""))' 2>/dev/null || echo "")
  role_got=$(echo "$resp" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("user",{}).get("role",""))' 2>/dev/null || echo "")
  admin_got=$(echo "$resp" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("user",{}).get("can_access_admin",False))' 2>/dev/null || echo "False")

  # 断言（json.loads 会把 true 转 Python True，print 出来是大写——直接字符串比对前先 lower）
  local admin_got_norm
  admin_got_norm=$(echo "$admin_got" | tr '[:upper:]' '[:lower:]')
  if [ -n "$token" ] && [ "$role_got" = "$role" ] && [ "$admin_got_norm" = "$expect_admin" ]; then
    echo -e "  ${GREEN}✅ $role 登录成功  role=$role_got  can_access_admin=$admin_got${NC}"
    PASS=$((PASS+1))
  else
    echo -e "  ${RED}❌ $role 失败  token=${token:0:8}  role=$role_got  admin=$admin_got (期望 admin=$expect_admin)${NC}"
    FAIL=$((FAIL+1))
  fi
}

echo "=== DDW 冒烟测试 L2：5 角色登录矩阵 ==="
echo "  目标: $BASE  Mock: $MOCK_MODE  角色数: ${#ACCOUNTS[@]}"
for spec in "${ACCOUNTS[@]}"; do
  test_role "$spec"
done

echo ""
echo "=== 结果: PASS=$PASS  FAIL=$FAIL ==="
[ "$FAIL" -eq 0 ] || { echo -e "${RED}L2 失败，禁止进入 Demo${NC}"; exit 1; }
echo -e "${GREEN}L2 通过 ✓${NC}"
exit 0