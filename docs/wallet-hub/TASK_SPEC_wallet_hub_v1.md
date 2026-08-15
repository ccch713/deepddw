# TASK_SPEC: DDW Wallet Hub 全面成型（v1.0）

> 编写：2026-08-12 · 开发执行：ZCode（16G） · 验收：32G Hermes + pytest
> 原则：**一口气全做完**（一期收单 + 二期问渠中台化 + 三期 SaaS 化），完成后可交付生产。
> 基线 commit：32G 主仓 `09c1de3`（ddw_wallet 微信支付修复）

---

## 0. 交接路径（必读）

### ZCode 读取路径（32G 本机，全部已就位）

| # | 路径 | 内容 |
|---|---|---|
| 1 | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wallet/` | **开发对象**：wallet 插件现状（1976 行，6 表 + 7 服务 + 10 端点 + 31 测试），**这是 Gitea 主仓，唯一事实源，原地开发** |
| 2 | `/Users/chenye/ddw-ai-hub/wenquK12/backend/app/api/wallet.py` | **问渠钱包 API**（要剥离的业务语义来源：双余额 recharge/income） |
| 3 | `/Users/chenye/ddw-ai-hub/wenquK12/backend/app/api/wechat.py` | 问渠微信 API |
| 4 | `/Users/chenye/ddw-ai-hub/wenquK12/backend/app/services/wechat_pay.py` | 问渠微信支付服务；**混合扣费逻辑在 `backend/app/api/message.py` L78-105（优先 recharge 后 income）** |
| 5 | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/docs/wallet-hub/` | 4 份设计文档（01-架构图 / 02-能力清单 / 03-缺口清单 / 04-路线图）+ 本 TASK_SPEC |

### 成品代码路径（写完必须放这里）

