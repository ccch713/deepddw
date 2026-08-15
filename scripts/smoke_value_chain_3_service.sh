#!/usr/bin/env bash
# ============================================================================
# 链 3 · 服务续费链路冒烟（工单 → 续费）
# 用法: bash scripts/smoke_value_chain_3_service.sh [BASE_URL]
# ============================================================================
BASE="${1:-http://127.0.0.1:8500}"
PASS=0; FAIL=0

check() {
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$BASE$1")
  if [ "$code" = "000" ] || [ "${code:0:1}" = "5" ]; then
    echo "❌ $1 ($code)"; FAIL=$((FAIL+1))
  else
    echo "✅ $1 ($code)"; PASS=$((PASS+1))
  fi
}

echo "== 链3 服务续费: 工单→客服→跟进→知识库→续费 =="
check "/api/v1/plugins/ddw-support-ticket/health"
check "/api/v1/plugins/ddw_online_cs/health"
check "/api/v1/plugins/ddw_followup/health"
check "/api/v1/plugins/ddw-knowledge-hierarchy/health"
check "/api/v1/plugins/ddw-ent-knowledge/health"
check "/api/v1/plugins/ddw-renewal/health"

echo "---"
echo "链3 结果: $PASS 通过 / $FAIL 失败"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
