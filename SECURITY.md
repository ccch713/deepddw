# Security Policy & Third-Party Plugin Disclaimer

> Last updated: 2026-08-16
> Language: 中文 / English

---

## 一、插件安全声明（Plugin Security Disclaimer）

### 中文

deepDDW 集成了 **DeepSeek Harness（DSH）官方插件机制**——用户可通过 DSH 官方命令
（`dsh plugin --profile web add <npm-package>`）从 **npm 官方仓库**安装插件，
这也是我们推荐的唯一插件获取渠道，以最大程度避免供应链投毒风险。

**郑重声明**：

1. **非 deepDDW 插件（第三方插件）的安全责任在用户**：任何非 deepDDW 官方发布的插件，
   包括但不限于 DSH 生态插件、社区插件、自行编写的插件，其代码安全性、数据安全性、
   均由用户自行查验与承担。因第三方插件引发的数据泄露、系统损坏或其他事故，
   **与 deepDDW 无关**，deepDDW 不承担任何责任。

2. **deepDDW 官方保障范围**：deepDDW 仅对**记忆体（Memory）与知识库（Knowledge Base）
   的代码完整性与安全性**提供保障。deepDDW 承诺：

   - **不窃取**用户数据
   - **不利用**用户数据
   - **不贩卖**用户数据
   - 数据默认全部存储在用户自己的设备/服务器上，不出内网

3. **建议**：安装任何插件前，请查验其来源、许可证与维护状态；生产环境建议使用
   DSH 官方发布的插件。

### English

deepDDW integrates the **official DeepSeek Harness (DSH) plugin mechanism** —
users can install plugins from the **official npm registry** via the DSH official
command (`dsh plugin --profile web add <npm-package>`). This is the only channel
we recommend for adding plugins, to minimize supply-chain poisoning risk.

**Important notices**:

1. **Third-party (non-deepDDW) plugins are the user's responsibility**: any plugin
   not published by deepDDW — including DSH ecosystem plugins, community plugins,
   or self-written plugins — must be reviewed and accepted by the user for its
   security and data safety. Any data breach, system damage, or other incidents
   caused by third-party plugins are **not the responsibility of deepDDW**.

2. **What deepDDW guarantees**: deepDDW only guarantees the **code integrity and
   security of the Memory and Knowledge Base components**. deepDDW promises:

   - We do **not steal** your data
   - We do **not exploit** your data
   - We do **not sell** your data
   - By default, all data is stored on your own device/server and never leaves
     your LAN

3. **Recommendation**: before installing any plugin, verify its source, license,
   and maintenance status. For production environments, prefer plugins published
   by the official DSH team.

---

## 二、安全报告（Reporting a Vulnerability）

### 中文

如您发现 deepDDW 自身（记忆体/知识库/网关）的安全漏洞，请通过
**GitHub Issues（私密标注）** 或项目维护邮箱与我们联系。请勿公开披露，
以便我们及时修复。

### English

If you discover a security vulnerability in deepDDW itself (memory/knowledge
base/gateway), please contact us via **GitHub Issues (mark private)** or the
maintainer email. Please do not disclose publicly so we can fix it promptly.
