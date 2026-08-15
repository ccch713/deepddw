#!/usr/bin/env bash
# ==============================================================================
# DDW AI Hub — 部署后健康检查
# 版本: v5.7.0
# 用途: 全面检查 DDW 在 ECS 上的运行状态
# 用法: bash scripts/ecs_postdeploy_healthcheck.sh [--json] [--wait SECONDS]
# ==============================================================================
set -euo pipefail

# --- 配置 ---
ECS_HOST="${DDW_ECS_HOST:-8.145.35.164}"
ECS_USER="${DDW_ECS_USER:-root}"
ECS_DIR="${DDW_ECS_DIR:-/opt/ddw/ddw-ai-hub}"
ECS_SERVICE="${DDW_ECS_SERVICE:-ddw-core}"
DDW_PORT=8500
HEALTH_URL="http://${ECS_HOST}/api/ddw/api/v1/admin/system/health"
FRONTEND_URL="http://${ECS_HOST}/api/ddw/index.html"
JSON_MODE=false
WAIT_TIMEOUT=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)  JSON_MODE=true; shift ;;
        --wait)  WAIT_TIMEOUT="$2"; shift 2 ;;
        --help|-h)
            echo "用法: $0 [--json] [--wait SECONDS]"
            echo "  --json      输出 JSON 格式结果"
            echo "  --wait N    最多等待 N 秒再检查 (等待服务启动)"
            exit 0
            ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

# --- 颜色 ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
TS=$(date '+%Y-%m-%d %H:%M:%S')

PASS=0; WARN=0; FAIL=0
JSON_RESULTS=()

check_pass() {
    local label="$1" detail="${2:-}"
    echo -e "  ${GREEN}✓${NC} ${label}${detail:+ — ${detail}}"
    ((PASS++))
    JSON_RESULTS+=("{\"check\":\"${label}\",\"status\":\"pass\",\"detail\":\"${detail}\"}")
}

check_fail() {
    local label="$1" detail="${2:-}"
    echo -e "  ${RED}✗${NC} ${label}${detail:+ — ${detail}}"
    ((FAIL++))
    JSON_RESULTS+=("{\"check\":\"${label}\",\"status\":\"fail\",\"detail\":\"${detail}\"}")
}

check_warn() {
    local label="$1" detail="${2:-}"
    echo -e "  ${YELLOW}⚠${NC} ${label}${detail:+ — ${detail}}"
    ((WARN++))
    JSON_RESULTS+=("{\"check\":\"${label}\",\"status\":\"warn\",\"detail\":\"${detail}\"}")
}

ssh_cmd() {
    ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
        "${ECS_USER}@${ECS_HOST}" "$@"
}

echo -e "\n${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  DDW AI Hub — 部署后健康检查 v5.7.0${NC}"
echo -e "  目标: ${ECS_HOST}"
echo -e "  时间: ${TS}"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"

# ──────────────────────────────────────────────────────
# 0. 等待服务启动 (可选)
# ──────────────────────────────────────────────────────
if [[ "${WAIT_TIMEOUT}" -gt 0 ]]; then
    echo -e "\n${BOLD}[等待] 等待服务启动 (最多 ${WAIT_TIMEOUT}s)${NC}"
    deadline=$((SECONDS + WAIT_TIMEOUT))
    while [[ $SECONDS -lt $deadline ]]; do
        if curl -sS -m 3 "${HEALTH_URL}" 2>/dev/null | grep -qi '"status"'; then
            check_pass "服务已在 ${SECONDS}s 内启动"
            break
        fi
        sleep 2
    done
    if [[ $SECONDS -ge $deadline ]]; then
        check_warn "等待超时" "服务未在 ${WAIT_TIMEOUT}s 内响应"
    fi
fi

# ──────────────────────────────────────────────────────
# 1. systemd 服务状态
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[1/7] systemd 服务${NC}"

svc_active=$(ssh_cmd "systemctl is-active ${ECS_SERVICE} 2>/dev/null" || echo "unknown")
svc_enabled=$(ssh_cmd "systemctl is-enabled ${ECS_SERVICE} 2>/dev/null" || echo "unknown")
svc_uptime=$(ssh_cmd "systemctl show ${ECS_SERVICE} --property=ActiveEnterTimestamp --value 2>/dev/null" || echo "unknown")

if [[ "${svc_active}" == "active" ]]; then
    check_pass "服务运行中" "uptime: ${svc_uptime}"
else
    check_fail "服务未运行" "status: ${svc_active}"
fi

