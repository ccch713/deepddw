# ⛔ ddw_aggregated_pay — 已终止（2026-08-12）

## 终止原因

| # | 问题 | 后果 |
|---|---|---|
| 1 | sqlite3 直连 `../ddw_offline_pos/data/offline_pos.db` 跨 db 读 | 插件分容器部署即失效 |
| 2 | 渠道配置只存 dict 无 SDK | 无法真实发起支付 |
| 3 | 与 ddw_wallet 功能重叠 | 维护成本翻倍 |

## 迁移去向

- 在线支付中台 → **ddw_wallet**（已生产，问渠 K12 用）
- 线下前台收银 → **ddw_offline_pos**（原 ddw_payment，2026-08-12 改名）

## 历史
- 2026-08-12 主仓 chenye/ddw-ai-hub-workspace 与 dev 副本 chenye/ddw-ai-hub-dev-archived 同步终止
- ZCode/Agent 任务**永久禁止**再以此插件为研究对象

## 决策者

陈先生 — 2026-08-12 拍板终止
