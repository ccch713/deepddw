# DDW 预付费钱包插件 TASK_SPEC v1.0

> **状态**：待开发（资质审核期间可并行开发）
> **日期**：2026-08-05
> **作者**：Hermes Agent（DeepSeek-V4-Flash）
> **目标**：问渠（K12 学习 SaaS）的支付与计费底座——预付费钱包插件 `ddw_wallet`
> **开发方式**：MiMo Code / MiniMax Code（AHE Loop），本 SPEC 可直接投喂

---

## 0. 文档说明

### 0.1 术语

| 术语 | 含义 |
|---|---|
| 钱包账户 | 每个学生/作者一个余额账户（单位：**分**，禁止浮点） |
| 充值单 | 用户发起充值产生的订单（pending → paid → refunded） |
| 按量扣费 | 学习产生消耗后按计费规则从余额扣减 |
| 分成 | 课件被学习后，学习收入按学科比例（80%/50%）计入作者余额 |
| 原路退回 | 退款走支付渠道原路返回（微信/支付宝） |

### 0.2 用户已拍板的商业规则（必须遵守）

1. **纯预付费**：最低充值 5 元（500 分），余额可退，无免费体验、不设门槛
2. **按量计费**：活跃学习时长（token 消耗）、课件生成、语音交互 三类计费点
3. **共享收益**：数理化课件作者得 80%，英语口语课件作者得 50%（**学科差异化，框架先行**）
4. **月卡暂不实现**（用户量上来后再加）
5. 支付渠道：微信支付（APIv3）+ 支付宝（电脑网站/手机网站）
6. 退款：余额原路退回；作者提现 V2 再做（预留接口）

---

## 1. 目录结构

```
plugins/ddw_wallet/
├── __init__.py                # PLUGIN_NAME="DDW Wallet 预付费钱包" VERSION="0.1.0"
├── plugin.py                  # WalletPlugin(PluginBase)：5 态生命周期 + 路由注册
├── router.py                  # FastAPI APIRouter（全部端点）
├── models.py                  # SQLAlchemy ORM（6 张表）
├── schemas.py                 # Pydantic v2 请求/响应模型
├── manifest.yaml              # 插件元数据（依赖 ddw-llm-gateway 等）
├── config.py                  # 环境变量读取（密钥不进代码）
├── services/
│   ├── __init__.py
│   ├── account.py             # 账户创建/余额查询/乐观锁扣减
│   ├── recharge.py            # 充值单创建 + 回调入账（幂等）
│   ├── charge.py              # 按量扣费（幂等键）
│   ├── refund.py              # 余额原路退回
│   ├── royalty.py             # 课件分成入账
│   ├── wechat_pay.py          # 微信 APIv3 客户端（官方 SDK 包装）
│   └── alipay_client.py       # 支付宝客户端（SDK 包装）
├── tests/
│   ├── conftest.py            # 测试库 fixture + mock 支付客户端
│   ├── test_account.py        # 账户与并发扣费
│   ├── test_recharge.py       # 充值单创建
│   ├── test_wechat_callback.py# 微信回调验签/解密/幂等
│   ├── test_charge.py         # 按量扣费
│   ├── test_refund.py         # 退款
│   └── test_royalty.py        # 分成计算（80%/50%）
├── README.md
└── LICENSE                    # Apache-2.0
```

## 2. 数据库模型（SQLAlchemy）

