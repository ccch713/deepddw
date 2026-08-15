#!/usr/bin/env bash
# ==============================================================================
# DDW AI Hub — ECS 部署前环境检查
# 版本: v5.7.0
# 用途: 检查本地和远端 ECS 环境是否满足部署条件
# 用法: bash scripts/ecs_preflight_check.sh [--json]
# ==============================================================================
set -euo pipefail

# --- 配置 ---
ECS_HOST="${DDW_ECS_HOST:-8.145.35.164}"
ECS_USER="${DDW_ECS_USER:-root}"
ECS_DIR="${DDW_ECS_DIR:-/opt/ddw/ddw-ai-hub}"
ECS_SERVICE="${DDW_ECS_SERVICE:-ddw-core}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_SRC="${PROJECT_ROOT}/cloud-llm/ddw-ai-hub"
JSON_MODE=false

[[ "${1:-}" == "--json" ]] && JSON_MODE=true

# --- 颜色 ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'

PASS=0; WARN=0; FAIL=0

check() {
    local label="$1"; shift
    local result
    result=$("$@" 2>&1) && { echo -e "  ${GREEN}✓${NC} ${label}"; ((PASS++)); return 0; } \
        || { echo -e "  ${RED}✗${NC} ${label}: ${result}"; ((FAIL++)); return 1; }
}

warn_check() {
    local label="$1"; shift
    local result
    result=$("$@" 2>&1) && { echo -e "  ${GREEN}✓${NC} ${label}"; ((PASS++)); return 0; } \
        || { echo -e "  ${YELLOW}⚠${NC} ${label}: ${result}"; ((WARN++)); return 1; }
}

ssh_cmd() {
    ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
        "${ECS_USER}@${ECS_HOST}" "$@"
}

echo -e "\n${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  DDW AI Hub — ECS 部署前环境检查 v5.7.0${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"

# ──────────────────────────────────────────────────────
# 1. 本地环境
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[1/6] 本地环境${NC}"

check "rsync 已安装" command -v rsync
check "ssh 已安装" command -v ssh
check "本地源码目录存在" test -d "${LOCAL_SRC}"
check "core/main.py 存在" test -f "${LOCAL_SRC}/core/main.py"
check "frontend/ 目录存在" test -d "${LOCAL_SRC}/frontend"
check "plugins/ 目录存在" test -d "${LOCAL_SRC}/plugins"
check "marketplace 模块存在" test -d "${LOCAL_SRC}/core/marketplace"
check "publisher 模块存在" test -d "${LOCAL_SRC}/core/marketplace/publisher"

# 检查关键插件
for plugin in ddw_token_manager ddw_llm_gateway; do
    check "插件 ${plugin} 存在" test -d "${LOCAL_SRC}/plugins/${plugin}"
done

# ──────────────────────────────────────────────────────
# 2. ECS 连通性
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[2/6] ECS 连通性${NC}"

check "ping ${ECS_HOST}" ping -c 1 -W 3 "${ECS_HOST}"
check "SSH 端口可达" nc -z -w 5 "${ECS_HOST}" 22

# SSH 有多种可能的失败原因（密码、key、CrowdSec封禁），这里只检查是否能连接
ssh_test_output=$(ssh_cmd "echo ok" 2>&1) && {
    echo -e "  ${GREEN}✓${NC} SSH 认证通过"
    ((PASS++))
} || {
    if echo "$ssh_test_output" | grep -qi "timeout\|timed out\|refused"; then
        echo -e "  ${RED}✗${NC} SSH 连接超时 — 可能被 CrowdSec 封禁"
        echo -e "       诊断: nc -z -w 5 ${ECS_HOST} 22"
        echo -e "       修复: 阿里云 Workbench → cscli decisions delete --ip <你的IP>"
    else
        echo -e "  ${RED}✗${NC} SSH 认证失败: ${ssh_test_output}"
    fi
    ((FAIL++))
}

# ──────────────────────────────────────────────────────
# 3. ECS 远端环境
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[3/6] ECS 远端环境${NC}"

ssh_ok() {
    ssh_cmd "$@" >/dev/null 2>&1
}

check "ECS 目标目录 ${ECS_DIR}" ssh_cmd "test -d ${ECS_DIR}"
check "ECS Python venv 存在" ssh_cmd "test -x /opt/ddw/venv311/bin/python"
warn_check "Python venv 版本 ≥ 3.11" ssh_cmd "/opt/ddw/venv311/bin/python -c 'import sys; assert sys.version_info >= (3,11)'"
check "systemd 服务 ${ECS_SERVICE} 存在" ssh_cmd "test -f /etc/systemd/system/${ECS_SERVICE}.service"
check "ECS .env 文件存在" ssh_cmd "test -f /opt/ddw/.env"
check "Caddy Docker 容器运行中" ssh_cmd "docker ps --format '{{.Names}}' | grep -q caddy"
check "PostgreSQL 容器运行中" ssh_cmd "docker ps --format '{{.Names}}' | grep -q postgres"

