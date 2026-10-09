# Agent 桥接 · agent-memory-vault（三机共享记忆库）

本项目的长期记忆、进展与交接不在本仓，在共享记忆库 `~/agent-memory-vault-vault`（三机同路径）。

- 开工：`bash ~/agent-memory-vault-vault/bin/sync.sh pull` → 读 `00-INDEX.md` + `项目/deepddw/00-项目简报.md`、`HANDOFFS.md`（若项目目录不存在，从 `项目/_模板/` 创建并登记 INDEX）
- 本项目 vault 轨道：`项目/deepddw/{10-输入|20-编码|30-测试|40-战略}/`，新文件名 `YYYY-MM-DD-<actor>-<摘要>.md`，frontmatter 带 actor / project_id: deepddw / track
- 热写（线索/拍板/HANDOFF 变更）当场写并立即 `sync.sh close "说明" <actor>`；收工同样 close
- 引用本仓文件写 `仓库名:相对路径`，不写本机绝对路径
- 禁止：密钥入库；Syncthing/rsync 直同步 vault；把记忆写进本代码仓
- 完整协议：库内 AGENTS.md
