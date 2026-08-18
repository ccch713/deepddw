# deepDDW 关键决策日志

| 时间 | 决策 | 理由 | 替代方案 |
|---|---|---|---|
| 2026-08-17 R4-0 | 部署模式键用 `deployment.mode`（非顶层 `mode`），避免与现有 `mode: standalone` 冲突 | 复用顶层 mode 会破坏现有配置读取逻辑；独立 deployment 命名空间更清晰 | 顶层 mode 加枚举值扩展（侵入 config.py） |
| 2026-08-17 R4-1 | members/invites 用独立 `_get_conn()`（同步 SQLite，同 knowledge.py 风格） | 复用 knowledge.py 连接池会引入跨模块锁纠缠；members 写入低频可接受新连接 | ORM（重，不符依赖克制）/ 共享连接（锁复杂） |
| 2026-08-17 R4-8 | DSH 设置面板用 cordis 插件包（非 Python API 端点渲染），参考 dshmarket MarketSection | v2.1 定案：不注入 dsh 源码，纯官方 MCP + 插件系统；dshmarket 有现成 section+tabs 注册模式 | FastAPI 端点返回 HTML（污染 dsh 原版）/ 自研 UI 插件（v2.1 已废弃） |
| 2026-08-17 | v0.5.0 删除 Launcher，deepDDW 纯 cordis 插件 | 用户指令：所有 UI 100% 在 DSH 内，零自定义页面/CSS；网关保留 | 独立 launcher + 前端静态页 |
| 2026-08-17 | M4 成员识别 → 新建 POST /device/identify 端点 | M4 弹窗调用 POST /device/identify（与 bind-member 同义），新增端点而非改名 | 仅新增，不改动现有 bind-member |
| 2026-08-17 | 新插件包 ddw-teams-panel 替代 dsh-teams-panel | 新名称体现"deepDDW 多用户"（非 DSH 官方）；删除旧包 | 保留旧包名 |
