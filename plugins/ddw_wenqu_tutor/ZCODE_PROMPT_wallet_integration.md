# 问渠 × Wallet Hub 整合提示词（ZCode 用）

你是 DDW AI Hub 的高级 Python 工程师。任务：**将问渠学科包（ddw_wenqu_tutor）接入 DDW 支付中台（ddw_wallet v0.2.0）**，实现开课余额校验 + 下课自动扣费。

---

## 第一步：深度阅读以下文件（按顺序，全部读完再动手）

### 1.1 支付中台（ddw_wallet）— 你要调用的 API

| # | 文件 | 看什么 |
|---|---|---|
| A | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wallet/router.py` | 找 `/accounts/{user_id}/balances`（查余额）和 `/charges`（扣费）和 `/charges/fallback`（混合扣费）三个端点的完整签名 |
| B | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wallet/schemas.py` | `ChargeCreate`（扣费请求模型）和 `WalletAccountOut`（余额响应模型）的字段定义 |
| C | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wallet/services/charge.py` | `charge()` 和 `charge_with_fallback()` 的幂等逻辑（ref_id 去重）和 `InsufficientBalanceError` 异常处理 |
| D | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wallet/services/account.py` | `get_three_balances()` 返回的三钱包字段名（recharge_balance_cents / income_balance_cents / skin_balance_cents） |
| E | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wallet/manifest.yaml` | 端点前缀确认 |

### 1.2 问渠学科包（ddw_wenqu_tutor）— 你要改的代码

| # | 文件 | 看什么 |
|---|---|---|
| F | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wenqu_tutor/router.py` | 重点看 `session_start()` 第 69 行 `wallet_client=None` 和 `session_end()` 第 169 行的调用方式。**这就是你要接入的地方** |
| G | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wenqu_tutor/services/session.py` | `end_session()` 已经写好了 `wallet_client.charge()` 调用链（第 170-190 行），但 wallet_client 永远是 None 所以走 except 分支。**你需要把真正的 client 传进来** |
| H | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wenqu_tutor/config.py` | `WALLET_BASE` = `http://127.0.0.1:8500` 和 `RATE_STUDY_CENTS_PER_MINUTE = 1200`（¥0.2/分钟） |
| I | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wenqu_tutor/models.py` | `WenquSession` 表结构，特别是 `student_name`（将作为 wallet 的 user_id）、`charge_txn_no`、`status` 字段 |
| J | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wenqu_tutor/schemas.py` | `SessionStart` 请求模型（student_name / subject / chapter） |
| K | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wenqu_tutor/plugin.py` | `WenquTutorPlugin.setup()` 看 router 注册方式 |

### 1.3 设计文档（wallet hub 完整架构）

| # | 文件 | 看什么 |
|---|---|---|
| L | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/docs/wallet-hub/02-能力清单-已实现vs问渠要求.md` | 问渠要求 vs wallet hub 已有能力的对照表 |
| M | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/docs/wallet-hub/04-嵌入问渠方案-中台化路线图.md` | 整合路线图和 API 契约 |

---

## 第二步：写 PRD + TASK_SPEC

读完全部文件后，输出以下两个文档（Markdown 格式），保存到：

### 2.1 PRD
保存到：`/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/docs/wallet-hub/05-问渠整合PRD.md`

PRD 必须包含：
1. 产品定位（问渠作为 ddw_wallet 的业务方）
2. 用户故事（学生开课、学生下课、家长查余额）
3. 功能清单（P0/P1/P2 优先级）
4. API 契约（问渠调 wallet hub 的 3 个端点的请求/响应格式）
5. 错误处理（402 余额不足、503 钱包服务不可用、幂等重复扣费）
6. 非功能需求（超时、重试、降级策略）

### 2.2 TASK_SPEC
保存到：`/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wenqu_tutor/TASK_SPEC_wallet_integration.md`

TASK_SPEC 必须包含：

**要创建的文件（4 个）：**

| # | 绝对路径 | 内容 |
|---|---|---|
| **A** | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wenqu_tutor/services/wallet_client.py` | httpx 异步 HTTP 客户端，封装 3 个方法 |
| **B** | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wenqu_tutor/router.py` | 改：session/start 加余额校验，session/end 传入真实 wallet_client |
| **C** | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wenqu_tutor/services/session.py` | 改：end_session() except 分支补错误日志 |
| **D** | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_wenqu_tutor/tests/test_wallet_integration.py` | 新建：3 个场景测试 |

**wallet_client.py 的 3 个方法签名：**
```python
class WenquWalletClient:
    """问渠→wallet hub HTTP 桥接客户端。"""

    def __init__(self, base_url: str = "http://127.0.0.1:8500"):
        self.base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=10.0)

    async def get_balance(self, user_id: str) -> dict:
        """GET /api/v1/plugins/ddw_wallet/accounts/{user_id}/balances
        返回: {"recharge_balance_cents": int, "income_balance_cents": int, "skin_balance_cents": int}
        失败: 抛 WalletServiceError
        """

    async def check_balance(self, user_id: str, min_cents: int = 100) -> bool:
        """余额是否 >= min_cents。调 get_balance 内部判断。"""

    async def charge(
        self,
        user_id: str,
        charge_type: str,       # "study_time"
        subject: str | None,    # "physics" / "chemistry"
        ref_id: str,            # session_id（幂等键）
        ref_type: str,          # "session"
        amount_cents: int,      # 活跃分钟 × 1200分/分钟
        balance_priority: str = "recharge,income,skin",
    ) -> dict:
        """POST /api/v1/plugins/ddw_wallet/charges
        返回: {"txn_no": str, "amount_cents": int, "balance_after_cents": int}
        失败: InsufficientBalanceError → 402 / WalletServiceError → 503
        """

    async def close(self):
        """关闭 httpx client。"""
