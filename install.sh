#!/bin/bash
# deepDDW 0.1 · 一键安装启动脚本
# 用法: bash install.sh [--port 8500] [--no-test] [--bg]
# 适用: macOS 14+ / Ubuntu 22+（Python 3.11+ 或 Docker）
set -euo pipefail

PORT=${DDW_PORT:-8500}
RUN_TESTS=true
BG_MODE=false
USE_DOCKER=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --port) PORT=$2; shift 2;;
        --docker) USE_DOCKER=true; shift;;
        --no-test) RUN_TESTS=false; shift;;
        --bg) BG_MODE=true; shift;;
        -h|--help)
            echo "deepDDW 一键安装部署脚本"
            echo "用法: bash install.sh [选项]"
            echo "  --port PORT   服务端口 (默认 8500)"
            echo "  --docker      使用 Docker Compose 部署（推荐全新服务器）"
            echo "  --no-test     跳过测试"
            echo "  --bg          后台运行（非 docker 模式）"
            exit 0;;
        *) echo "未知参数: $1"; exit 1;;
    esac
done

log() { echo "[$(date '+%H:%M:%S')] $*"; }

if [ "$USE_DOCKER" = true ]; then
    log "Docker Compose 部署..."
    if [ ! -f .env ]; then
        cp .env.example .env
        log "已生成 .env，请编辑并填写 DDW_ACCESS_TOKEN 后重新运行"
        exit 0
    fi
    docker compose -f deepddw-compose.yml up -d --build
    log "deepDDW 已启动: http://localhost:8500/"
    exit 0
fi

# ---- 本地 venv 方式 ----
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"; break
    fi
done
[ -n "$PYTHON" ] || { log "需要 Python 3.11+"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    log "创建虚拟环境..."
    $PYTHON -m venv .venv
fi
. .venv/bin/activate

if ! python -c "import fastapi, mcp" 2>/dev/null; then
    log "安装依赖..."
    pip install -q -r requirements.txt
fi

mkdir -p data logs

if [ "$RUN_TESTS" = true ] && [ -d "tests" ]; then
    log "运行测试..."
    python -m pytest tests/ plugins/ -q --no-header -p no:cacheprovider || log "测试未全绿（仍继续启动，见输出）"
fi

if [ ! -f .env ] && [ -z "${DDW_ACCESS_TOKEN:-}" ]; then
    log "⚠️  未配置 DDW_ACCESS_TOKEN，将使用开发默认 Token（生产环境务必设置）"
fi

log "启动 deepDDW (端口 $PORT)..."
if [ "$BG_MODE" = true ]; then
    nohup python -m uvicorn core.main:app --host 0.0.0.0 --port "$PORT" > logs/deepddw.log 2>&1 &
    echo $! > .deepddw.pid
    sleep 2
    log "后台启动 PID=$(cat .deepddw.pid) 日志 logs/deepddw.log"
else
    python -m uvicorn core.main:app --host 0.0.0.0 --port "$PORT"
fi
