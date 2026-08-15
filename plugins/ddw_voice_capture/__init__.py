"""DDW 录音与语音输入插件 v1.0.0（DDW AI Hub — 销售端 CRM P3-1）。

销售端录音与语音输入管理：
- 支持本地/电话/会议/随手记等多源录音元数据记录
- 与企业/联系人/商机建立可选关联，便于后续转写后构建客户档案
- 状态机由本插件维护 + 由 P3-3 转写插件更新
- **本插件不实现语音转写**，仅管理录音文件元数据（file_url + 基础属性）

所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-voice-capture"

__all__ = ["PLUGIN_NAME", "VERSION"]