```python
# models.py 核心表（表前缀 dw_wallet_）
# 所有金额字段：Integer（单位：分），禁止 Float

class WalletAccount(Base):
    __tablename__ = "dw_wallet_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # DDW 用户ID
    balance_cents: Mapped[int] = mapped_column(default=0)      # 可用余额（分）
    frozen_cents: Mapped[int] = mapped_column(default=0)       # 冻结金额（预留）
    status: Mapped[str] = mapped_column(default="active")      # active|frozen|closed
    version: Mapped[int] = mapped_column(default=0)            # 乐观锁版本号
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(onupdate=func.now())

class RechargeOrder(Base):
    __tablename__ = "dw_wallet_recharge_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True)   # 平台单号 WQ+时间戳+随机
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    amount_cents: Mapped[int]                                        # 充值金额（分）
    channel: Mapped[str] = mapped_column(String(16))                 # wechat|alipay
    status: Mapped[str] = mapped_column(default="pending")           # pending|paid|failed|refunded
    provider_order_id: Mapped[str] = mapped_column(String(64), nullable=True)  # 微信/支付宝单号
    notify_raw: Mapped[Text] = mapped_column(nullable=True)          # 原始回调（审计）
    paid_at: Mapped[datetime] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class ChargeRecord(Base):
    __tablename__ = "dw_wallet_charge_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    txn_no: Mapped[str] = mapped_column(String(40), unique=True)     # 扣费流水号
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    amount_cents: Mapped[int]                                        # 扣减（正数）
    charge_type: Mapped[str] = mapped_column(String(24))             # study_time|courseware|voice
    subject: Mapped[str] = mapped_column(String(128), nullable=True) # 科目（物理/化学/英语...）
    ref_id: Mapped[str] = mapped_column(String(64), unique=True)     # 幂等键（会话ID/生成任务ID）
    ref_type: Mapped[str] = mapped_column(String(32))                # session|generation|other
    balance_after: Mapped[int]                                       # 扣后余额
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class RefundRecord(Base):
    __tablename__ = "dw_wallet_refund_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    refund_no: Mapped[str] = mapped_column(String(40), unique=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    amount_cents: Mapped[int]
    channel: Mapped[str]                       # wechat|alipay
    source: Mapped[str]                        # recharge|balance（退哪笔）
    status: Mapped[str] = mapped_column(default="processing")  # processing|success|failed
    provider_refund_id: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class RoyaltyRecord(Base):
    __tablename__ = "dw_wallet_royalty_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    royalty_no: Mapped[str] = mapped_column(String(40), unique=True)
    author_user_id: Mapped[str] = mapped_column(String(64), index=True)  # 课件作者
    courseware_id: Mapped[str] = mapped_column(String(64), index=True)   # 课件ID
    trigger_txn_id: Mapped[str] = mapped_column(String(64), unique=True) # 触发扣费流水（防重复分成）
    study_amount_cents: Mapped[int]            # 本次学习消耗（分）
    rate_percent: Mapped[int]                  # 80 或 50（学科规则）
    income_cents: Mapped[int]                  # 作者收益 = study_amount * rate / 100
    status: Mapped[str] = mapped_column(default="settled")   # settled|pending
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class RateRule(Base):
    __tablename__ = "dw_wallet_rate_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    charge_type: Mapped[str]                    # study_time|courseware|voice
    subject: Mapped[str] = mapped_column(nullable=True)  # None=默认，物理/化学/数学/英语...
    unit_price_cents: Mapped[int]               # 单价（分）
    unit: Mapped[str] = mapped_column(default="minute")  # minute|item|second
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(onupdate=func.now())
```

## 3. Pydantic Schemas（schemas.py）

```python
# 请求
class RechargeCreate(BaseModel):
    amount_cents: int = Field(ge=500, le=1000000)   # 最低 5 元（500 分）
    channel: Literal["wechat", "alipay"]
    user_id: str = Field(min_length=1, max_length=64)

class ChargeCreate(BaseModel):
    user_id: str
    charge_type: Literal["study_time", "courseware", "voice"]
    subject: str | None = None
    ref_id: str                          # 幂等键（唯一）
    ref_type: str = "session"
    amount_cents: int = Field(gt=0)      # 由调用方计量，或由钱包按 RateRule 计算（二选一：amount 必填，RateRule 用于展示/校准）

class RefundCreate(BaseModel):
    user_id: str
    amount_cents: int = Field(gt=0)
    source: Literal["recharge", "balance"] = "balance"

class RoyaltyCreate(BaseModel):
    author_user_id: str
    courseware_id: str
    trigger_txn_id: str
    study_amount_cents: int
    subject: str | None = None           # 决定 rate（英语=50，其他=80）

# 响应
class WalletAccountOut(BaseModel):
    user_id: str
    balance_cents: int
    status: str
    updated_at: datetime

class RechargeOut(BaseModel):
    order_no: str
    amount_cents: int
    channel: str
    status: str
    pay_params: dict | None = None       # wechat: {code_url}, alipay: {form_html}

class ChargeOut(BaseModel):
    txn_no: str
    amount_cents: int
    balance_after: int

class RefundOut(BaseModel):
    refund_no: str
    status: str

class TransactionOut(BaseModel):
    txn_no: str | None
    order_no: str | None
    amount_cents: int
    direction: Literal["in", "out"]      # in=充值/分成, out=消费/退款
    channel: str
    subject: str | None
    created_at: datetime
```

