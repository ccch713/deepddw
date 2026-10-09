"""deepDDW 组织连接插件（bindcode-v1 协议服务端实现）。

让本 deepDDW 实例作为「组织后端」被 DDW AI 助手系列 App 绑定连接：

- 公网三件（产品令牌 + 限速）：bind / unbind / me；
- 成员级 access_token 直连本实例 LLM 端点（OpenAI 兼容 chat/completions，
  供给走部署者自配的 llm_gateway 供应商，与任何官方渠道无关）；
- 管理端（静态 Token 门禁）：建组织 / 签码 / 轮换密钥 / 解绑 / 用量对账。

协议规范：docs/组织连接协议-bindcode-v1.md（本仓 docs/ 随附副本）。
默认关闭，config/deployment.yaml 的 ``org_relay.enabled: true`` 或
``DDW_ORG_RELAY_ENABLED=1`` 开启。
"""

VERSION = "0.1.0"
PLUGIN_NAME = "ddw-org-relay"

__all__ = ["PLUGIN_NAME", "VERSION"]
