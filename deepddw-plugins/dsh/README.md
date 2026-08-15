# @deepddw/dsh-workbench

deepDDW 工作台插件（DSH 官方插件机制，cordis 插件包）。

在 **dsh 原版界面**（100% 原样，不改 dsh 源码/bundle）上，通过官方 slots
注入 deepDDW 能力：

| Slot | 注入内容 |
|---|---|
| `settings.section` ×3 | 设置页左侧新增子项：📚 知识库 / 🧠 记忆 / 🤖 模型配置 |
| `conversation.session.header.utilities` | 右上角 📄 按钮 → 可隐藏的右侧文档栏（320px） |

## 安装

```bash
# 1. 在 deepDDW 仓内（本插件包目录）
dsh plugin --profile web add /absolute/path/to/deepddw-plugins/dsh

# 2. （可选）配置 deepDDW 网关地址：环境变量
export DEEPDDW_BASE_URL=http://127.0.0.1:8600

# 3. 重启 dsh（bundle 层变化需重启生效）
dsh web
```

> 也可以直接 `dsh plugin --profile web add ./deepddw-plugins/dsh`（在 deepDDW 仓根执行）。

## 配置（cordis 层，可选）

在 profile 层（`~/.dsh/profiles/web/cordis.yml` 或插件 bundle 的 patch 层）为
`deepddw-workbench` 提供 config：

```yaml
- id: deepddw-workbench
  name: '@deepddw/dsh-workbench'
  config:
    deepddw:
      baseUrl: http://127.0.0.1:8600
```

未配置时回退：`DEEPDDW_BASE_URL` 环境变量 → 默认 `http://127.0.0.1:8600`。

## MCP 接入（dsh 原生 MCP 客户端 → deepDDW 网关）

在 profile 层 `cordis.yml` 追加一条 MCP 服务器（deepDDW 5 工具：
`ddw.llm.chat` / `ddw.kb.search` / `ddw.memory.put` / `ddw.memory.search` /
`ddw.docs_portal.search`）：

```yaml
- id: mcp-deepddw
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: deepddw
    transport: streamable-http
    url: http://127.0.0.1:8600/api/v1/mcp
    headers:
      X-DDW-Token: !!js 'process.env.DDW_ACCESS_TOKEN || ""'
```

> LAN 免密模式（默认开）下可不带 Token 头；外网部署时用 `DDW_ACCESS_TOKEN`
> 环境变量提供 Token，插件/进程内不落明文。

工具以 `mcp__deepddw__ddw.kb.search` 等名称出现在模型中。

## 卸载

```bash
dsh plugin --profile web remove @deepddw/dsh-workbench
# 移除后 dsh 恢复原版（插件机制干净，不留残留）
```

## 安全红线遵守

- 不改 dsh 源码/bundle、不重写界面、不破坏原版 LLM 设置；
- key 只写不读明文（`/api/v1/llm/config` GET 只回布尔；输入框 password 型）；
- token 不写 URL / iframe src / 日志（postMessage + sessionStorage 传递）；
- 401 时提示"未授权：外网访问需通过启动页填写 Token"并引导回启动页。