## 4. API 端点（JSON 示例）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/plugins/ddw_wallet/accounts` | 创建账户 `{user_id}` → 200 `{user_id, balance_cents:0, status:"active"}` |
| GET | `/api/v1/plugins/ddw_wallet/accounts/{user_id}` | 余额查询 → `{user_id, balance_cents, status, updated_at}` |
| POST | `/api/v1/plugins/ddw_wallet/recharges` | 创建充值单 → wechat: `{order_no, status:"pending", pay_params:{code_url:"weixin://wxpay/..."}}`；alipay: `{pay_params:{form_html:"<form ...>"}}` |
| POST | `/api/v1/plugins/ddw_wallet/recharges/notify/wechat` | 微信支付回调（验签+解密+入账），返回微信要求的成功应答 |
| POST | `/api/v1/plugins/ddw_wallet/recharges/notify/alipay` | 支付宝异步通知（验签+入账），返回 `success` |
| GET | `/api/v1/plugins/ddw_wallet/recharges/{order_no}` | 充值单状态查询 |
| POST | `/api/v1/plugins/ddw_wallet/charges` | 按量扣费（幂等）→ 200 `{txn_no, amount_cents, balance_after}`；余额不足 → 402 `{code:"INSUFFICIENT_BALANCE", balance_cents}` |
| POST | `/api/v1/plugins/ddw_wallet/refunds` | 余额退款（原路退回）→ 200 `{refund_no, status:"processing"}` |
| POST | `/api/v1/plugins/ddw_wallet/royalties` | 课件分成入账（幂等 trigger_txn_id）→ 200 `{royalty_no, income_cents}` |
| GET | `/api/v1/plugins/ddw_wallet/transactions?user_id=&page=&size=` | 流水（分页，direction 过滤）→ `{items:[TransactionOut], total, page, size}` |
| GET | `/api/v1/plugins/ddw_wallet/rates` | 计费规则列表（管理端） |

## 5. 核心逻辑（关键 Python 代码）

### 5.1 微信 APIv3 客户端（services/wechat_pay.py，官方 SDK 包装）

```python
# 依赖：pip install wechatpayv3（腾讯官方 Python SDK，APIv3）
# 密钥全部来自环境变量（config.py），禁止硬编码
from wechatpayv3 import WeChatPay, WeChatPayType
from ddw_wallet.config import settings

_wx: WeChatPay | None = None

def get_client() -> WeChatPay:
    global _wx
    if _wx is None:
        _wx = WeChatPay(
            wechatpay_type=WeChatPayType.NATIVE,
            mchid=settings.WECHAT_MCH_ID,                    # 1749100620
            private_key=open(settings.WECHAT_PRIVATE_KEY).read(),  # apiclient_key.pem
            cert_serial_no=settings.WECHAT_CERT_SERIAL_NO,   # 证书序列号（从证书解析）
            apiv3_key=settings.WECHAT_API_V3_KEY,            # 用户确认的 APIv3 密钥
            appid=settings.WECHAT_APP_ID,                    # 关联公众号/小程序 AppID（需配置）
            notify_url=settings.WECHAT_NOTIFY_URL,           # https://wenquedu.com/api/v1/plugins/ddw_wallet/recharges/notify/wechat
        )
    return _wx

def create_native_order(order_no: str, amount_cents: int, description: str) -> str:
    """Native 下单，返回 code_url（二维码内容）"""
    wx = get_client()
    result = wx.pay(
        description=description,
        out_trade_no=order_no,
        amount={"total": amount_cents},      # 单位：分
        payer=None,                          # Native 无需 openid
    )
    # result["code_url"] → 前端生成二维码
    return result["code_url"]

def decrypt_notify(headers: dict, body: str) -> dict:
    """回调：验签 + 解密（SDK 内部完成），返回明文 resource 对象"""
    wx = get_client()
    result = wx.callback(headers=headers, body=body)   # 验签失败抛异常
    return result  # {'mchid','out_trade_no','trade_state':'SUCCESS','transaction_id','amount':{'total':...}, ...}

def refund(order_no: str, refund_no: str, total_cents: int, refund_cents: int) -> dict:
    wx = get_client()
    return wx.refund(
        out_trade_no=order_no,
        out_refund_no=refund_no,
        amount={"refund": refund_cents, "total": total_cents, "currency": "CNY"},
    )
```

### 5.2 充值回调入账（services/recharge.py，幂等核心）

