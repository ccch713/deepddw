# CHANGELOG

## 2026-08-07 安全加固（ECS + 32G 隧道链路）

- [P1] 公网 Gateway 入口裸奔修复：`/gateway/*`（ddw.9cio.com）与 `/AH/*`（www.9cio.com）增加 Caddy basic_auth（用户 ddw），封死 `api/token` 无凭据发放漏洞。验证：无凭据 401 / 带凭据 200。备份：`/root/ecs-framework/caddy/Caddyfile.bak-gateway-auth`
- [P2] 32G `com.hermes.gitea-tunnel` launchd 进程风暴修复：plist 含 `-f` + KeepAlive 导致 1412 个 ssh 进程堆积，删除 `-f`、增加 ExitOnForwardFailure/ServerAliveInterval/ThrottleInterval 后收敛为 1 个进程
- [P3] 32G CouchDB 绑定收紧：`bind_address 0.0.0.0 → 127.0.0.1`（ECS 隧道走 localhost 不受影响）
- 审计基线：iptables policy DROP + geo-IP + UFW deny + CrowdSec + fail2ban 四层防护在位；公网暴露面仅 80/443/22(117段)/RustDesk(117+111段)；近 30 天 SSH 爆破 0 次

详细记录见 Obsidian：`_01_项目/03_项目/Hermes运维/2026-08-07-ECS安全审计与修复.md`

## 2026-08-07 新增：32G Hermes WebUI 公网入口

- `https://webui.ddw.9cio.com` 上线：32G Hermes WebUI(8787) 经 SSH 隧道 8903（launchd `com.hermes.webui-tunnel`）+ ECS Caddy basic_auth（与 gateway 同账号）
- iptables 新增规则：80/443 全球放行（geo-IP DROP 之前，Let's Encrypt 海外验证需要），已持久化 rules.v4
- 端到端验证：无凭据 401 / 带凭据 302→登录页 / 证书 LE 有效
- [FIX] webui.ddw.9cio.com 空白页：reverse_proxy 缺 `flush_interval -1` 导致 SSE 被缓冲截断，已修复（用户实测通过）
- [2026-08-10] 登录滑块验证：图片验证码换 AJ-Captcha 风格拼图滑块（Pillow 自研，零依赖）。修复多租户 409 死循环（slider_token 登录成功后才 revoke）；密码显示/隐藏图标；多租户弹窗改独立模态框。ECS Caddy 补 /ui/* handle 防 SPA fallback。测试 86 passed。
- [2026-08-10] 滑块验证 v2：拼图块白边/拖拽联动/防卡顿/y轴对齐/中心偏移（commit a937678，浏览器实测登录成功）