| # | 路径 | 说明 |
|---|---|---|
| 1 | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wallet/` | **唯一成品路径**，原地开发原地保存（32G 本机 = Gitea 主仓） |
| 2 | 禁止写入：`/Users/chenye/ddw-ai-hub/wenquK12/`（问渠只读参考）、`/Users/chenye/workspace/ddw-ai-hub/`（冻结的 dev 归档副本） |

### 交付流程

```
32G ZCode 开发 → /Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wallet/ 原地完成
→ 32G 主仓 pytest 全绿 → Hermes 验收 → Gitea commit [LLM:zcode]
```

---

## 1. 现状盘点（evidence，2026-08-12 实测）

### ✅ 已有（直接复用，禁止重写）

| # | 模块 | 状态 |
|---|---|---|
| 1 | `services/wechat_pay.py` | 真实 APIv3：Native 下单 / 回调验签+解密 / **`create_refund()` 已封装好**（只差接线） |
| 2 | `services/account.py` | 乐观锁余额变更（version + 5 次重试），credit/debit |
| 3 | `services/charge.py` | 按量扣费 + ref_id 幂等 + balance_after 快照 |
| 4 | `services/recharge.py` | 充值单 + 微信回调入账（WHERE status='pending' 原子更新） |
| 5 | `services/royalty.py` | 课件分成（英语 50% / 其他 80%，trigger_txn_id 幂等） |
| 6 | `router.py` | 10 端点：recharges / recharges/notify/wechat / charges / refunds / royalties / transactions / rate-rules |
| 7 | `models.py` | 6 表：accounts / recharge_orders / charge_records / refund_records / royalty_records / rate_rules，金额 Integer 分 |

### 🔴 缺口（本次全部完成，共 12 项 + 2 项）

| 编号 | 缺口 | 级别 | 方案 |
|---|---|---|---|
| G1 | 支付宝收单真实化 | P0 | `alipay_client.py` 重写：真实 SDK 下单 + RSA2 验签 + 查单 |
| G2 | 退款链路接通 | P0 | `refund.py` 接 `wechat_pay.create_refund()` + 支付宝退款 + 退款回调端点 |
| G3 | 三钱包拆账 | P0 | `WalletAccount` 加 recharge/income/skin 三余额字段 + 迁移 |
| G4 | 混合扣费 | P0 | `charge_with_fallback`（recharge→income→skin） |
| G5 | 平台抽佣 | P0 | `settle_royalty` 扩展 + `dw_wallet_platform_accounts` 表 |
| G6 | 对账引擎 | P0 | 拉微信账单 + 比对本地 + 差异报告（手动触发版） |
| G7 | 多租户 | P1 | 6 表加 tenant_id + 复合索引 + 服务层注入 |
| G8 | 余额冻结/解冻 | P1 | 使用预留 frozen_cents，freeze/unfreeze |
| G9 | 流水租户过滤 | P1 | list_transactions 强制 (tenant_id, user_id) |
| G10 | 子商户号 | P2 | 按 tenant 路由商户配置表 |
| G11 | 异步回调队列 | P2 | raw_callback 表 + 后台 worker（轻量，不引 Celery） |
| G12 | 审计日志 | P2 | dw_wallet_audit_logs 表（操作人/类型/前后余额/原因） |
| G13 | 修复测试 | — | `test_recharge_min_amount` 失败修复 |
| G14 | 问渠语义对齐 | — | 问渠双余额（recharge/income）+ skin 虚拟币语义剥离对齐 |

---

## 2. 目录结构（目标态）

```
plugins/ddw_wallet/
├── __init__.py
├── config.py                  # +ALIPAY_* 完整配置（已有占位，补齐证书模式）
├── manifest.yaml
├── models.py                  # 6 表扩展：三余额 + tenant_id + platform_accounts + audit_logs + raw_callbacks + tenant_payment_config
├── router.py                  # 端点扩展（见 §4）
├── schemas.py
├── plugin.py
├── services/
│   ├── account.py             # credit/debit 加 target 参数 + freeze/unfreeze + 审计钩子
│   ├── alipay_client.py       # ⚠️ 重写：真实 SDK（下单/验签/查单/退款）
│   ├── wechat_pay.py          # 不动（已完整），仅确认 create_refund 签名
│   ├── recharge.py            # +tenant 注入 + 支付宝回调入账 + 子商户路由
│   ├── charge.py              # +charge_with_fallback 混合扣费 + 抽佣触发
│   ├── refund.py              # +真实调用微信/支付宝退款 + 退款回调
│   ├── royalty.py             # +平台抽佣 +tenant
│   ├── reconciliation.py      # 🆕 对账引擎（手动触发）
│   ├── tenant_config.py       # 🆕 子商户号路由
│   └── audit.py               # 🆕 审计日志写入
├── migration/
│   └── migration_v1.py        # 🆕 单余额→三余额迁移（dry-run 先行）
└── tests/                     # 全量测试（见 §5）
```

---

## 3. 核心模型变更（models.py）

### 3.1 WalletAccount 三钱包

```python
class WalletAccount(WalletBase):
    __tablename__ = "dw_wallet_accounts"
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # G7
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 三钱包（分：Integer，禁 Float）
    recharge_balance_cents: Mapped[int] = mapped_column(Integer, default=0)   # 实收→消费
    income_balance_cents: Mapped[int] = mapped_column(Integer, default=0)     # 可提现→兜底
    skin_balance_cents: Mapped[int] = mapped_column(Integer, default=0)       # 虚拟币不可提现
    frozen_cents: Mapped[int] = mapped_column(Integer, default=0)             # G8 冻结
    status: Mapped[str] = mapped_column(String(20), default="active")
    version: Mapped[int] = mapped_column(Integer, default=0)                  # 乐观锁保留
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user"),)
```

> ⚠️ 原 `balance_cents` 字段删除，迁移脚本把旧值写入 `recharge_balance_cents`。

### 3.2 新增 4 张表

```python
class PlatformAccount(WalletBase):       # G5 平台分账账户
    __tablename__ = "dw_wallet_platform_accounts"
    tenant_id: str; balance_cents: int; version: int; updated_at

class AuditLog(WalletBase):              # G12 审计日志
    __tablename__ = "dw_wallet_audit_logs"
    tenant_id: str; user_id: str; operator: str   # system/admin/<id>
    action: str          # manual_credit/manual_debit/adjust/freeze/refund...
    amount_cents: int; balance_before: int; balance_after: int
    reason: str; created_at

class RawCallback(WalletBase):           # G11 异步队列
    __tablename__ = "dw_wallet_raw_callbacks"
    channel: str; event_type: str
    headers: Text                         # ⚠️ 必存：微信验签需 Wechatpay-Signature/Timestamp/Nonce/Serial 四头，仅请求时存在
    raw_body: Text
    status: str          # pending/processed/failed
    created_at; processed_at

