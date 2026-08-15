# ⚠️ 已作废（DEPRECATED）

**此插件已被 `ddw_online_cs` 插件取代，不再维护。**

## 替代方案

请使用 `plugins/ddw_online_cs/`（在线客服插件），功能完全覆盖：
- RAG 知识库检索 + MiniMax-M3 LLM 回答
- 全站浮动客服对话框（打字机效果、表情包、上下文感知）
- 附件上传（图片/PDF/邮件）+ LLM 提炼
- 售前/售后双模式（自动识别）
- 投诉/建议自动记录（产品迭代来源）

## 作废原因

- 连字符目录名（customer-service）与平台加载器不兼容（`importlib.import_module` 无法导入含连字符的模块名）
- 缺少 plugin.py 入口文件，启动时被跳过
- 依赖 `sdk.plugin_base`（PluginBase 协议）而非平台标准 `plugin.py + Plugin 类` 协议

---

*标记于 2026-08-04*