```python
def handle_wechat_notify(headers: dict, body: str) -> tuple[bool, str]:
    """返回 (是否成功应答, 应答文本)。微信要求成功时返回 200 + '{"code":"SUCCESS","message":"成功"}'"""
    try:
        data = get_client().callback(headers=headers, body=body)   # 验签+解密，失败抛异常
    except Exception:
        return False, '{"code":"FAIL","message":"验签失败"}'       # 微信会重试
    if data.get("trade_state") != "SUCCESS":
        return True, '{"code":"SUCCESS","message":"成功"}'          # 非成功状态直接确认，不处理

    out_trade_no = data["out_trade_no"]
    paid_amount = data["amount"]["total"]
    transaction_id = data["transaction_id"]

    with db.session() as s:
        order = s.query(RechargeOrder).filter_by(order_no=out_trade_no).with_for_update().first()
        if order is None:
            return False, '{"code":"FAIL","message":"订单不存在"}'   # 重试直到订单存在
        if order.status == "paid":
            return True, '{"code":"SUCCESS","message":"成功"}'       # 幂等：已入账直接确认
        if order.status != "pending":
            return False, '{"code":"FAIL","message":"状态异常"}'
        # 金额校验：回调金额必须等于订单金额
        if paid_amount != order.amount_cents:
            return False, '{"code":"FAIL","message":"金额不符"}'

        # 入账（同事务）
        order.status = "paid"
        order.provider_order_id = transaction_id
        order.notify_raw = json.dumps(data, ensure_ascii=False)
        order.paid_at = datetime.now()
        _credit_balance(s, order.user_id, order.amount_cents)   # 乐观锁加余额
        s.commit()
    return True, '{"code":"SUCCESS","message":"成功"}'
```

### 5.3 按量扣费（services/charge.py，乐观锁 + 幂等）

```python
def charge(user_id: str, charge_type: str, subject: str | None,
           ref_id: str, ref_type: str, amount_cents: int) -> ChargeOut:
    with db.session() as s:
        # 幂等：同 ref_id 只扣一次
        existed = s.query(ChargeRecord).filter_by(ref_id=ref_id).first()
        if existed:
            return ChargeOut(txn_no=existed.txn_no, amount_cents=existed.amount_cents,
                             balance_after=existed.balance_after)

        acc = s.query(WalletAccount).filter_by(user_id=user_id).with_for_update().first()
        if acc is None or acc.status != "active":
            raise HTTPException(404, "账户不存在或已冻结")
        if acc.balance_cents < amount_cents:
            raise HTTPException(402, detail={"code": "INSUFFICIENT_BALANCE",
                                             "balance_cents": acc.balance_cents})

        acc.balance_cents -= amount_cents
        rec = ChargeRecord(txn_no=_gen_no("C"), user_id=user_id, amount_cents=amount_cents,
                           charge_type=charge_type, subject=subject, ref_id=ref_id,
                           ref_type=ref_type, balance_after=acc.balance_cents)
        s.add(rec)
        s.commit()
        return ChargeOut(txn_no=rec.txn_no, amount_cents=rec.amount_cents,
                         balance_after=acc.balance_cents)
```

### 5.4 课件分成（services/royalty.py，80%/50% 学科规则）

```python
SUBJECT_ROYALTY_RATE = {"default": 80, "english": 50}   # 数理化=80%，英语口语=50%

def settle_royalty(author_user_id: str, courseware_id: str, trigger_txn_id: str,
                   study_amount_cents: int, subject: str | None) -> RoyaltyOut:
    with db.session() as s:
        existed = s.query(RoyaltyRecord).filter_by(trigger_txn_id=trigger_txn_id).first()
        if existed:                                        # 幂等：同一次学习只分一次
            return RoyaltyOut(royalty_no=existed.royalty_no, income_cents=existed.income_cents)

        rate = SUBJECT_ROYALTY_RATE.get(subject, SUBJECT_ROYALTY_RATE["default"])
        income = study_amount_cents * rate // 100          # 整数运算，向下取整
        if income <= 0:
            raise HTTPException(400, "分成金额为 0")
        acc = s.query(WalletAccount).filter_by(user_id=author_user_id).with_for_update().first()
        if acc is None:
            acc = WalletAccount(user_id=author_user_id, balance_cents=0)
            s.add(acc)
        acc.balance_cents += income
        rec = RoyaltyRecord(royalty_no=_gen_no("R"), author_user_id=author_user_id,
                            courseware_id=courseware_id, trigger_txn_id=trigger_txn_id,
                            study_amount_cents=study_amount_cents, rate_percent=rate,
                            income_cents=income)
        s.add(rec)
        s.commit()
        return RoyaltyOut(royalty_no=rec.royalty_no, income_cents=income)
```