class TenantPaymentConfig(WalletBase):   # G10 子商户路由
    __tablename__ = "dw_wallet_tenant_payment_config"
    tenant_id: str (unique)
    wechat_mch_id: str; wechat_app_id: str
    alipay_app_id: str
    # 证书路径/密钥一律走环境变量前缀 DDW_WALLET_TENANT_<TENANT>_* 或本表存路径（不存密钥值）
```

### 3.3 存量表加字段

- `recharge_orders` / `charge_records` / `refund_records` / `royalty_records`：全部加 `tenant_id: String(32) NOT NULL` + 复合索引 `(tenant_id, user_id)`（G7/G9）
- `charge_records` 加 `balance_type: str`（recharge/income/skin，G3/G4 扣减来源）
- `royalty_records` 加 `platform_fee_cents: int`（G5）

---

## 4. API 端点变更（router.py）

### 保留（形状不变）：`/recharges` POST、`/recharges/notify/wechat` POST、`/transactions` GET

### 新增 / 扩展

| # | Method | Path | 说明 |
|---|---|---|---|
| 1 | POST | `/recharges` | +`channel: wechat\|alipay`（现有已有）+ tenant 头注入 |
| 2 | POST | `/recharges/notify/alipay` | **G1** 支付宝异步通知验签+入账（同微信原子模式） |
| 3 | GET | `/recharges/query/{order_no}` | **G1** 主动查单兜底（alipay.trade.query / 微信查单） |
| 4 | POST | `/refunds` | **G2** 现接口接真实退款调用，返回 processing |
| 5 | POST | `/refunds/notify/wechat` | **G2** 微信退款结果回调（更新 status=success/failed） |
| 6 | POST | `/refunds/notify/alipay` | **G2** 支付宝退款回调 |
| 7 | POST | `/charges` | **G4** 混合扣费：body 加 `balance_priority`（默认 recharge,income,skin） |
| 8 | POST | `/accounts/{user_id}/freeze` | **G8** 冻结（amount_cents, reason） |
| 9 | POST | `/accounts/{user_id}/unfreeze` | **G8** 解冻 |
| 10 | GET | `/accounts/{user_id}/balances` | 三余额 + 冻结金额查询 |
| 11 | GET | `/transactions` | **G9** 强制 `tenant_id` 过滤（从请求头 X-Tenant-Id 或 JWT 取） |
| 12 | GET | `/royalties` | 分成列表 +tenant |
| 13 | POST | `/reconcile` | **G6** 手动触发对账（date 参数）→ 返回差异报告 |
| 14 | GET | `/reconcile/report` | **G6** 最近一次对账报告 |
| 15 | GET | `/audit-logs` | **G12** 审计日志查询（tenant 隔离） |
| 16 | POST | `/platform/accounts` | **G5** 平台账户查询/调账（管理员） |
| 17 | GET | `/platform/accounts` | 平台账户余额 |
| 18 | GET | `/health` | 保留，+version 字段 |

### 租户注入规则

- 所有读写端点从请求头 `X-Tenant-Id` 取租户（开发模式默认 `"default"`，生产从 JWT 解析——与底座鉴权层对齐）
- 未传租户 → 400；查无租户配置 → 用环境变量默认商户

---

## 5. 核心逻辑要点

### G1 支付宝真实化（alipay_client.py 重写）

```python
# 官方 SDK: pip install python-alipay-sdk（已在依赖中）
from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
from alipay.aop.api.AlipayClientConfig import AlipayClientConfig

def create_wap_order(order_no, amount_cents, subject) -> str:
    """alipay.trade.wap.pay 下单，返回跳转 form_html（真实）"""
    # request = AlipayTradeWapPayRequest(); biz_content = {
    #   out_trade_no, total_amount=f"{cents/100:.2f}", subject,
    #   product_code="QUICK_WAP_WAY", quit_url=...}
    # client.page_execute(request) → form html

def verify_notify(params: dict, sign: str) -> bool:
    """RSA2 验签（真实）：用支付宝公钥对 params 排序拼接 + sign 做 rsa2 验证"""
    # client.verify(params, sign) 或自实现 rsa2 验签

