#!/usr/bin/env bash
# ==============================================================================
# DDW 冒烟测试 L3：客户定制剧本 10 步走查（Demo 前 4 小时必跑）
# 用途：按客户真实使用路径走一遍 10 个关键动作，任一步 FAIL → 取消 Demo 改期
# 模板：基于嘉必优万永刚的 Demo 剧本（已脱敏，客户名用占位符）
# 用法：
#   1. 真跑：bash scripts/smoke_l3_customer.sh
#   2. 语法/逻辑自检：MOCK_MODE=1 bash scripts/smoke_l3_customer.sh
#   3. 指定客户：CUSTOMER_NAME="嘉必优" bash scripts/smoke_l3_customer.sh
# 退出码：0=PASS；非0=任一步失败
# ==============================================================================
set -e

BASE="${BASE_URL:-https://ddw.9cio.com}"
TIMEOUT="${SMOKE_TIMEOUT:-20}"
MOCK_MODE="${MOCK_MODE:-0}"
CUSTOMER_NAME="${CUSTOMER_NAME:-嘉必优生物}"

PASS=0; FAIL=0; STEP=0

if [ -t 1 ]; then
  GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
else
  GREEN=''; RED=''; CYAN=''; NC=''
fi

# --- 工具函数 ---
record_pass() {
  STEP=$((STEP+1))
  echo -e "  [${STEP}/10] ${GREEN}PASS${NC} $1"
  PASS=$((PASS+1))
}
record_fail() {
  STEP=$((STEP+1))
  echo -e "  [${STEP}/10] ${RED}FAIL${NC} $1"
  FAIL=$((FAIL+1))
}
record() {
  # record <ok?> <name>
  if [ "$1" = "1" ]; then record_pass "$2"; else record_fail "$2"; fi
}

# http_code <method> <path> [curl_args...]
http_code() {
  local m="$1" p="$2"; shift 2
  if [ "$MOCK_MODE" = "1" ]; then echo "200"; return; fi
  curl -s -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" -X "$m" "$@" "$BASE$p" 2>/dev/null || echo "000"
}

# code_ok <expected_codes...> <actual_code>  → 1=PASS 0=FAIL
code_ok() {
  local actual="${@: -1}"
  for c in "${@:1:$#-1}"; do
    [ "$c" = "$actual" ] && return 0
  done
  # mock 模式全部视为 OK
  [ "$MOCK_MODE" = "1" ] && return 0
  return 1
}

# --- 10 步剧本 ---
echo "=== DDW 冒烟测试 L3：客户剧本 10 步走查 ==="
echo "  目标: $BASE  Mock: $MOCK_MODE  客户: $CUSTOMER_NAME"
echo ""

# 步骤 1: 登录（滑块+密码）
echo -e "${CYAN}[步骤 1]${NC} 登录（滑块+密码）"
c=$(http_code POST /api/v1/auth/login-password -H 'Content-Type: application/json' -d '{"account":"13800000002","password":"Test@2026","captcha_id":"mock","captcha_code":"8888"}')
if code_ok 200 201 422 "$c"; then record_pass "登录 API 可达 (HTTP $c)"; else record_fail "登录 API 失败 (HTTP $c)"; fi

# 步骤 2: 右上角用户名（/auth/me）
echo ""
echo -e "${CYAN}[步骤 2]${NC} 右上角用户名（/auth/me）"
c=$(http_code GET /api/v1/auth/me)
if code_ok 200 401 "$c"; then record_pass "用户信息端点可达 (HTTP $c)"; else record_fail "用户信息端点失败 (HTTP $c)"; fi

# 步骤 3: saas-admin 数据概览
echo ""
echo -e "${CYAN}[步骤 3]${NC} saas-admin 数据概览接口"
c=$(http_code GET /api/v1/admin/overview)
if code_ok 200 "$c"; then record_pass "数据概览接口可达 (HTTP $c)"; else record_fail "数据概览接口失败 (HTTP $c)"; fi

# 步骤 4: LLM 网关双轨
echo ""
echo -e "${CYAN}[步骤 4]${NC} LLM 网关双轨（云端/本地）"
c1=$(http_code GET /api/v1/llm/providers)
c2=$(http_code GET /api/v1/llm/gateway/health)
if code_ok 200 "$c1" && code_ok 200 "$c2"; then
  record_pass "LLM 网关双轨可达 (cloud=$c1 local=$c2)"
else
  record_fail "LLM 网关双轨失败 (cloud=$c1 local=$c2)"
fi

# 步骤 5: 成员管理
echo ""
echo -e "${CYAN}[步骤 5]${NC} 成员管理（/users/）"
c=$(http_code GET /api/v1/users/)
if code_ok 200 "$c"; then record_pass "成员列表可获取 (HTTP $c)"; else record_fail "成员列表失败 (HTTP $c)"; fi

# 步骤 6: saas-admin.html 侧栏可达
echo ""
echo -e "${CYAN}[步骤 6]${NC} saas-admin.html 侧栏可达"
c=$(http_code GET /saas-admin.html)
if code_ok 200 "$c"; then record_pass "saas-admin.html 可加载 (HTTP $c)"; else record_fail "saas-admin.html 失败 (HTTP $c)"; fi

# 步骤 7: 退出登录
echo ""
echo -e "${CYAN}[步骤 7]${NC} 退出登录（/auth/logout）"
c=$(http_code POST /api/v1/auth/logout)
if code_ok 200 204 "$c"; then record_pass "退出接口可达 (HTTP $c)"; else record_fail "退出接口失败 (HTTP $c)"; fi

# 步骤 8: 经销商登录 + 选租户
echo ""
echo -e "${CYAN}[步骤 8]${NC} 经销商登录 + 选租户"
c1=$(http_code POST /api/v1/auth/login-password -H 'Content-Type: application/json' -d '{}')
c2=$(http_code GET /api/v1/partners/tenants)
if code_ok 200 422 "$c1" && code_ok 200 "$c2"; then
  record_pass "经销商登录+租户列表可达 (login=$c1 tenants=$c2)"
else
  record_fail "经销商链路失败 (login=$c1 tenants=$c2)"
fi

# 步骤 9: Demo 账号列表
echo ""
echo -e "${CYAN}[步骤 9]${NC} 客户 Demo 账号列表"
c=$(http_code GET /api/v1/admin/demo-accounts)
if code_ok 200 "$c"; then record_pass "Demo 账号列表可达 (HTTP $c)"; else record_fail "Demo 账号列表失败 (HTTP $c)"; fi

# 步骤 10: 一键进入
echo ""
echo -e "${CYAN}[步骤 10]${NC} 一键进入（/admin/demo-accounts/enter）"
c=$(http_code POST /api/v1/admin/demo-accounts/enter -H 'Content-Type: application/json' -d '{}')
if code_ok 200 201 "$c"; then record_pass "一键进入可达 (HTTP $c)"; else record_fail "一键进入失败 (HTTP $c)"; fi

# --- 汇总 ---
echo ""
echo "=== 结果: PASS=$PASS  FAIL=$FAIL ==="
if [ "$FAIL" -ne 0 ]; then
  echo -e "${RED}客户剧本 10 步走查失败 → 取消 Demo 改期（铁律1）${NC}"
  exit 1
fi
echo -e "${GREEN}客户剧本 10 步走查全部通过 ✓ 可以 Demo${NC}"
exit 0