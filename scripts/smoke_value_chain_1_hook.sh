#!/usr/bin/env bash
# ============================================================================
# 链 1 · 获客签约链路冒烟（线索 → 订单）
# 用法: bash scripts/smoke_value_chain_1_hook.sh [BASE_URL]  (默认 http://127.0.0.1:8500)
# 判定: HTTP 200/401/307 = 可达(通过)；5xx/000 = 失败
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

echo "== 链1 获客签约: 线索→商机→报价→合同→电子签→订单 =="
check "/api/v1/plugins/ddw-lead-claim/health"
check "/api/v1/plugins/ddw-opportunity/health"
check "/api/v1/plugins/ddw-quotation/health"
check "/api/v1/plugins/ddw-contract-core/health"
check "/api/v1/plugins/ddw-signature-adapter/health"
check "/api/v1/plugins/ddw-order/health"
check "/api/v1/plugins/ddw-partner-directory/health"

echo "---"
echo "链1 结果: $PASS 通过 / $FAIL 失败"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