def query_order(order_no: str) -> dict:
    """alipay.trade.query 查单：TRADE_SUCCESS/TRADE_FINISHED 判定"""
```

- 配置补齐：`ALIPAY_CERT_MODE`（公钥模式默认）/ `ALIPAY_APP_CERT_PUBLIC_KEY` / `ALIPAY_ALIPAY_CERT_PUBLIC_KEY` / `ALIPAY_ALIPAY_ROOT_CERT`（证书模式），环境变量驱动
- 金额：`total_amount` 必须字符串两位小数（`f"{cents/100:.2f}"`），禁 float 运算

### G2 退款接通（refund.py）

```python
async def refund_balance(session, tenant_id, user_id, amount_cents, reason):
    order = 最近一笔 paid 充值单（+tenant 过滤）
    await debit_balance(..., target="recharge")     # 或按规则扣
    rec = RefundRecord(status="processing")          # 先落本地
    await session.flush()
    if order.channel == "wechat":
        wechat_pay.create_refund(order.order_no, rec.refund_no, order.amount_cents, amount_cents)
    elif order.channel == "alipay":
        alipay_client.create_refund(order.order_no, rec.refund_no, amount_cents)
    # 回调端点把 status processing → success/failed（G2 端点 5/6）
    # 失败：原路解冻/回滚余额 + 审计日志
```

### G3/G4 混合扣费（charge.py）

```python
async def charge_with_fallback(session, tenant_id, user_id, amount_cents,
                               ref_id, charge_type, subject,
                               priority=("recharge","income","skin")):
    # 1. ref_id 幂等检查（charge_records）
    # 2. 单事务内按 priority 逐钱包扣减（乐观锁 version，每钱包 5 次重试）
    # 3. 每段写一条 charge_records（balance_type 标注来源）+ balance_after 快照
    # 4. 任一 wallet 余额不足 → 下一个；全不足 → InsufficientBalanceError(402)
    # 5. 任一段失败整体回滚
    # 6. 扣费成功后触发 G5 抽佣 settle_platform_fee()
    # 7. 写审计日志（audit.py）
```

### G5 平台抽佣（royalty.py 扩展）

```python
PLATFORM_FEE_PERCENT = 5   # 可配置 env: DDW_WALLET_PLATFORM_FEE_PERCENT

def settle_platform_fee(session, tenant_id, user_id, amount_cents, txn_no):
    # 抽佣 = amount_cents * percent / 100（向下取整，分）
    # credit PlatformAccount(tenant_id).balance_cents += fee
    # 写 royalty_records? 不 —— 写 charge_records 附属或独立 platform_fee_records（建议独立：dw_wallet_platform_fee_records，tenant_id/user_id/txn_no unique/fee_cents）
    # 幂等：txn_no UNIQUE
# settle_royalty 保持课件分成逻辑，先抽佣后分作者
```

### G6 对账引擎（reconciliation.py）

```python
async def daily_reconciliation(target_date) -> ReconciliationReport:
    # 1. 拉微信账单 APIv3 /v3/bill/fundflowbill（wechat_pay.py 加 fetch_bill()）
    # 2. 拉本地 recharge_orders（target_date, status=paid）
    # 3. 按 order_no 匹配 → matched/mismatched（金额不符/单边缺失）
    # 4. 返回报告：date, matched, mismatched[], payment_total, local_total, diff
    # 5. 差异写入 dw_wallet_reconciliation_logs 表（新表）
# 一期：手动 POST /reconcile 触发；cron 调度二期由底座 systemd 挂（不引 Celery）
```

### G8 冻结（account.py）

```python
async def freeze_balance(session, tenant_id, user_id, amount_cents, reason):
    # 乐观锁：balance=balance-amount, frozen=frozen+amount（原子 UPDATE WHERE version）
    # 解冻反向。审计日志。冻结金额不可消费（debit 时检查 available = balance - frozen）