if [[ "${svc_enabled}" == "enabled" ]]; then
    check_pass "服务已设为开机自启"
else
    check_warn "服务未设为开机自启"
fi

# 进程检查
pid=$(ssh_cmd "pgrep -f 'uvicorn core.main' 2>/dev/null" || echo "")
if [[ -n "${pid}" ]]; then
    proc_mem=$(ssh_cmd "ps -o rss= -p ${pid} 2>/dev/null | tr -d ' '" || echo "0")
    proc_mem_mb=$((proc_mem / 1024))
    check_pass "uvicorn 进程存在" "PID=${pid}, RSS=${proc_mem_mb}MB"
else
    check_fail "uvicorn 进程不存在"
fi

# ──────────────────────────────────────────────────────
# 2. HTTP 端口监听
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[2/7] 端口监听${NC}"

port_listen=$(ssh_cmd "ss -tlnp | grep ':${DDW_PORT}' | head -1" 2>/dev/null || echo "")
if [[ -n "${port_listen}" ]]; then
    check_pass "端口 ${DDW_PORT} 监听中" "${port_listen}"
else
    check_fail "端口 ${DDW_PORT} 未监听"
fi

# ──────────────────────────────────────────────────────
# 3. HTTP 健康端点
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[3/7] HTTP 健康端点${NC}"

health_resp=$(curl -sS -m 10 "${HEALTH_URL}" 2>/dev/null || echo "CURL_FAILED")
if [[ "${health_resp}" == "CURL_FAILED" ]]; then
    # 尝试直连 8500 端口 (绕过 Caddy)
    health_resp_direct=$(curl -sS -m 5 "http://${ECS_HOST}:${DDW_PORT}/api/v1/admin/system/health" 2>/dev/null || echo "CURL_FAILED")
    if [[ "${health_resp_direct}" != "CURL_FAILED" ]]; then
        check_warn "通过 Caddy 访问失败" "直连 8500 端口有响应"
        health_resp="${health_resp_direct}"
    else
        check_fail "健康端点无法访问" "Caddy + 直连均失败"
    fi
fi

if echo "${health_resp}" | grep -qi '"status"'; then
    # 提取 status 字段
    status_val=$(echo "${health_resp}" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('status', d.get('healthy', 'unknown')))
except:
    print('parse_error')
" 2>/dev/null || echo "parse_error")
    if [[ "${status_val}" == "ok" || "${status_val}" == "true" || "${status_val}" == "healthy" ]]; then
        check_pass "健康端点返回 OK" "status=${status_val}"
    else
        check_warn "健康端点返回非 OK" "status=${status_val}"
    fi
else
    check_fail "健康端点响应异常" "$(echo "${health_resp}" | head -c 200)"
fi

# ──────────────────────────────────────────────────────
# 4. 前端页面
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[4/7] 前端页面${NC}"

for page in "index.html:首页" "login.html:登录页" "plugin-market.html:插件市场"; do
    fname="${page%%:*}"
    label="${page##*:}"
    http_code=$(curl -sS -o /dev/null -w '%{http_code}' -m 5 \
        "http://${ECS_HOST}/api/ddw/${fname}" 2>/dev/null || echo "000")
    if [[ "${http_code}" == "200" ]]; then
        check_pass "${label} (${fname})" "HTTP ${http_code}"
    else
        check_fail "${label} (${fname})" "HTTP ${http_code}"
    fi
done

# ──────────────────────────────────────────────────────
# 5. 插件健康
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[5/7] 插件状态${NC}"

plugin_list=$(ssh_cmd "ls -d ${ECS_DIR}/plugins/*/ 2>/dev/null | xargs -I{} basename {}" 2>/dev/null || echo "")
if [[ -z "${plugin_list}" ]]; then
    check_warn "未发现已部署插件"
else
    plugin_count=0
    while IFS= read -r plugin_name; do
        [[ -z "${plugin_name}" ]] && continue
        [[ "${plugin_name}" == _* ]] && continue
        plugin_health=$(curl -sS -m 3 \
            "http://${ECS_HOST}:${DDW_PORT}/api/v1/plugins/${plugin_name}/health" 2>/dev/null || echo "CURL_FAILED")
        if echo "${plugin_health}" | grep -qi '"status".*"ok"'; then
            check_pass "插件 ${plugin_name}" "健康"
        elif [[ "${plugin_health}" == "CURL_FAILED" ]]; then
            check_warn "插件 ${plugin_name}" "无响应"
        else
            check_warn "插件 ${plugin_name}" "$(echo "${plugin_health}" | head -c 100)"
        fi
        ((plugin_count++))
    done <<< "${plugin_list}"
    check_pass "插件总数" "${plugin_count} 个"
