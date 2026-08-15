"""DDW 电子签章适配器插件 v1.0.0（DDW AI Hub — 销售端 CRM P5-1）。

电子签章服务适配层：对接腾讯电子签 / 契约锁 / e签宝 等第三方电子签章服务商。
- 仅负责数据落库与状态机管理（pending / signing / signed / rejected / expired）
- 第三方 API 集成通过适配器模式（SignatureAdapter）预留扩展点
  （本版本不真正实现第三方 HTTP 调用）
- 第三方异步回调：POST /signature-requests/{id}/callback
- 人工上传签后文件：POST /signature-requests/{id}/manual-upload

所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-signature-adapter"

__all__ = ["PLUGIN_NAME", "VERSION"]