# 端口检查
check "端口 8500 可达" ssh_cmd "ss -tlnp | grep -q ':8500'"

# ──────────────────────────────────────────────────────
# 4. ECS 磁盘/内存
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[4/6] ECS 资源${NC}"

DISK_AVAIL=$(ssh_cmd "df -BM ${ECS_DIR} 2>/dev/null | tail -1 | awk '{print \$4}'" 2>/dev/null || echo "0")
DISK_AVAIL_NUM=${DISK_AVAIL//M/}
if [[ "${DISK_AVAIL_NUM}" -gt 500 ]]; then
    echo -e "  ${GREEN}✓${NC} 磁盘剩余: ${DISK_AVAIL}"
    ((PASS++))
elif [[ "${DISK_AVAIL_NUM}" -gt 100 ]]; then
    echo -e "  ${YELLOW}⚠${NC} 磁盘剩余偏低: ${DISK_AVAIL}"
    ((WARN++))
else
    echo -e "  ${RED}✗${NC} 磁盘不足: ${DISK_AVAIL}"
    ((FAIL++))
fi

MEM_AVAIL=$(ssh_cmd "free -m | awk '/^Mem:/{print \$7}'" 2>/dev/null || echo "0")
if [[ "${MEM_AVAIL}" -gt 500 ]]; then
    echo -e "  ${GREEN}✓${NC} 可用内存: ${MEM_AVAIL}MB"
    ((PASS++))
elif [[ "${MEM_AVAIL}" -gt 200 ]]; then
    echo -e "  ${YELLOW}⚠${NC} 内存偏低: ${MEM_AVAIL}MB"
    ((WARN++))
else
    echo -e "  ${RED}✗${NC} 内存不足: ${MEM_AVAIL}MB"
    ((FAIL++))
fi

# ──────────────────────────────────────────────────────
# 5. ECS 部署一致性检查
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[5/6] 部署一致性${NC}"

# 检查本地和远端 core/ 目录结构
LOCAL_CORE_COUNT=$(find "${LOCAL_SRC}/core" -name "*.py" -not -path "*__pycache__*" 2>/dev/null | wc -l | tr -d ' ')
REMOTE_CORE_COUNT=$(ssh_cmd "find ${ECS_DIR}/core -name '*.py' -not -path '*__pycache__*' 2>/dev/null | wc -l" 2>/dev/null | tr -d ' ')
echo -e "  ${GREEN}✓${NC} 本地 core/ Python 文件: ${LOCAL_CORE_COUNT}"
echo -e "  ${GREEN}✓${NC} 远端 core/ Python 文件: ${REMOTE_CORE_COUNT:-0}"

LOCAL_FRONTEND_COUNT=$(find "${LOCAL_SRC}/frontend" -type f 2>/dev/null | wc -l | tr -d ' ')
REMOTE_FRONTEND_COUNT=$(ssh_cmd "find ${ECS_DIR}/frontend -type f 2>/dev/null | wc -l" 2>/dev/null | tr -d ' ')
echo -e "  ${GREEN}✓${NC} 本地 frontend/ 文件: ${LOCAL_FRONTEND_COUNT}"
echo -e "  ${GREEN}✓${NC} 远端 frontend/ 文件: ${REMOTE_FRONTEND_COUNT:-0}"

LOCAL_PLUGINS=$(ls -d "${LOCAL_SRC}"/plugins/*/ 2>/dev/null | xargs -I{} basename {} | grep -v "^_" | tr '\n' ', ')
echo -e "  ${GREEN}✓${NC} 本地插件: ${LOCAL_PLUGINS:-无}"

# ──────────────────────────────────────────────────────
# 6. 安全检查
# ──────────────────────────────────────────────────────
echo -e "\n${BOLD}[6/6] 安全检查${NC}"

warn_check ".env 不含占位符密码" ssh_cmd "! grep -qE 'xxx_pass|changeme|your_|PASSWORD=\*\*\*' /opt/ddw/.env 2>/dev/null"
warn_check "ufw 已启用" ssh_cmd "ufw status | grep -q 'active'"
warn_check "SSH 密码登录已禁用" ssh_cmd "grep -q '^PasswordAuthentication no' /etc/ssh/sshd_config 2>/dev/null"
check "CrowdSec 运行中" ssh_cmd "systemctl is-active crowdsec 2>/dev/null | grep -q active"

# ──────────────────────────────────────────────────────
# 汇总
# ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}通过: ${PASS}${NC}  ${YELLOW}警告: ${WARN}${NC}  ${RED}失败: ${FAIL}${NC}"
if [[ ${FAIL} -eq 0 ]]; then
    echo -e "  ${GREEN}${BOLD}环境检查通过 — 可以部署${NC}"
else
    echo -e "  ${RED}${BOLD}有 ${FAIL} 项检查失败 — 请先修复再部署${NC}"
fi
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"

exit ${FAIL}
