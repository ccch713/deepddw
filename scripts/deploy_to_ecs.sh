#!/usr/bin/env bash
# ==============================================================================
# DDW AI Hub — 一键 ECS 部署脚本
# 版本: v5.7.0
# 用途: 将 DDW 主应用 + 插件 + 前端同步到 ECS 并重启服务
# 用法: bash scripts/deploy_to_ecs.sh [--dry-run] [--skip-health] [--only PLUGIN]
# ==============================================================================
set -euo pipefail

# --- 配置 ---
ECS_HOST="${DDW_ECS_HOST:-8.145.35.164}"
ECS_USER="${DDW_ECS_USER:-root}"
ECS_DIR="${DDW_ECS_DIR:-/opt/ddw/ddw-ai-hub}"
ECS_SERVICE="${DDW_ECS_SERVICE:-ddw-core}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_SRC="${PROJECT_ROOT}/cloud-llm/ddw-ai-hub"
HEALTH_TIMEOUT=60
DRY_RUN=false
SKIP_HEALTH=false
ONLY_PLUGIN=""

# --- 参数解析 ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=true; shift ;;
        --skip-health) SKIP_HEALTH=true; shift ;;
        --only)       ONLY_PLUGIN="$2"; shift 2 ;;
        --help|-h)
            echo "用法: $0 [--dry-run] [--skip-health] [--only PLUGIN]"
            echo "  --dry-run      仅显示将执行的操作，不实际部署"
            echo "  --skip-health  跳过部署后健康检查"
            echo "  --only NAME    仅部署指定插件"
            exit 0
            ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

# --- 颜色 ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
TS=$(date '+%Y-%m-%d %H:%M:%S')

log()  { echo -e "${TS} ${GREEN}✓${NC} $*"; }
warn() { echo -e "${TS} ${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${TS} ${RED}✗${NC} $*"; }
step() { echo -e "\n${BOLD}── $* ──${NC}"; }

# --- 工具函数 ---
ssh_cmd() {
    ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
        "${ECS_USER}@${ECS_HOST}" "$@"
}

rsync_to() {
    local local_path="$1" remote_path="$2"
    if $DRY_RUN; then
        echo "  [dry-run] rsync ${local_path} → ${ECS_HOST}:${remote_path}"
        return 0
    fi
    rsync -az --delete \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.venv' \
        --exclude='*.egg-info' \
        --exclude='node_modules' \
        --exclude='.git' \
        "${local_path}" "${ECS_USER}@${ECS_HOST}:${remote_path}"
}

# ==============================================================================
echo -e "\n${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  DDW AI Hub — ECS 部署 v5.7.0${NC}"
echo -e "  目标: ${ECS_USER}@${ECS_HOST}:${ECS_DIR}"
echo -e "  时间: ${TS}"
$DRY_RUN && echo -e "  ${YELLOW}*** DRY RUN 模式 — 不会实际修改远端 ***${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"

# ──────────────────────────────────────────────────────
# 0. 前置检查
# ──────────────────────────────────────────────────────
step "0/7 前置检查"

if [[ ! -d "${LOCAL_SRC}/core" ]]; then
    err "本地源码目录不存在: ${LOCAL_SRC}"
    exit 1
fi

if ! ssh_cmd "echo ok" >/dev/null 2>&1; then
    err "SSH 连接到 ${ECS_HOST} 失败"
    echo "  可能原因: 密钥未配置 / CrowdSec 封禁 / 网络不通"
    exit 1
fi
log "SSH 连接正常"

if ! ssh_cmd "test -d ${ECS_DIR}" 2>/dev/null; then
    err "ECS 目标目录不存在: ${ECS_DIR}"
    exit 1
fi
log "ECS 目标目录存在"

# ──────────────────────────────────────────────────────
# 1. 同步 DDW 主应用代码 (core/)
# ──────────────────────────────────────────────────────
step "1/7 同步 DDW 主应用 (core/)"

# ⚠️ 重要: 不要同步 config/deployment.yaml — ECS 上是 PG 版，本地是 SQLite 版
if [[ -n "${ONLY_PLUGIN}" ]]; then
    warn "跳过主应用同步 (仅部署插件 ${ONLY_PLUGIN})"
else
    rsync_to "${LOCAL_SRC}/core/" "${ECS_DIR}/core/"
    log "core/ 同步完成"

    # 同步 config（排除 deployment.yaml）
    mkdir -p /tmp/ddw-deploy-config
    rsync -az --exclude='deployment.yaml' \
        "${LOCAL_SRC}/config/" /tmp/ddw-deploy-config/ 2>/dev/null || true
    if $DRY_RUN; then
        echo "  [dry-run] rsync config/ → ECS (排除 deployment.yaml)"
    else
        rsync -az /tmp/ddw-deploy-config/ \
            "${ECS_USER}@${ECS_HOST}:${ECS_DIR}/config/" 2>/dev/null || true
    fi
    rm -rf /tmp/ddw-deploy-config
    log "config/ 同步完成 (排除 deployment.yaml)"
fi

# ──────────────────────────────────────────────────────
# 2. 同步插件
# ──────────────────────────────────────────────────────
step "2/7 同步插件"

if [[ -n "${ONLY_PLUGIN}" ]]; then
    # 仅部署指定插件
    plugin_dir="${LOCAL_SRC}/plugins/${ONLY_PLUGIN}"
    if [[ ! -d "${plugin_dir}" ]]; then
        err "插件 ${ONLY_PLUGIN} 不存在: ${plugin_dir}"
        exit 1
    fi
    rsync_to "${plugin_dir}/" "${ECS_DIR}/plugins/${ONLY_PLUGIN}/"
    log "插件 ${ONLY_PLUGIN} 同步完成"