### 5.5 退款（services/refund.py，原路退回）

```python
def refund_balance(user_id: str, amount_cents: int) -> RefundOut:
    with db.session() as s:
        acc = s.query(WalletAccount).filter_by(user_id=user_id).with_for_update().first()
        if acc is None or acc.balance_cents < amount_cents:
            raise HTTPException(400, "余额不足或账户不存在")
        # 优先退最近一笔充值单（原路退回原则）；无充值记录则整笔退
        order = (s.query(RechargeOrder)
                 .filter_by(user_id=user_id, status="paid")
                 .order_by(RechargeOrder.paid_at.desc()).first())
        if order is None:
            raise HTTPException(400, "无原路可退（无充值记录）")
        acc.balance_cents -= amount_cents
        refund_no = _gen_no("F")
        s.add(RefundRecord(refund_no=refund_no, user_id=user_id, amount_cents=amount_cents,
                           channel=order.channel, source="balance", status="processing"))
        s.commit()
    # 异步调微信/支付宝退款（渠道按 order.channel），成功回写 status=success
    _call_provider_refund(order_no=order.order_no, refund_no=refund_no,
                          total_cents=order.amount_cents, refund_cents=amount_cents, channel=order.channel)
    return RefundOut(refund_no=refund_no, status="processing")
```

### 5.6 计费规则（services/charge.py 校准）

RateRule 表用于**展示与校准**：调用方（问渠学习会话/OpenMAIC 生成任务）自行计量并调用扣费接口传 amount；钱包侧用 RateRule 做上限校验（如 study_time 单价 × 时长 与传入金额偏差 >5% 时告警），MVP 不自动重算。

### 5.7 计费规则初始值（用户拍板 2026-08-05，写入 RateRule 种子数据）

| charge_type | subject | unit_price | unit | 说明 |
|---|---|---|---|---|
| study_time | 默认 | 0.2 元/活跃分钟（1200 分/时） | minute | 学习时长费（收入大头，毛利 95%+） |
| voice | 默认 | 0.5 元/分钟 | minute | 语音交互 |
| courseware | 静态（≤10 张图） | **5-10 元/次**（简单 500 分 / 复杂 800-1000 分，按复杂度阶梯） | item | **平进平出不赚钱**，成本回收 |
| courseware | 视频（≤30 分钟） | **20-50 元/次**（按规格：Seedance Mini 档 2000 分起，高规格 5000 分封顶） | item | 平进平出；超规格（4K/长叙事）按成本加成报价 |

**课件生成计费铁律（写进操作手册）**：
1. AI 生成不保证一次成功——**每次生成/重生成都按次计费**（云端 LLM 按次收费，平台平进平出不赚差价）
2. 平台向作者透明展示成本行情（见《课件作者操作手册》），老师知情后再生成
3. 生成费只是成本回收；**作者收益来自课件被学习的分成（80%/50%）**，学习费才是收入大头

## 6. 配置与密钥（config.py，全部环境变量）

```bash
# .env（禁止进 git，仅服务器/32G 本地）
DDW_WALLET_WECHAT_MCH_ID=1749100620
DDW_WALLET_WECHAT_APP_ID=wxXXXXXXXX            # 需配置：公众号/小程序 AppID（JSAPI 支付需要；Native 扫码可暂用商户平台绑定的 APPID）
DDW_WALLET_WECHAT_API_V3_KEY=<用户确认的 32 位密钥>
DDW_WALLET_WECHAT_PRIVATE_KEY=/path/apiclient_key.pem
DDW_WALLET_WECHAT_CERT=/path/apiclient_cert.pem
DDW_WALLET_WECHAT_CERT_SERIAL_NO=<证书序列号，启动时自动解析>
DDW_WALLET_WECHAT_PUBLIC_KEY_ID=PUB_KEY_ID_0117491006202026080500211977005001
DDW_WALLET_WECHAT_NOTIFY_URL=https://wenquedu.com/api/v1/plugins/ddw_wallet/recharges/notify/wechat
DDW_WALLET_ALIPAY_APP_ID=xxxxxxxx
DDW_WALLET_ALIPAY_PRIVATE_KEY=/path/alipay_private_key.pem
DDW_WALLET_ALIPAY_PUBLIC_KEY=/path/alipay_public_key.pem
DDW_WALLET_ALIPAY_NOTIFY_URL=https://wenquedu.com/api/v1/plugins/ddw_wallet/recharges/notify/alipay
DDW_WALLET_DB_URL=postgresql+asyncpg://...    # 复用 DDW 数据库（独立表）
```

