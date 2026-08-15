"""DDW 投标标书撰写插件 v1.0.0（DDW AI Hub — 设计院插件群 D3）。

投标项目全流程：项目建档 → 标书生成 → 标书风格修饰 → 标书审查 → 标书批准 → 模板管理。
所有数据落 SQLite（async SQLAlchemy 2.0）。

注意：本插件对"标书风格修饰"功能做脱敏处理（详见 manifest）。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-bid-writer"

__all__ = ["VERSION", "PLUGIN_NAME"]
