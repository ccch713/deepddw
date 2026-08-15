"""DDW 发票管理插件 v1.0.0（DDW AI Hub — 销售端 CRM P5-2）。

销售端开票申请与发票记录：开票申请（requested）→ 上传发票文件（issued）→ 作废（voided）。
支持专票/普票、价税分离、按企业/订单/状态/类型/开票日期多维筛选、统计概览。
所有数据落 SQLite（async SQLAlchemy 2.0），多租户隔离。
"""

VERSION = "1.0.0"
PLUGIN_NAME = "ddw-invoice"

__all__ = ["PLUGIN_NAME", "VERSION"]