```

### G11 异步回调（recharge.py 改造）

```python
# 微信/支付宝回调 → 先落 RawCallback(status=pending, headers=原始请求头, raw_body=原文) → 立即返回 SUCCESS
# ⚠️ headers 必须落库：微信验签需要 Wechatpay-Signature/Timestamp/Nonce/Serial 四头，仅回调请求时存在；
#    worker 验签依赖这些头，丢了 = 无法验签 = 全部回调失败
# 后台轻量 worker：asyncio 任务队列（进程内，随插件 start 启动）
#   → 处理：验签→入账→更新 RawCallback status
# 失败重试 3 次 → failed + 日志告警
# 注意：必须保留 notify_raw 原报文字段（已有）
```

---

## 6. 测试要求（tests/，每模块 ≥5 条）

| 文件 | 必测场景 |
|---|---|
| `test_account_v2.py` | 三钱包 credit/debit 定向；乐观锁并发（100 并发同一用户）；冻结后消费被拒；解冻恢复 |
| `test_charge_v2.py` | 混合扣费 3 种组合（recharge 足/不足跳 income/全不足 402）；原子回滚；ref_id 100 次幂等 |
| `test_alipay_v2.py` | 下单金额格式化（分→两位小数串）；RSA2 验签真/假签名；回调入账幂等；查单 TRADE_SUCCESS 判定 |
| `test_refund_v2.py` | 微信退款调用参数正确；支付宝退款；回调 success/failed 状态流转；无充值单报错 |
| `test_royalty_v2.py` | 抽佣 5% 计算（含小数向下取整）；抽佣幂等（同 txn 不重复）；先抽佣后分作者 |
| `test_tenant.py` | 跨租户查流水被隔离；未传 tenant 400；A 校余额不影响 B 校 |
| `test_reconcile.py` | 账单 vs 本地匹配/差异报告；金额不符标记 mismatched |
| `test_audit.py` | 手动调账写审计；审计查询租户隔离 |
| `test_recharge.py` | **修复现有 1 个失败**：min_amount 校验行为（config min_recharge_cents=100 → <1 元拒绝，pydantic 校验与路由校验统一） |

**现有 31 测试必须全绿（含修复后），新增测试 ≥ 35 条。**

---

## 7. 验收标准（全部满足才交付）

- [ ] pytest 全绿（现有 31 + 新增 ≥35，无 skip 无 xfail 滥用）
- [ ] 微信收单回归：mock 下单→回调→入账→消费→退款全链路
- [ ] 支付宝：mock 联调全链路 + 真实小额实测（资质到位后，代码先行）
- [ ] 三钱包：充值入 recharge；分成入 income；平台发放入 skin；消费按优先级扣
- [ ] 混合扣费：recharge 不足自动跳 income；全不足 402；并发 100 余额正确
- [ ] 抽佣：每笔 5% 入平台账户，幂等（同 txn 只抽一次）
- [ ] 多租户：A/B 两校数据完全隔离（含流水/审计/平台账户）
- [ ] 对账：手动触发返回差异报告，金额不符可发现
- [ ] 审计：所有余额变更（充值/扣费/退款/调账/冻结）都有日志
- [ ] 金额纪律：全程 Integer 分，无 float；支付宝金额两位小数串
- [ ] 密钥纪律：零硬编码，全部环境变量（config.py 声明）
- [ ] 迁移脚本：dry-run 打印迁移前后对比，可回滚

---

## 8. 红线（违反即返工）

1. **禁改** `services/wechat_pay.py` 已验证的收单逻辑（除非新增 fetch_bill）
2. **禁删** 现有幂等设计（ref_id / trigger_txn_id / WHERE status='pending' 原子更新）
3. **禁 float** 金额；**禁硬编码**密钥/商户号（读 config.py）
4. 现有 6 表表名/主键**禁改**（只加字段/加表）；旧 `balance_cents` 迁移后删除
5. 问渠代码 `wenquK12/` 只读参考，**禁止修改**
6. 开发过程每完成一个 G 项跑一次 `pytest`，全绿再继续

---

## 9. 执行顺序（ZCode 建议顺序）

```
Step 1: G13 修现有失败测试（5 min，建立信心）
Step 2: G1 支付宝真实化（独立，不依赖其他）
Step 3: G3 三钱包 schema + 迁移脚本（模型层，一切的前提）
Step 4: G4 混合扣费 + G5 抽佣（服务层）
Step 5: G2 退款接通（复用 wechat create_refund）
Step 6: G7/G9 多租户 + 租户过滤（横切，最后改 router 注入）
Step 7: G8 冻结 + G12 审计（account.py 扩展）
Step 8: G6 对账引擎（独立模块）
Step 9: G10 子商户路由 + G11 异步回调
Step 10: 全量回归 + 迁移 dry-run 验证 + README 更新
```

---

## 10. ZCode 总提示词（可直接粘贴，32G 本机）

```
你是 DDW 团队的高级 Python 工程师。任务：把 DDW Wallet Hub（预付费钱包支付中台）从
"单租户单钱包骨架" 升级为 "多租户三钱包 + 微信/支付宝全通道 + 退款/抽佣/对账/审计" 的
生产级支付中台。严格按照 TASK_SPEC 执行，完整施工图（模型/端点/测试/验收）在：
/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/docs/wallet-hub/TASK_SPEC_wallet_hub_v1.md

