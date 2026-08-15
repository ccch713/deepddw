# DDW 插件热加载设计方案（v0.1 · 设计稿，未实现）

> 日期：2026-08-15 · 状态：待评审
> 范围：**只设计，不动代码**。本文给出热加载架构、红线落地方式、更新策略与实施路径。

---

## 0. 结论先行（TL;DR）

- **插件零改动**：热加载全部实现在 core 层（加载器抽象 + installer 集成 + 管理端点），
  90+ 插件已统一实现 `PluginBase` 协议，无需逐个修改。
- **做"安装即生效 + 停用/更新重挂"，不做"运行中卸载路由 / 插件级 HMR"**（架构不支持，见 §2 非目标）。
- **三条红线**：验签先于加载、授权过滤同路径、`locked` 拒绝热启——确保今晚的授权/防盗版体系零削弱。
- 客户收益：**在线增补不中断 + 失败隔离**（首次部署无变化）。

---

## 1. 目标与非目标

### 1.1 目标

| # | 能力 | 说明 |
|---|---|---|
| G1 | **安装即生效** | `.ddwplugin` 验签安装后，插件立即加载并挂载路由，**在线业务不中断**（现为重启后生效） |
| G2 | **停用/更新重挂** | 管理端可停用指定插件；更新 = 新版本落盘 + 滚动重挂（先停后挂，短窗口） |
| G3 | **失败隔离** | 单插件加载/初始化失败只影响它自己，不影响其他已加载插件与整体服务 |
| G4 | **加载审计** | 每次热装/热启/停用记录操作者、时间、插件、结果（与 customer 溯源一脉相承） |

### 1.2 非目标（明确不做，含理由）

| 能力 | 为什么不做 |
|---|---|
| 运行中**卸载路由** | FastAPI 路由注册不可逆；SQLAlchemy 模型注册进共享 `Base.metadata` 无法回滚；插件 DB schema 无法干净撤销 → 卸载 = 停用入口 + 标记待重启清理 |
| 插件级 **HMR**（改代码即热更新） | Python 模块重载存在 `sys.modules` 污染与单例残留（测试期已踩坑）；`uvicorn --reload` 已覆盖开发场景 → 开发模式可选做 watcher，生产禁用 |
| 跨进程热迁移/集群 | 超出本设计范围（属部署/编排层） |

---

## 2. 现状盘点（设计依据，引用真实代码）

| 组件 | 现状 | 与热加载的关系 |
|---|---|---|
| `core/main.py::load_plugins` | 启动时一次性扫描 `plugins/*/manifest.yaml` → import → `PluginBase` 实例化 → `register()` 挂 router；含 license 过滤、locked 跳过、manifest 读取 | **核心重构对象**：抽成可复用的"单插件加载"函数 |
| `core/plugin_manager/installer.py` | `install_from_package`：zip 解压 → 验签（Ed25519，`DDW_PLUGIN_SIGNING_PUBLIC_KEY`）→ 落盘 `plugins/<name>/`；含路径穿越防护 | **安装入口**：落盘后调用加载器完成"立即生效" |
| `sdk/plugin_base.py::PluginBase` | SDK v2：`__init__` + FSM（CREATED→INITIALIZED→RUNNING→STOPPED）+ `setup()/register()`（legacy 兼容：`register` 检测 `self.router/_router` 后 include） | **统一协议**：插件无需改动；热加载只负责"何时实例化 + 何时 register" |
| license 授权过滤 | `load_plugins` 内：license 文件验签（Ed25519）→ 有效则取 `authorized_plugins`；production 下失败 fail-closed 只加载 `license: free`；`DDW_ENV` 未设置但有 license 文件按生产处理 | **红线②**：热加载必须复用同一过滤，不允许第二条路径 |
| `status: locked` | `load_plugins` 读 manifest 跳过 locked 插件（仅入库不部署） | **红线③**：热装/热启同样拒绝 |
| `.ddwplugin` 验签 | `installer.verify_package`（文件清单 sha256 + Ed25519 签名，公钥 env） | **红线①**：安装路径唯一入口，验签不可绕过 |

---

## 3. 架构设计

### 3.1 总体结构

```
                    ┌─────────────────────────────────────────────┐
                    │              PluginRuntime（core 新增）        │
                    │  ├─ registry: PluginRegistry                 │
                    │  │    {name → {manifest, module, instance,   │
                    │  │             router, state, loaded_at}}    │
                    │  ├─ load_one(name) / unload_entry(name)      │
                    │  ├─ reload_one(name)（停→挂，滚动）            │
                    │  └─ audit_log                                 │
                    └───────────────┬─────────────────────────────┘
          ┌─────────────────────────┼──────────────────────────┐
          ▼                         ▼                          ▼
   load_plugins(启动)         installer.install_from_package  admin 管理端点
   （改为：批量调 load_one）    （验签落盘后 → runtime.load_one）  （POST /plugins/load, /unload…）
          │
          └── 复用同一授权过滤：license 分层 + authorized_plugins + locked 拒绝
```

