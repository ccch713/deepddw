#!/bin/bash
# DDW AI Hub · 一键安装部署脚本
# 用法: bash install.sh [--port 8500] [--no-test] [--bg]
# 适用: macOS 14+ / Ubuntu 22+
# 设计: 客户现场 FDE 一条命令完成全部部署
set -euo pipefail

# ====================================================================
# 参数解析
# ====================================================================
PORT=${DDW_PORT:-8500}
RUN_TESTS=true
BG_MODE=false
SKIP_DEPS=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --port) PORT=$2; shift 2;;
        --no-test) RUN_TESTS=false; shift;;
        --bg) BG_MODE=true; shift;;
        --skip-deps) SKIP_DEPS=true; shift;;
        -h|--help)
            echo "DDW AI Hub 一键安装部署脚本"
            echo "用法: bash install.sh [选项]"
            echo "选项:"
            echo "  --port PORT     服务端口 (默认 8500)"
            echo "  --no-test       跳过测试"
            echo "  --bg            后台运行"
            echo "  --skip-deps     跳过依赖安装"
            echo "  -h, --help      显示帮助"
            exit 0;;
        *) echo "未知参数: $1"; exit 1;;
    esac
done

# ====================================================================
# 工具函数
# ====================================================================
log()   { echo "[$(date '+%H:%M:%S')] $*"; }
ok()    { echo "[$(date '+%H:%M:%S')] ✅ $*"; }
warn()  { echo "[$(date '+%H:%M:%S')] ⚠️  $*"; }
fail()  { echo "[$(date '+%H:%M:%S')] ❌ $*"; exit 1; }

# ====================================================================
# Step 1: 检测 Python
# ====================================================================
log "Step 1/7: 检测 Python 环境..."
PYTHON=""
PY_VER=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        VER=$($candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        if [ -n "$VER" ]; then
            MAJOR=$(echo "$VER" | cut -d. -f1)
            MINOR=$(echo "$VER" | cut -d. -f2)
            if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
                PYTHON="$candidate"
                PY_VER="$VER"
                break
            fi
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    fail "Python 3.11+ 未安装。请先安装: brew install python@3.12 (macOS) 或 apt install python3.12 (Ubuntu)"
fi
ok "Python $PY_VER ($PYTHON)"

# ====================================================================
# Step 2: 创建虚拟环境
# ====================================================================
log "Step 2/7: 创建虚拟环境..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    $PYTHON -m venv .venv
    ok "虚拟环境已创建"
else
    ok "虚拟环境已存在"
fi
. .venv/bin/activate

# ====================================================================
# Step 3: 安装依赖
# ====================================================================
log "Step 3/7: 安装依赖..."
if [ "$SKIP_DEPS" = true ]; then
    warn "跳过依赖安装 (--skip-deps)"
elif python -c "import fastapi" 2>/dev/null; then
    ok "依赖已就位"
else
    # 基础依赖
    pip install -q -r requirements.txt 2>&1 | tail -3
    # 额外依赖（部分包不在 requirements.txt 中）
    pip install -q greenlet cryptography aiofiles jinja2 redis openai alembic 2>/dev/null || true
    ok "依赖安装完成"
fi

# ====================================================================
# Step 4: 创建目录
# ====================================================================
log "Step 4/7: 创建数据目录..."
mkdir -p data logs
ok "目录就位 (data/ logs/)"

# ====================================================================
# Step 5: 运行测试（可选）
# ====================================================================
if [ "$RUN_TESTS" = true ] && [ -d "tests" ]; then
    log "Step 5/7: 运行测试..."
    if python -m pytest tests/ -q --no-header -p no:cacheprovider 2>&1 | tail -3; then
        ok "测试通过"
    else
        warn "测试失败但仍继续启动"
    fi
else
    log "Step 5/7: 跳过测试"
fi

# ====================================================================
# Step 6: 显示启动信息
# ====================================================================
log "Step 6/7: 准备启动..."
PLUGIN_COUNT=$(find plugins -name "manifest.yaml" -not -path "*/_template/*" 2>/dev/null | wc -l | tr -d ' ')
echo ""
echo "=========================================="
echo "  DDW AI Hub · 一键部署完成"
echo "=========================================="
echo "  端口:     http://localhost:$PORT"
echo "  API文档:  http://localhost:$PORT/docs"
echo "  插件数:   $PLUGIN_COUNT"
echo "  数据目录: $SCRIPT_DIR/data/"
echo "  日志目录: $SCRIPT_DIR/logs/"
echo "  Python:   $PY_VER (venv)"
echo "=========================================="
echo ""

# ====================================================================
# Step 7: 启动服务
# ====================================================================
log "Step 7/7: 启动 DDW AI Hub..."

if [ "$BG_MODE" = true ]; then
    nohup python -m uvicorn core.main:app --host 0.0.0.0 --port "$PORT" > logs/ddw.log 2>&1 &
    echo $! > .ddw.pid
    sleep 3
    if ps -p "$(cat .ddw.pid)" > /dev/null 2>&1; then
        PLUGINS_LOADED=$(grep -c "loaded plugin" logs/ddw.log 2>/dev/null || echo "0")
        echo ""
        echo "=========================================="
        echo "  🚀 DDW AI Hub 已启动 (后台)"
        echo "  PID:      $(cat .ddw.pid)"
        echo "  插件加载: $PLUGINS_LOADED"
        echo "  日志:     tail -f logs/ddw.log"
        echo "  停止:     kill \$(cat .ddw.pid)"
        echo "=========================================="
    else
        fail "启动失败，查看 logs/ddw.log"
    fi
else
    echo "按 Ctrl+C 停止服务"
    echo ""
    python -m uvicorn core.main:app --host 0.0.0.0 --port "$PORT"
fi