fi

# ──────────────────────────────────────────────────────
# 6. 基础设施 (Docker)
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[6/7] 基础设施${NC}"

# PostgreSQL
pg_status=$(ssh_cmd "docker ps --filter name=postgres --format '{{.Status}}' 2>/dev/null" || echo "")
if [[ -n "${pg_status}" ]]; then
    check_pass "PostgreSQL 容器" "${pg_status}"
else
    check_warn "PostgreSQL 容器未运行" "可能使用 SQLite"
fi

# Caddy
caddy_status=$(ssh_cmd "docker ps --filter name=caddy --format '{{.Status}}' 2>/dev/null" || echo "")
if [[ -n "${caddy_status}" ]]; then
    check_pass "Caddy 容器" "${caddy_status}"
else
    check_fail "Caddy 容器未运行"
fi

# 磁盘
disk_info=$(ssh_cmd "df -h /opt/ddw 2>/dev/null | tail -1" || echo "")
disk_avail=$(echo "${disk_info}" | awk '{print $4}' || echo "unknown")
disk_pct=$(echo "${disk_info}" | awk '{print $5}' || echo "unknown")
if [[ "${disk_pct}" != "unknown" ]]; then
    pct_num=${disk_pct//%/}
    if [[ "${pct_num}" -lt 80 ]]; then
        check_pass "磁盘使用" "${disk_pct} (可用 ${disk_avail})"
    elif [[ "${pct_num}" -lt 90 ]]; then
        check_warn "磁盘使用偏高" "${disk_pct} (可用 ${disk_avail})"
    else
        check_fail "磁盘使用危险" "${disk_pct} (可用 ${disk_avail})"
    fi
fi

# 内存
mem_info=$(ssh_cmd "free -m | awk '/^Mem:/{printf \"%dMB / %dMB (%d%%)\", \$7, \$2, \$7*100/\$2}'" 2>/dev/null || echo "unknown")
if [[ "${mem_info}" != "unknown" ]]; then
    check_pass "可用内存" "${mem_info}"
fi

# ──────────────────────────────────────────────────────
# 7. 最近日志错误
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[7/7] 最近日志${NC}"

recent_errors=$(ssh_cmd "journalctl -u ${ECS_SERVICE} --since '10 min ago' --no-pager -p err 2>/dev/null | tail -5" 2>/dev/null || echo "")
if [[ -z "${recent_errors}" ]]; then
    check_pass "最近10分钟无错误日志"
else
    error_count=$(echo "${recent_errors}" | wc -l | tr -d ' ')
    check_warn "最近10分钟有 ${error_count} 条错误" ""
    echo "    $(echo "${recent_errors}" | head -3 | sed 's/^/    /')"
fi

# 最近重启
last_restart=$(ssh_cmd "journalctl -u ${ECS_SERVICE} --since '1 hour ago' --no-pager | grep -c 'Started DDW\|Started ddw\|uvicorn.*started' 2>/dev/null" || echo "0")
if [[ "${last_restart}" -gt 0 ]]; then
    check_pass "最近1小时启动记录" "${last_restart} 次"
fi

# ──────────────────────────────────────────────────────
# 汇总
# ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}通过: ${PASS}${NC}  ${YELLOW}警告: ${WARN}${NC}  ${RED}失败: ${FAIL}${NC}"
echo ""

if [[ ${FAIL} -eq 0 && ${WARN} -eq 0 ]]; then
    echo -e "  ${GREEN}${BOLD}🎉 全部通过 — DDW 运行正常${NC}"
    overall="healthy"
elif [[ ${FAIL} -eq 0 ]]; then
    echo -e "  ${YELLOW}${BOLD}⚠ 有 ${WARN} 项警告 — 基本正常，建议关注${NC}"
    overall="degraded"
else
    echo -e "  ${RED}${BOLD}❌ 有 ${FAIL} 项失败 — 需要修复${NC}"
    overall="unhealthy"
fi
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"

# JSON 输出
if $JSON_MODE; then
    json_items=$(IFS=,; echo "${JSON_RESULTS[*]}")
    cat <<EOF
{
  "timestamp": "${TS}",
  "host": "${ECS_HOST}",
  "overall": "${overall}",
  "pass": ${PASS},
  "warn": ${WARN},
  "fail": ${FAIL},
  "checks": [${json_items}]
}
EOF
fi

exit ${FAIL}