### 3.2 核心组件

**A. `PluginRuntime`（core/plugin_manager/runtime.py，新增）**
- `load_one(plugin_name) -> bool`：单插件加载（重构自 `load_plugins` 循环体）
  1. 读 manifest（unreadable → 失败隔离返回 False）
  2. **红线③**：`status == locked` → 拒绝
  3. **红线②**：license 授权过滤（commercial 需授权；production fail-closed 语义一致）
  4. `importlib.import_module(f"plugins.{name}.plugin")`
  5. `cls(app, config, manifest)` 实例化 → `register()`（现有协议）
  6. registry 登记 + 审计
- `unload_entry(plugin_name)`：停用入口（**不做路由卸载**）——registry 标记 `disabled`，管理端点与授权判定对该插件拒绝；保留模块与路由（物理清理走"重启"）
- `reload_one(plugin_name)`：更新/重挂——先 `unload_entry` 停用 → 重新 `load_one`（模块级单例残留时标记"需重启完成彻底更新"，见 §5）
- 模块级单例：`PluginRuntime` 单例挂在 `app.state.plugin_runtime`

**B. `PluginRegistry`**
- 内存索引：`name → {manifest, module, instance, router, state: loaded|disabled|error, loaded_at, error}`
- 启动时由 `load_plugins` 全量填充（迁移现有逻辑），运行时由管理端点增量更新

**C. installer 集成**
- `install_from_package` 验签落盘成功后 → 调 `runtime.load_one(name)`
- 失败路径：落盘成功但加载失败 → 目录保留 + registry 记 `error` + 审计（不自动回滚安装，留人工处置）

**D. 管理端点（core/api/admin.py 追加，或独立 license-plugin 管理模块）**
- `POST /api/v1/admin/plugins/{name}/load`：热装/热启（已落盘插件）
- `POST /api/v1/admin/plugins/{name}/unload`：停用
- `POST /api/v1/admin/plugins/{name}/reload`：更新重挂
- `GET /api/v1/admin/plugins/runtime`：registry 状态（loaded/disabled/error + 审计摘要）
- 权限：`Role.SUPERADMIN`（引用 core/constants/roles.py）；所有操作写审计日志

### 3.3 数据流（安装即生效）

```
POST 上传 .ddwplugin → installer.verify_package（验签+路径防护）
  → 落盘 plugins/<name>/
  → runtime.load_one(name)
      ├─ manifest 读取 → locked? 拒绝
      ├─ license 授权过滤（与启动路径同一函数）
      ├─ import → 实例化 → register → router 挂载
      └─ registry 登记 + audit_log（operator/ts/result）
  → 返回 {loaded: true, router: /api/v1/plugins/...}
```

---

## 4. 红线落地方式（确保授权/防盗版零削弱）

| 红线 | 落地方式 | 防什么 |
|---|---|---|
| **① 验签先于加载** | 加载**唯一入口**是 `install_from_package`（验签通过才落盘）；`runtime.load_one` 只接受"已落盘且 registry 可查"的插件；**不提供**绕过落盘的动态加载捷径（含开发调试参数） | 未验签插件被热装 |
| **② 授权过滤同路径** | `load_plugins` 的 license 过滤逻辑抽成共享函数（`core/utils/license_validator` 层），启动与热加载**调用同一函数**；热装顺序固定：**先授权校验通过 → 再 import/实例化** | 未授权/失败场景下商业插件被热装绕过 fail-closed |
| **③ locked 拒绝** | `load_one` 第一步读 manifest 的 `status`，`locked` 直接拒绝（返回 `{loaded:false, reason:"locked"}`），与启动跳过逻辑同源 | 被取代插件被热启 |

**新增攻击面与对策**：

| 攻击面 | 对策 |
|---|---|
| 管理端点成为新入口 | superadmin 权限 + 验签（复用 broker 风格 token 或 JWT role）+ **加载审计**（operator/user_id、时间、插件、动作、结果、请求 IP） |
| 动态解压路径注入 | 复用 installer 既有路径穿越防护（拒绝 `..`/绝对路径） |
| 授权状态变化竞态 | 热装只发生在授权验证通过之后；授权失败/吊销时 `registry` 标记 `disabled`（信息层 + 拦截层同判） |
| 审计篡改 | 审计日志只追加；可纳入后续运维批次（备份/审计模块）统一落库 |

