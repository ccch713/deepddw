#!/usr/bin/env bash
# ==============================================================================
# DDW 冒烟测试 L1：部署后必跑（铁律1 落地）
# 用途：部署完成后立即跑一遍基础 5 场景，任一失败禁止进入 L2/L3
# 用法：bash scripts/smoke_demo.sh                  # 默认 ddw.9cio.com
#       BASE_URL=http://localhost:8500 bash scripts/smoke_demo.sh   # 本地 mock
#       BASE_URL=http://localhost:8500 MOCK_MODE=1 bash scripts/smoke_demo.sh  # 纯语法/mock 模式
# 退出码：0=PASS；非0=FAIL
# ==============================================================================
set -e

BASE="${BASE_URL:-https://ddw.9cio.com}"
TIMEOUT="${SMOKE_TIMEOUT:-10}"
MOCK_MODE="${MOCK_MODE:-0}"

PASS=0
FAIL=0
RESULTS=()

# 颜色（终端用）
if [ -t 1 ]; then
  GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
else
  GREEN=''; RED=''; YELLOW=''; NC=''
fi

ok()   { echo -e "  ${GREEN}✅${NC} $1 (HTTP $2)"; PASS=$((PASS+1)); RESULTS+=("PASS $1"); }
fail() { echo -e "  ${RED}❌${NC} $1 (HTTP $2)"; FAIL=$((FAIL+1)); RESULTS+=("FAIL $1"); }

check() {
  # check <name> <method> <path> [extra_curl_args...]
  local name="$1"; local method="$2"; local path="$3"; shift 3
  local code
  if [ "$MOCK_MODE" = "1" ]; then
    # mock 模式：返回 200 保证语法/逻辑跑通（端点可达即视为 PASS）
    code="200"
  else
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" -X "$method" "$@" "$BASE$path" || echo "000")
  fi
  case "$code" in
    200|201|302|307|308|422) ok "$name" "$code" ;;  # 307=登录重定向(正常); 422=路由存在但参数校验失败，视为端点可达
    *)                  fail "$name" "$code" ;;
  esac
}

echo "=== DDW 冒烟测试 L1 ==="
echo "  目标: $BASE  超时: ${TIMEOUT}s  Mock: $MOCK_MODE"
echo ""

# 5 个核心场景
check "健康检查 /"            GET  /                                     -H 'Accept: */*'
check "登录页 /ui/login.html"    GET  /ui/login.html
check "OpenAPI /openapi.json"  GET  /openapi.json
check "滑块端点 /api/v1/auth/slider" GET /api/v1/auth/slider
check "登录 API /api/v1/auth/login-password" POST /api/v1/auth/login-password -H 'Content-Type: application/json' -d '{}'

echo ""
echo "=== 结果: PASS=$PASS  FAIL=$FAIL ==="
if [ "$FAIL" -ne 0 ]; then
  echo -e "${RED}冒烟 L1 失败，禁止进入 L2/L3（铁律1）${NC}"
  exit 1
fi
echo -e "${GREEN}冒烟 L1 通过 ✓${NC}"
exit 0