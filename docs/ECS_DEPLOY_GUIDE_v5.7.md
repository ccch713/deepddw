# DDW AI Hub ECS 部署指南 v5.7

> 面向 DDW 开发者的 ECS 生产部署完整手册
> 最后更新: 2026-07-13

---

## 目录

1. [架构概览](#1-架构概览)
2. [前置条件](#2-前置条件)
3. [快速部署](#3-快速部署)
4. [分步部署详解](#4-分步部署详解)
5. [部署脚本说明](#5-部署脚本说明)
6. [PostgreSQL 配置](#6-postgresql-配置)
7. [Caddy 反向代理](#7-caddy-反向代理)
8. [systemd 服务管理](#8-systemd-服务管理)
9. [监控与健康检查](#9-监控与健康检查)
10. [故障排查](#10-故障排查)
11. [安全加固](#11-安全加固)
12. [回滚方案](#12-回滚方案)
13. [附录: 已知 Pitfall](#13-附录-已知-pitfall)

---

## 1. 架构概览

```
用户浏览器
    ↓
Caddy (Docker) ← 80/443 入口，按域名/路径路由
    ↓
DDW Core (systemd) ← 0.0.0.0:8500，uvicorn
    ├── core/           ← FastAPI 主应用
    ├── plugins/        ← 已安装插件
    ├── core/marketplace/ ← 插件市场模块
    └── frontend/       ← 静态前端文件
    ↓
PostgreSQL (Docker) ← oral-clinic-postgres:5433
```

### ECS 服务器信息

| 项目 | 值 |
|------|-----|
| 主机 | 8.145.35.164 |
| 用户 | root |
| OS | Ubuntu 20.04 LTS |
| Python | 3.11 (venv: /opt/ddw/venv311/) |
| 部署目录 | /opt/ddw/ddw-ai-hub |
| 服务名 | ddw-core |
| 端口 | 8500 |
| 数据库 | PostgreSQL (oral-clinic-postgres:5433) |

---

## 2. 前置条件

### 本地环境

- macOS/Linux 开发机
- `ssh` + `rsync` 已安装
- SSH 密钥已配置到 ECS（`~/.ssh/config` 中有 `ruiguo` 或直接 IP）

### ECS 环境

- Python 3.11+ 虚拟环境: `/opt/ddw/venv311/`
- systemd 服务: `ddw-core.service`
- Docker: Caddy + PostgreSQL 容器
- `.env` 配置文件: `/opt/ddw/.env`

### 检查命令

```bash
# 运行部署前检查
bash scripts/ecs_preflight_check.sh

# 查看输出
# ✓ 通过  ⚠ 警告  ✗ 失败
```

---

## 3. 快速部署

```bash
# 一键部署 (全量)
bash scripts/deploy_to_ecs.sh

# 仅部署指定插件
bash scripts/deploy_to_ecs.sh --only ddw_token_manager

# 试运行 (不实际修改)
bash scripts/deploy_to_ecs.sh --dry-run

# 部署后手动检查
bash scripts/ecs_postdeploy_healthcheck.sh
```

---

## 4. 分步部署详解

### 4.1 同步 DDW 主应用代码

```bash
# 核心代码 (注意: 排除 deployment.yaml!)
rsync -az --delete \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    cloud-llm/ddw-ai-hub/core/ \
    root@8.145.35.164:/opt/ddw/ddw-ai-hub/core/

# 配置文件 (排除 deployment.yaml — ECS 上是 PG 版)
rsync -az --exclude='deployment.yaml' \
    cloud-llm/ddw-ai-hub/config/ \
    root@8.145.35.164:/opt/ddw/ddw-ai-hub/config/
```

> ⚠️ **不要**直接 rsync 本地 `deployment.yaml` 到 ECS — 会覆盖 PG 配置!

### 4.2 同步插件

```bash
# 同步所有插件
rsync -az --delete \
    --exclude='__pycache__' \
    cloud-llm/ddw-ai-hub/plugins/ \
    root@8.145.35.164:/opt/ddw/ddw-ai-hub/plugins/

# 同步单个插件
rsync -az --delete \
    cloud-llm/ddw-ai-hub/plugins/ddw_token_manager/ \
    root@8.145.35.164:/opt/ddw/ddw-ai-hub/plugins/ddw_token_manager/
```

### 4.3 同步前端

```bash
rsync -az --delete \
    cloud-llm/ddw-ai-hub/frontend/ \
    root@8.145.35.164:/opt/ddw/ddw-ai-hub/frontend/
```

### 4.4 清理缓存 + 重启

```bash
# 清理 __pycache__
ssh root@8.145.35.164 \
    "find /opt/ddw/ddw-ai-hub -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null"

# 重启服务
ssh root@8.145.35.164 "systemctl restart ddw-core && sleep 3 && systemctl is-active ddw-core"
```

### 4.5 验证

```bash
# 健康检查
curl -s http://8.145.35.164/api/ddw/api/v1/admin/system/health

# 前端页面
curl -s -o /dev/null -w '%{http_code}' http://8.145.35.164/api/ddw/index.html

# 插件市场
curl -s -o /dev/null -w '%{http_code}' http://8.145.35.164/api/ddw/plugin-market.html
```

---

## 5. 部署脚本说明

### ecs_preflight_check.sh — 部署前环境检查

检查 6 大维度:
1. **本地环境**: rsync/ssh 是否可用, 源码目录是否存在
2. **ECS 连通性**: ping/SSH 端口/认证
3. **ECS 远端环境**: Python venv, systemd 服务, Docker 容器
4. **ECS 资源**: 磁盘空间, 可用内存
5. **部署一致性**: 本地 vs 远端文件数对比
6. **安全检查**: .env 占位符, ufw, SSH 配置, CrowdSec

```bash
bash scripts/ecs_preflight_check.sh
# 输出: ✓ 通过  ⚠ 警告  ✗ 失败
# 退出码 = 失败项数量
```

### deploy_to_ecs.sh — 一键部署

7 步部署流程:
1. 前置检查 (SSH, 目录)
2. 同步 core/ (排除 deployment.yaml)
3. 同步 plugins/
4. 同步 frontend/
5. 同步 marketplace/ (随 core/)
6. 清理缓存 + 验证文件
7. 重启服务 + 健康检查

选项:
- `--dry-run`: 仅显示操作，不实际执行
- `--skip-health`: 跳过部署后健康检查
- `--only NAME`: 仅部署指定插件

### ecs_postdeploy_healthcheck.sh — 部署后健康检查

检查 7 大维度:
1. **systemd 服务**: 运行状态, 自启配置, 进程信息
2. **端口监听**: 8500 端口
3. **HTTP 健康端点**: /api/v1/admin/system/health
4. **前端页面**: index.html, login.html, plugin-market.html
5. **插件健康**: 各插件 /api/v1/plugins/{name}/health
6. **基础设施**: PostgreSQL, Caddy, 磁盘, 内存
7. **日志**: 最近 10 分钟错误

```bash
bash scripts/ecs_postdeploy_healthcheck.sh
bash scripts/ecs_postdeploy_healthcheck.sh --json  # JSON 输出
bash scripts/ecs_postdeploy_healthcheck.sh --wait 30  # 等待 30s 再检查
```

---

## 6. PostgreSQL 配置

### 连接信息

```
主机: 127.0.0.1:5433 (或 Docker 内 172.17.0.2:5432)
用户: oral_clinic
数据库: ddw
```

### ECS 8GB 推荐配置

```yaml
max_connections: 100
shared_buffers: 512MB        # ⚠️ 不要超过 512MB!
effective_cache_size: 2GB    # ⚠️ 不要超过 2GB!
work_mem: 16MB
maintenance_work_mem: 256MB
wal_buffers: 16MB
```

> ⚠️ **铁律**: `shared_buffers + effective_cache_size` 不超过 ECS 总内存的 50%

### 常见问题

- **PG 端口映射丢失**: `docker restart oral-clinic-postgres`
- **shared_buffers 超配**: 见 `ecs-pg-overprovisioning-fix` skill
- **密码重置**: `docker exec oral-clinic-postgres psql -U oral_clinic -c "ALTER USER oral_clinic WITH PASSWORD 'new_pass';"`

---

## 7. Caddy 反向代理

### 容器启动

```bash
# 使用 host 网络模式 (直接访问 localhost:8500)
docker run -d --name caddy --restart unless-stopped --network host \
    -v /root/ecs-framework/caddy/Caddyfile:/etc/caddy/Caddyfile \
    -v caddy_data:/data \
    -v caddy_config:/config \
    caddy:2-alpine
```

### Caddyfile 模板

```caddy
:80 {
    @ddw host ddw.9cio.com
    handle @ddw {
        reverse_proxy 172.19.0.1:8500   # Docker 网桥模式
        # 或 reverse_proxy localhost:8500  # host 网络模式
    }

    handle_path /api/ddw/* {
        reverse_proxy 172.19.0.1:8500
    }
}
```

### 重启 Caddy

```bash
cd /root/ecs-framework/caddy && docker compose down caddy && docker compose up -d caddy
```

> ❌ 不要用 `docker restart caddy` (不重读配置)

---

## 8. systemd 服务管理

### 服务文件

`/etc/systemd/system/ddw-core.service`:

```ini
[Unit]
Description=DDW AI Hub Core
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ddw/ddw-ai-hub
EnvironmentFile=/opt/ddw/.env
Environment=PATH=/usr/local/bin:/usr/bin:/bin:/root/.local/bin
ExecStart=/opt/ddw/venv311/bin/python -m uvicorn core.main:app --host 0.0.0.0 --port 8500
Restart=always
RestartSec=5
SyslogIdentifier=ddw-core

[Install]
WantedBy=multi-user.target
```

### 常用命令

```bash
systemctl status ddw-core       # 查看状态
systemctl restart ddw-core      # 重启
systemctl stop ddw-core         # 停止
systemctl enable ddw-core       # 开机自启
journalctl -u ddw-core -f       # 实时日志
journalctl -u ddw-core --since '10 min ago'  # 最近日志
```

---

## 9. 监控与健康检查

### 手动检查

```bash
# 健康端点
curl -s http://8.145.35.164/api/ddw/api/v1/admin/system/health

# 插件健康
curl -s http://8.145.35.164:8500/api/v1/plugins/ddw_token_manager/health

# 前端可访问性
curl -s -o /dev/null -w '%{http_code}' http://8.145.35.164/api/ddw/index.html
```

### 自动化检查

```bash
# 使用部署后检查脚本
bash scripts/ecs_postdeploy_healthcheck.sh

# JSON 输出 (可被 AI 消费)
bash scripts/ecs_postdeploy_healthcheck.sh --json
```

### 监控栈 (可选)

ECS 上可部署 Prometheus + Grafana:
- Prometheus: 256MB 内存
- Grafana: 256MB 内存
- cAdvisor: 容器级监控
- Node Exporter: 主机级监控

---

## 10. 故障排查

### 服务启动失败

```bash
# 查看错误日志
journalctl -u ddw-core --no-pager -n 30

# 常见原因:
# 1. Python 版本不对 → 检查 ExecStart 路径
# 2. 缺少依赖 → source /opt/ddw/venv311/bin/activate && pip install -r requirements.txt
# 3. .env 缺失 → 检查 /opt/ddw/.env
# 4. 端口被占 → ss -tlnp | grep :8500
```

### 502 Bad Gateway

```bash
# 检查 Caddy 日志
docker logs caddy --tail 20

# 常见原因:
# 1. DDW 服务未运行 → systemctl status ddw-core
# 2. Caddy 指向错误 IP → 检查 Caddyfile 中的 reverse_proxy 地址
# 3. iptables 阻断 → iptables -L INPUT -n | head -20
```

### SSH 连接失败 (CrowdSec 封禁)

```bash
# 诊断
nc -z -w 5 8.145.35.164 22  # 返回非0 = 被封

# 修复
# 1. 等 4 小时自动解封
# 2. 阿里云 Workbench → cscli decisions delete --ip <你的IP>
# 3. 从 16G Mac mini 中转 (IP 不同)
```

### 数据库连接失败

```bash
# 检查 PG 容器
docker ps | grep postgres
docker exec oral-clinic-postgres pg_isready

# 端口映射
docker exec oral-clinic-postgres ss -tlnp | grep 5432
```

---

## 11. 安全加固

### 最低标准

| 措施 | 命令 |
|------|------|
| SSH 密钥认证 | `/etc/ssh/sshd_config: PasswordAuthentication no` |
| 防火墙 | `ufw allow from 172.0.0.0/8 to any port 8500 proto tcp` |
| CrowdSec | `systemctl status crowdsec` |
| .env 保护 | `chmod 600 /opt/ddw/.env` |

### CrowdSec

```bash
cscli decisions list          # 查看封禁
cscli metrics                 # 查看指标
cscli decisions delete --ip X # 解封
```

### 部署安全门禁

部署前必须通过 `ecs-deploy-security-gate` skill 的安全检查:
- 不在对话中暴露 API Key / 密码
- .env 不提交到 Git
- 部署前检查占位符密码

---

## 12. 回滚方案

### 代码回滚

```bash
# 如果新代码有问题，从 Git 恢复
ssh root@8.145.35.164 "cd /opt/ddw/ddw-ai-hub && git checkout HEAD~1"
ssh root@8.145.35.164 "systemctl restart ddw-core"
```

### 配置回滚

```bash
# 恢复 .env 备份
ssh root@8.145.35.164 "cp /opt/ddw/.env.bak /opt/ddw/.env"
ssh root@8.145.35.164 "systemctl restart ddw-core"
```

### 数据库回滚

```bash
# 从备份恢复 (如果有)
docker exec oral-clinic-postgres pg_restore -U oral_clinic -d ddw /backup/ddw.dump
```

---

## 13. 附录: 已知 Pitfall

1. **不要 rsync deployment.yaml** — 本地是 SQLite 版，ECS 是 PG 版
2. **Caddy 内 127.0.0.1 ≠ 宿主机** — 必须用 Docker 网桥 IP 或 host 网络模式
3. **PG shared_buffers > 512MB 会 OOM** — ECS 8GB 铁律
4. **Python 3.8 不支持新语法** — ECS 已升级到 3.11 (venv311)
5. **CrowdSec 会封 SSH** — 连接失败 2 次后等 5 分钟
6. **systemd EnvironmentFile 不展开变量** — .env 中不要用 `$VAR`
7. **docker restart 不重读配置** — Caddy 改配置后必须 down + up
8. **__pycache__ 导致旧代码残留** — 部署后清理

---

## 授权机制部署配置（P0-P3 必读）

> 授权体系全部采用 **fail-closed**：未配置关键密钥/环境变量时，商业插件不会加载、
> 换码广播保护不生效（有明确告警日志）。以下配置项缺一不可。

### 1. 必需环境变量（写入 `/opt/ddw/.env`，`chmod 600`）

| 变量 | 用途 | 获取方式 |
|:--|:--|:--|
| `DDW_ENV=production` | 许可证 fail-closed 门控。**未设置时**：若存在 license 文件会自动按生产语义处理（fail-closed）；开发/演示环境请显式设 `DDW_ENV=development` | 直接写入 |
| `DDW_LICENSE_PUBLIC_KEY` | 客户端验签公钥（base64）。**不配置则无法验签任何 license（明确报错）** | `scripts/gen_license_keys.py` 生成后取 base64 公钥 |
| `DDW_LICENSE_STATE_KEY` | 换码广播状态文件（license_state.json）HMAC 完整性密钥。**不配置则防篡改保护禁用（告警）** | 任意长随机串，如 `openssl rand -hex 32` |
| `DDW_PLUGIN_SIGNING_PUBLIC_KEY` | .ddwplugin 插件包验签公钥（base64）。不配置则安装签名包被拒 | 与 license 公钥同一密钥对或独立密钥对 |

### 2. 密钥文件（发证端持有，严禁进入 Git/客户端）

- 私钥：`scripts/gen_license_keys.py --output-dir ./license_keys` 生成
  （`license_signing_private_key.pem`，chmod 600，已被 .gitignore 忽略）
- 发证：`scripts/issue_license.py --private-key … --license-key … --customer … --instance-id … --machine-fingerprint …`
- 机器指纹采集（目标机执行）：
  `python -c "from core.utils.machine_fingerprint import get_machine_fingerprint; print(get_machine_fingerprint())"`

### 3. Docker 部署：宿主 machine-id 挂载（跨机克隆检测）

同镜像的所有容器 `/etc/machine-id` 相同（镜像层），仅靠它无法区分复制克隆的容器。
**Docker 部署必须挂载宿主 machine-id**，否则指纹降级为容器 ID 并打告警：

```bash
docker run -v /etc/machine-id:/hostfs/etc/machine-id:ro \
  -v /var/lib/dbus/machine-id:/hostfs/var/lib/dbus/machine-id:ro \
  -e DDW_ENV=production -e DDW_LICENSE_PUBLIC_KEY=... \
  -e DDW_LICENSE_STATE_KEY=... ddw-ai-hub:latest
```

### 4. license 文件落位

- `license_cache.json` 与 `license_state.json` 位于配置的 `license.cache_path` 目录
  （默认 `./data/`，与 deployment.yaml `license.cache_path` 同源）
- 换码流程：新码文件替换 `license_cache.json` → 系统检测到 license_key 变化 →
  旧码自动进入 7 天倒计时（grace_ends_at=+7 天）→ 数据同步拦截按状态放行/拒绝

### 5. 跨机授权广播 Broker（P4，多节点/双网卡部署必读）

> 适用：企业内多个 DDW 节点（主系统 + 复制容器 + 边缘节点）。换码广播需要从
> 权威节点传播到所有节点，且授权校验走独立网络通道（双网卡隔离）。

**网络拓扑**：
```
授权权威节点（主系统，持有 license_state.json）
   └─ 授权网卡地址可配：license.broker.url（如 http://10.0.1.10:8500）
         │ 内网（授权网段）
   ┌─────┴──────┬──────────┐
业务节点A    克隆容器C2   边缘节点N
（懒拉取权威 state，TTL 内离线可用）
```

**权威节点（主系统）配置**（`deployment.yaml`）：
```yaml
license:
  broker:
    enabled: true          # 暴露 GET /api/v1/license/broker/state
    token: ${DDW_LICENSE_BROKER_TOKEN}
    ttl_seconds: 300
```

**业务节点配置**（复制容器/边缘节点）：
```yaml
license:
  broker:
    enabled: true
    url: http://<授权节点IP>:8500   # 双网卡：指向授权网卡地址
    token: ${DDW_LICENSE_BROKER_TOKEN}
    ttl_seconds: 300
```

**令牌与安全**：
- 令牌 `DDW_LICENSE_BROKER_TOKEN`（env，`openssl rand -hex 32` 生成）与 license
  公钥同批分发；请求头 `X-DDW-Broker-Token` + 时间戳 `X-DDW-Broker-Ts` +
  HMAC 签名 `X-DDW-Broker-Sig`（±300s 防重放）
- 业务节点在 `/api/v1/license/info` 被调用时懒拉取权威 state 覆盖本机
  （TTL 内不重复拉取）；**Broker 不可达时回退本地缓存**（断网容错）
- 跨公网部署请在反向代理上启用 TLS（代码不内置）

**双网卡说明**：`license.broker.url` 指向授权网卡地址即可实现授权校验与业务
流量走不同网段；无需额外代码。

---

## 关联文件

- ECS 服务文件: `/etc/systemd/system/ddw-core.service`
- ECS 环境变量: `/opt/ddw/.env`
- ECS 部署配置: `/opt/ddw/ddw-ai-hub/config/deployment.yaml` (PG 版)
- Caddy 配置: `/root/ecs-framework/caddy/Caddyfile`
- 本地部署配置: `config/deployment.yaml` (SQLite 版)
- 插件开发约定: `references/plugin-conventions.md`
- 部署操作手册 skill: `ddw-deployment`
- ECS 统一框架 skill: `ecs-unified-framework`
- PG 超配修复 skill: `ecs-pg-overprovisioning-fix`