---

## 5. 更新策略

| 操作 | 策略 | 说明 |
|---|---|---|
| **新增安装** | 立即生效 | 验签 → 落盘 → `load_one` → 挂载；无存量模块冲突 |
| **更新（同版本升级）** | **滚动重挂**：`unload_entry`（停用）→ 覆盖落盘 → `load_one` → 挂载 | 短窗口内该插件路由不可用（毫秒~秒级）；其他插件不受影响 |
| **更新（含模块级单例插件，如 ddw_memory/vector store）** | **标记重启**：新版本落盘 + registry 记 `pending_restart` + 管理端提示"此插件更新需重启生效" | 模块级单例无法热替换（`sys.modules` 残留）；重启是唯一彻底路径，**这是诚实的边界** |
| **停用** | `unload_entry`：registry 标记 disabled + 管理端点/授权判定拒绝其入口 | 路由物理保留（无法卸载），但业务入口已停；彻底清理走重启 |
| **卸载（删插件）** | 仅管理端标记 `uninstalled` + 目录保留（或删除）+ 提示重启 | 不尝试运行中删除路由/模型 |
| **失败隔离** | `load_one` 全程 try/except：加载失败 → registry 记 `error` + 审计 + 不影响其他插件/服务 | 替代现有"启动时一个坏插件拖慢整个启动" |

---

## 6. 安全与兼容性

- **与授权链路兼容**：热加载只新增"触发时机"，判定逻辑全部复用现有函数（license 验签、分层、locked、指纹、broker 广播），无第二条判定路径 → 今晚的授权/防盗版体系行为不变。
- **与 installer 兼容**：验签/路径防护原样复用；热加载不新增解压入口。
- **与锁死机制兼容**：locked 插件在启动与热装两个路径都被拒绝（同源判断）。
- **配置**：`DDW_ENV=production` 下热装仅 superadmin 可调（管理端点本身）；开发模式可放宽审计级别但**验签与授权红线不降级**。

---

## 7. 实施步骤（分阶段，供评审后排期）

| 阶段 | 内容 | 交付 |
|---|---|---|
| **P1 加载器抽象** | 从 `load_plugins` 抽出 `load_one`/`unload_entry` 共享函数；启动路径改为批量调用（**行为不变**，全量回归保底）；`PluginRuntime`/`PluginRegistry` 骨架 | 重构 + 全量回归 1820 全绿 |
| **P2 安装即生效** | installer 落盘后调 `load_one`；管理端点 load/unload/reload + superadmin + 审计 | 热装/停用/重挂可用 |
| **P3 更新策略落地** | 滚动重挂 + `pending_restart` 标记 + 管理端提示 | 更新闭环 |
| **P4（可选）开发模式 HMR** | `DDW_ENV=development` 下 watcher + 重挂（生产禁用） | 开发体验 |
| 贯穿 | 每条红线单独 pytest：验签拒绝/未授权拒绝/locked 拒绝/审计记录 | 测试集 |

## 8. 风险与回退

| 风险 | 缓解 |
|---|---|
| 模块级单例残留（热更新不彻底） | 诚实标记 `pending_restart`，更新走重启；不停用路由不卸载 |
| 依赖顺序（热装插件依赖未加载插件） | 加载前检查 manifest `dependencies`，缺失依赖 → 拒绝并提示（与启动路径一致，启动本就不排序，属既有边界） |
| 管理端点滥用 | superadmin + 审计 + 限频（后续运维批次） |
| **回退** | 任何异常 → 重启服务回到现状（热加载是增量能力，启动路径保持全量加载，重启永远可回退） |

## 9. 测试计划

1. 安装即生效：上传签名包 → 新路由立即可用（无需重启）
2. 红线①：篡改包/未签名包 → 拒绝安装，不触发加载
3. 红线②：未授权 commercial 插件热装 → 拒绝（fail-closed 语义一致）
4. 红线③：locked 插件热装 → 拒绝
5. 失败隔离：坏插件加载失败 → 其他插件与 /health 正常
6. 更新：同版本重挂短窗口、单例插件标记 pending_restart
7. 审计：每次操作记录 operator/动作/结果
8. 全量回归：启动路径行为不变（1820 基线）

---

## 附：一句话给决策

**插件零改动、只改 core 三处、三红线复用现有判定、更新走"滚动重挂或标记重启"的诚实边界——热插拔是授权体系的增量而非威胁。**