```

**router.py 改动点：**
```python
# session/start 改动（约第 69 行附近）：
@router.post("/session/start", response_model=SessionOut)
async def session_start(req: SessionStart, db: AsyncSession = Depends(get_db)):
    wallet = WenquWalletClient(base_url=WALLET_BASE)
    try:
        has_balance = await wallet.check_balance(req.student_name, min_cents=100)
        if not has_balance:
            raise HTTPException(status_code=402, detail={
                "code": "INSUFFICIENT_BALANCE",
                "message": "钱包余额不足，请先充值",
            })
        session = await create_session(db, ...)
        return SessionOut(...)
    finally:
        await wallet.close()

# session/end 改动（约第 169 行附近）：
@router.post("/session/{session_id}/end", response_model=SessionEndOut)
async def session_end(session_id: str, db: AsyncSession = Depends(get_db)):
    wallet = WenquWalletClient(base_url=WALLET_BASE)
    try:
        result = await end_session(db, session_id, wallet)
        return SessionEndOut(...)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        await wallet.close()
```

**测试用例（3 条核心）：**
```python
# T1: 余额充足 → 开课成功
# mock GET /accounts/{uid}/balances → {"recharge_balance_cents": 5000, ...}
# POST /session/start → 200 + session_id

# T2: 余额不足 → 402
# mock GET /accounts/{uid}/balances → {"recharge_balance_cents": 0, "income_balance_cents": 0, "skin_balance_cents": 0}
# POST /session/start → 402 INSUFFICIENT_BALANCE

# T3: 下课扣费成功
# mock POST /charges → {"txn_no": "C20260813xxx", "amount_cents": 2400, "balance_after_cents": 2600}
# POST /session/{id}/end → 200 + active_minutes + charge_cents + balance_after_cents
```

**验收标准：**
- pytest 全绿（新增 3 条 + 不破坏原有测试）
- `ruff check plugins/ddw_wenqu_tutor/` 无错误
- wallet_client 只用 httpx（不引入 requests）
- 不修改 ddw_wallet 的任何代码（纯消费方）

---

## 第三步：铁律（必须遵守）

1. **问渠是 ddw_wallet 的消费方**，只调 API，不直连 wallet 数据库
2. **wallet_client 用 httpx.AsyncClient**，不用 requests（async FastAPI 里同步 requests 阻塞事件循环）
3. **ref_id = session_id**，保证幂等（同一节课重复调不重复扣）
4. **余额不足统一 402**，错误码 `INSUFFICIENT_BALANCE`，前端据此弹充值引导
5. **wallet 服务不可用时降级**：开课不阻塞（允许开课但记录 warning），下课不阻塞（记录 charge_error 事件，后续手动补扣）
6. **不修改 ddw_wallet 的任何文件**，整合改动全部在 ddw_wenqu_tutor 内完成
7. **Pydantic 模型模块级定义**，禁止在函数/闭包内定义（FastAPI 422 坑）
8. **PluginBase.__init__ 自动调 self.setup()**，setup() 依赖的属性必须在 super().__init__() 之前初始化
9. **config.py 的 WALLET_BASE 已存在**，直接 import 使用，不要新建配置项
10. **manifest.yaml 的 dependencies** 必须是 dict（`plugins: {}`），不是 list
