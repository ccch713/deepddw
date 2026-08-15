"""DDW Aggregated Pay Plugin.

================================================================================
⛔ DEPRECATED — 2026-08-12 — 已终止维护

本插件是早期聚合支付/对账原型，2026-08-12 由用户拍板终止，原因：
  - sqlite3 直连跨 db 读 ddw_offline_pos（生产部署一旦分容器即失效）
  - 仅字典存 channel 配置，无真实 SDK 接入
  - 与 ddw_wallet（在线支付中台）功能重叠

【替代方案】
  在线支付中台 → ddw_wallet（问渠 K12）
  线下前台收银 → ddw_offline_pos（原 ddw_payment，2026-08-12 改名）

【历史】
  最早 2026-08-12 由 Gitea 主仓 chenye/ddw-ai-hub-workspace 同步终止

DO NOT USE — 任何新插件请基于 ddw_wallet 构建，不要继承本插件代码。
================================================================================
PLUGIN_NAME = "ddw_aggregated_pay"
VERSION = "0.1.0"

STATUS = "deprecated"  # 2026-08-12: 主仓同步终止

def __getattr__(name):
    raise RuntimeError("ddw_aggregated_pay 已于 2026-08-12 终止。请改用 ddw_wallet 或 ddw_offline_pos。")