else
    # 部署所有插件
    deployed_count=0
    for plugin_dir in "${LOCAL_SRC}"/plugins/*/; do
        plugin_name=$(basename "${plugin_dir}")
        [[ "${plugin_name}" == _* || "${plugin_name}" == .* ]] && continue
        rsync_to "${plugin_dir}" "${ECS_DIR}/plugins/"
        log "插件 ${plugin_name} 同步完成"
        ((deployed_count++))
    done
    log "共部署 ${deployed_count} 个插件"
fi

# ──────────────────────────────────────────────────────
# 3. 同步前端文件
# ──────────────────────────────────────────────────────
step "3/7 同步前端文件 (frontend/)"

if [[ -n "${ONLY_PLUGIN}" ]]; then
    warn "跳过前端同步 (仅部署插件)"
else
    rsync_to "${LOCAL_SRC}/frontend/" "${ECS_DIR}/frontend/"
    log "frontend/ 同步完成"
fi

# ──────────────────────────────────────────────────────
# 4. 同步插件市场模块 (core/marketplace/)
# ──────────────────────────────────────────────────────
step "4/7 同步插件市场模块 (marketplace/)"

if [[ -n "${ONLY_PLUGIN}" ]]; then
    warn "跳过 marketplace 同步 (仅部署插件)"
else
    # marketplace 已包含在 core/ 同步中，此处确认
    if ssh_cmd "test -d ${ECS_DIR}/core/marketplace" 2>/dev/null; then
        log "marketplace/ 已同步 (随 core/)"
    else
        rsync_to "${LOCAL_SRC}/core/marketplace/" "${ECS_DIR}/core/marketplace/"
        log "marketplace/ 同步完成"
    fi
fi

# ──────────────────────────────────────────────────────
# 5. 清理 __pycache__ 并验证远端文件
# ──────────────────────────────────────────────────────
step "5/7 清理缓存 + 验证"

if ! $DRY_RUN; then
    ssh_cmd "find ${ECS_DIR} -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; echo ok" >/dev/null
    log "__pycache__ 已清理"

    # 验证关键文件
    for f in core/main.py core/__init__.py; do
        if ssh_cmd "test -f ${ECS_DIR}/${f}" 2>/dev/null; then
            log "验证: ${f} ✓"
        else
            err "验证失败: ${f} 不存在!"
        fi
    done
fi

# ──────────────────────────────────────────────────────
# 6. 重启 DDW 服务
# ──────────────────────────────────────────────────────
step "6/7 重启 DDW 服务"

if $DRY_RUN; then
    echo "  [dry-run] systemctl restart ${ECS_SERVICE}"
else
    # 先检查服务状态
    prev_status=$(ssh_cmd "systemctl is-active ${ECS_SERVICE} 2>/dev/null" || echo "inactive")
    log "服务之前状态: ${prev_status}"

    ssh_cmd "systemctl restart ${ECS_SERVICE}" || {
        err "服务重启失败，尝试查看日志..."
        ssh_cmd "journalctl -u ${ECS_SERVICE} --no-pager -n 20" || true
        exit 1
    }
    log "服务重启命令已发送"

    # 等待服务启动
    sleep 3
    new_status=$(ssh_cmd "systemctl is-active ${ECS_SERVICE} 2>/dev/null" || echo "failed")
    if [[ "${new_status}" == "active" ]]; then
        log "服务已启动: ${new_status}"
    else
        err "服务状态异常: ${new_status}"
        warn "查看日志: ssh ${ECS_USER}@${ECS_HOST} 'journalctl -u ${ECS_SERVICE} --no-pager -n 30'"
    fi
fi

# ──────────────────────────────────────────────────────
# 7. 部署后健康检查
# ──────────────────────────────────────────────────────
if ! $SKIP_HEALTH; then
    step "7/7 健康检查"

    if $DRY_RUN; then
        echo "  [dry-run] curl http://${ECS_HOST}/api/ddw/api/v1/admin/system/health"
    else
        deadline=$((SECONDS + HEALTH_TIMEOUT))
        healthy=false
        while [[ $SECONDS -lt $deadline ]]; do
            health_resp=$(curl -sS -m 5 \
                "http://${ECS_HOST}/api/ddw/api/v1/admin/system/health" 2>/dev/null || echo "")
            if echo "$health_resp" | grep -qi '"status".*"ok"\|"healthy".*true\|"status".*200'; then
                healthy=true
                break
            fi
            sleep 3
        done

        if $healthy; then
            log "健康检查通过 ✓"
        else
            err "健康检查失败 (${HEALTH_TIMEOUT}s 超时)"
            echo "  手动检查: curl -s http://${ECS_HOST}/api/ddw/api/v1/admin/system/health"
        fi
    fi
else
    warn "跳过健康检查 (--skip-health)"
fi

# ──────────────────────────────────────────────────────
# 完成
# ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}${BOLD}部署完成${NC} — ${TS}"
echo -e "  目标: ${ECS_USER}@${ECS_HOST}:${ECS_DIR}"
echo -e "  服务: systemctl status ${ECS_SERVICE}"
echo -e "  前端: http://${ECS_HOST}/api/ddw/index.html"
echo -e "  健康: http://${ECS_HOST}/api/ddw/api/v1/admin/system/health"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