**安全铁律**：密钥只存在于 `.env`（权限 600）或 ECS 加密环境变量；**不进代码、不进 git、不进日志、不回显**。

## 7. LLM Prompt（本模块说明）

**本插件为确定性资金逻辑，无 LLM 调用**（支付/扣费/退款/分成全部走代码+数据库事务）。预留一个可选能力（V1.1）：充值/消费提醒文案生成——

```text
[系统] 你是问渠钱包的通知文案助手。根据用户的消费流水生成一条简短、亲切的微信通知（≤50字），
语气参考：充话费后的到账提醒。不要使用营销话术，不要承诺收益。
[输入] JSON：{"event": "recharge_success|charge|balance_low", "amount_cents": 500, "balance_cents": 1200, "subject": "物理"}
[输出] 仅输出通知文案，如："充值 5 元已到账，当前余额 12 元。加油，今天也要主动思考！"
```

V1.0 不实现；如实现，走 DDW LLM Gateway（MiniMax M3），不直连。

## 8. 测试用例（pytest，8 条）

```python
# conftest：内存/测试 PG + mock 支付客户端（不发起真实网络请求）

def test_create_account():            # 创建账户 → balance=0, status=active
def test_duplicate_account():         # 同 user_id 重复创建 → 返回已有账户（不报错）
def test_create_wechat_recharge():    # 充值 500 分 → 返回 code_url（mock 微信下单），订单 pending
def test_recharge_min_amount():       # 充值 400 分（<500）→ 422 校验错误
def test_wechat_notify_success():     # mock 回调（验签+解密成功）→ 入账 500 分，订单 paid
def test_wechat_notify_idempotent():  # 同回调重发 → 余额只加一次
def test_wechat_notify_amount_mismatch():  # 回调金额≠订单金额 → 拒绝且不入账
def test_wechat_notify_bad_signature():    # 验签失败 → 返回 FAIL，余额不变
def test_charge_success():             # 扣费 100 分 → balance_after 正确，流水生成
def test_charge_insufficient():        # 余额不足 → 402 INSUFFICIENT_BALANCE
def test_charge_idempotent():          # 同 ref_id 二次扣费 → 返回首次流水，不再扣
def test_refund_balance():             # 退款 → 余额减少，RefundRecord processing（mock 渠道）
def test_royalty_default_80():         # 数理化学习 1000 分 → 作者 +800
def test_royalty_english_50():         # 英语学习 1000 分 → 作者 +500
def test_royalty_idempotent():         # 同 trigger_txn_id → 只分一次
def test_balance_concurrent_charge():  # 并发扣费（10 线程）→ 最终余额正确，无负数（乐观锁）
```

（16 条，覆盖 8 个必测场景 + 边界）

## 9. 验收标准

1. `pytest tests/ -q` 全绿（16 条），ruff 0 errors
2. 微信支付：真实 Native 扫码支付闭环（1 元小额实测：创建单→扫码→回调入账→余额正确）
3. 支付宝：真实支付闭环（小额实测，等商户号审核通过）
4. 回调安全：验签失败/金额不符/重复回调 三种攻击场景均被正确拒绝且不影响余额
5. 幂等：充值回调重发、扣费重试、分成重试，均不重复记账
6. 金额：全链路整数分，无浮点运算
7. 退款：真实小额退款原路到账
8. 计费规则：RateRule 可配置（数据库），学科差异化预留
9. 管理端：流水查询接口可用（家长端"每一分钱花得明明白白"的数据源）

## 10. 开发顺序（MiMo/MiniMax Code 按序执行）

1. M0：models.py + schemas.py + config.py + account.py（账户+乐观锁）→ pytest 通过再前进
2. M1：recharge.py + wechat_pay.py（mock 下单+回调验签解密+幂等入账）
3. M2：charge.py（扣费+幂等+402）→ refund.py（退款 mock）
4. M3：royalty.py（80%/50% 分成）→ router.py 全端点 + 管理端 rates
5. M4：支付宝客户端（alipay_client.py，等支付宝审核通过后联调）
6. M5：真实微信小额闭环验收（需备案域名可访问 + 证书部署）

**每步铁律**：写一个文件 → py_compile + ruff → 写测试 → pytest 通过 → 再下一个；每完成一个模块 git commit 一次（标签 `[LLM: xxx]`）。