读取路径（32G 本机，全部就位）：
1. 开发对象：/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wallet/（Gitea 主仓，原地开发）
2. 问渠语义参考：/Users/chenye/ddw-ai-hub/wenquK12/backend/app/api/wallet.py（双余额 recharge/income）
3. 问渠支付：/Users/chenye/ddw-ai-hub/wenquK12/backend/app/services/wechat_pay.py
4. 问渠混合扣费：/Users/chenye/ddw-ai-hub/wenquK12/backend/app/api/message.py L78-105（优先 recharge 后 income）
5. 设计文档：/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/docs/wallet-hub/（01-架构图/02-能力/03-缺口/04-路线图）

成品路径：/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wallet/（唯一，原地保存）

任务清单（14 项，全部完成）：
G1 支付宝收单真实化（alipay_client.py 重写：alipay.trade.wap.pay 下单 + RSA2 验签 + alipay.trade.query 查单 + 退款，官方 python-alipay-sdk）
G2 退款链路接通（refund.py 接 wechat_pay.create_refund() 已有封装 + 支付宝退款 + 退款回调端点）
G3 三钱包拆账（WalletAccount 加 recharge/income/skin 三余额字段 + 迁移脚本 migration_v1.py，旧 balance_cents → recharge）
G4 混合扣费（charge_with_fallback：recharge→income→skin 优先级，单事务原子回滚）
G5 平台抽佣（settle_royalty 扩展 + dw_wallet_platform_accounts 表，默认 5% 可配置）
G6 对账引擎（拉微信账单 /v3/bill/fundflowbill + 比对本地 + 差异报告，手动触发版）
G7 多租户（6 表加 tenant_id + 复合索引 + 服务层注入）
G8 余额冻结/解冻（freeze_balance/unfreeze_balance，用预留 frozen_cents）
G9 流水租户过滤（list_transactions 强制 (tenant_id, user_id)）
G10 子商户号路由（dw_wallet_tenant_payment_config 表，按 tenant 选商户配置）
G11 异步回调队列（dw_wallet_raw_callbacks 表 + 进程内轻量 worker，不引 Celery）
G12 审计日志（dw_wallet_audit_logs 表：操作人/类型/前后余额/原因）
G13 修复测试（test_recharge_min_amount 失败：config min_recharge_cents=100 与路由/pydantic 校验统一）
G14 问渠语义对齐（三钱包语义与问渠双余额对齐，skin=平台发放虚拟币不可提现）

约束（红线）：
1. 只改 /Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wallet/ 内文件；wenquK12/ 只读参考禁改
2. 金额全程 Integer 分，禁 float；密钥/商户号禁硬编码（config.py 环境变量，前缀 DDW_WALLET_）
3. 微信收单核心（services/wechat_pay.py）禁动，只可新增 fetch_bill
4. 现有 6 表表名/主键禁改（只加字段/加表）；幂等设计（ref_id/trigger_txn_id/WHERE status='pending'）禁删
5. 每完成一个 G 项跑一次 pytest 全绿再继续；最终 pytest 全绿（现有 31 + 新增 ≥35，无 skip/xfail 滥用）
6. 现有 10 个 API 端点形状保持兼容（只加字段/参数，不破坏调用方）

执行顺序：G13 → G1 → G3 → G4+G5 → G2 → G7+G9 → G8+G12 → G6 → G10+G11 → 全量回归 + 迁移 dry-run + README 更新

完成后输出：修改文件清单 + 新增端点清单 + 测试统计（总数/通过/失败）+ 迁移脚本 dry-run 输出 + 自测结论。
```
