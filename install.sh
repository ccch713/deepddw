#!/bin/bash
# deepDDW 0.1 · 一键安装启动脚本
# 用法: bash install.sh [--port 8500] [--no-test] [--bg]
# 适用: macOS 14+ / Ubuntu 22+（Python 3.11+ 或 Docker）
set -euo pipefail

PORT=${DDW_PORT:-8500}
RUN_TESTS=true
BG_MODE=false
USE_DOCKER=false
WITH_DSH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --port) PORT=$2; shift 2;;
        --docker) USE_DOCKER=true; shift;;
        --with-dsh) WITH_DSH=true; shift;;
        --no-test) RUN_TESTS=false; shift;;
        --bg) BG_MODE=true; shift;;
        -h|--help)
            echo "deepDDW 一键安装部署脚本"
            echo "用法: bash install.sh [选项]"
            echo "  --port PORT   服务端口 (默认 8500)"
            echo "  --docker      使用 Docker Compose 部署（推荐全新服务器）"
            echo "  --with-dsh    安装 dsh 工作台插件（@deepddw/dsh-workbench）+ MCP 桥到 dsh web profile"
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

# ---- dsh 工作台插件（v2.0：dsh 原版界面 + deepDDW 插件注入） ----
# 配置 dsh 官方 MCP 桥（deepDDW 知识库/记忆/文档以官方 MCP 标准接入 dsh 原版界面）。
# 需要本机已安装 dsh（npm i -g @deepseek-ai/dsh）。重启 dsh web 后生效。
# v2.1（2026-08-16）：废弃自研 UI 插件方案（污染 dsh 原版），纯官方 MCP 接入。
if [ "$WITH_DSH" = true ]; then
    log "配置 dsh MCP 桥（官方标准接入 deepDDW 工具）..."
    DSH_BIN="$(command -v dsh || true)"
    if [ -z "$DSH_BIN" ]; then
        log "⚠️  未找到 dsh 命令，跳过 MCP 配置（可手动执行 dsh plugin 相关命令）"
    else
        # 1) 确保 mcp-client 包已装进 web profile（patch insert 引用它，不装则静默跳过）
        if ! ls "$HOME/.dsh/profiles/web/node_modules/@deepseek-ai/dsh-mcp-client" >/dev/null 2>&1; then
            (cd "$HOME/.dsh/profiles/web" && pnpm add "@deepseek-ai/dsh-mcp-client@0.1.0-rc.6" >/dev/null 2>&1) \
                && log "mcp-client 包已安装" || log "⚠️  mcp-client 安装失败，MCP 桥可能不生效"
        fi
        # 2) MCP 桥配置追加到 profile patch（deepDDW 5 工具；LAN 免密可直接连）
        PATCH_FILE="$HOME/.dsh/profiles/web/cordis.patch.yml"
        if [ -f "$PATCH_FILE" ] && ! grep -q "mcp-deepddw" "$PATCH_FILE" 2>/dev/null; then
            # 模板默认含空数组行 "[]"（占位）：追加 - insert 前必须删掉，否则 YAML 非法
            if grep -q "^\[\]$" "$PATCH_FILE" 2>/dev/null; then
                sed -i '' '/^\[\]$/d' "$PATCH_FILE"
                log "已清理 patch 模板空数组占位行（避免 YAML 非法）"
            fi
            cat >> "$PATCH_FILE" <<'MCPEOF'
- insert:
    - id: mcp-deepddw
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: deepddw
        transport: streamable-http
        url: http://127.0.0.1:8600/api/v1/mcp
        headers: {}
MCPEOF
            log "MCP 桥已写入 $PATCH_FILE（重启 dsh web 后生效）"
        fi
        log "完成：重启 dsh web（dsh web）后，deepDDW 工具（知识库/记忆/文档）以官方 MCP 出现在 dsh 对话工具列表"
    fi
fi

log "启动 deepDDW (端口 $PORT)..."
# P1-2（multidevice）：可选 TLS——deployment.yaml security.tls.enabled=true 时
# 自动加 ssl 参数（证书由 ./scripts/gen_self_signed_cert.sh 生成）。
UVICORN_SSL_ARGS=""
if python -c "import yaml,sys; c=yaml.safe_load(open('config/deployment.yaml')) if __import__('os').path.exists('config/deployment.yaml') else {}; print('1' if (c.get('security',{}).get('tls',{}) or {}).get('enabled') else '0')" 2>/dev/null | grep -q 1; then
  CERT="$(python -c "import yaml,os; c=yaml.safe_load(open('config/deployment.yaml')); t=(c.get('security',{}).get('tls',{}) or {}); print(t.get('cert_file','./data/tls/cert.pem'))" 2>/dev/null)"
  KEY="$(python -c "import yaml,os; c=yaml.safe_load(open('config/deployment.yaml')); t=(c.get('security',{}).get('tls',{}) or {}); print(t.get('key_file','./data/tls/key.pem'))" 2>/dev/null)"
  if [ -f "$CERT" ] && [ -f "$KEY" ]; then
    UVICORN_SSL_ARGS="--ssl-certfile $CERT --ssl-keyfile $KEY"
    log "TLS 已启用（$CERT）→ https://<host>:$PORT"
  else
    log "警告: security.tls.enabled=true 但证书缺失，请先运行 ./scripts/gen_self_signed_cert.sh"
  fi
fi
if [ "$BG_MODE" = true ]; then
    # shellcheck disable=SC2086  # UVICORN_SSL_ARGS 故意分词
    nohup python -m uvicorn core.main:app --host 0.0.0.0 --port "$PORT" $UVICORN_SSL_ARGS > logs/deepddw.log 2>&1 &
    echo $! > .deepddw.pid
    sleep 2
    log "后台启动 PID=$(cat .deepddw.pid) 日志 logs/deepddw.log"
else
    # shellcheck disable=SC2086
    python -m uvicorn core.main:app --host 0.0.0.0 --port "$PORT" $UVICORN_SSL_ARGS
fi
