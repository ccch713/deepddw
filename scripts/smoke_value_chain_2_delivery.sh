#!/usr/bin/env bash
# ============================================================================
# 链 2 · 交付履约链路冒烟（订单 → 回款）
# 用法: bash scripts/smoke_value_chain_2_delivery.sh [BASE_URL]
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

echo "== 链2 交付履约: 订单→实例绑定→授权→收款→对账→开票→应收 =="
check "/api/v1/plugins/ddw-order/health"
check "/api/v1/plugins/ddw-instance-binding/health"
check "/api/v1/plugins/ddw-license-core/health"
check "/api/v1/plugins/ddw_wallet/health"
check "/api/v1/plugins/ddw_offline_pos/health"
check "/api/v1/plugins/ddw-reconciliation/health"
check "/api/v1/plugins/ddw-invoice/health"
check "/api/v1/plugins/ddw-receivable/health"

echo "---"
echo "链2 结果: $PASS 通过 / $FAIL 失败"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
