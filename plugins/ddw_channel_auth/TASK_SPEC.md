# TASK_SPEC — ddw_channel_auth 插件 V1

> 目标：实现 DDW「渠道授权与结算」插件 PRD v1.0 的**最小可用核心**：账号体系骨架 + 客户报备状态机 + 注册码实例化 + 换码广播 + 5 适配器电子签框架 + 待办核销清单 + 30 天试用 + POC 报告骨架 + 一级分销红线。
> 项目根：`/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/`
> 插件目录：`plugins/ddw_channel_auth/`（**下划线目录**，`importlib.import_module` 依赖）
> 工期：一夜（米莫折扣窗口 00:00-08:00）

---

## 〇、合规铁律（违反即重做）

1. **目录名严格 `ddw_channel_auth` 下划线**，连字符会被 `load_plugins()` skip。
2. **集成协议**：`core/plugins_loader.py` 用 `importlib.import_module(f"plugins.{name}.plugin")`，依赖：
   - `plugin.py` 含 `class Plugin(PluginBase)` 且 `__init__(self, app, config, manifest, **kwargs)`
   - `__init__.py` 含 `PLUGIN_NAME = "ddw-channel-auth"` + `VERSION = "1.0.0"`
   - `setup()` 中 `self._router = build_router()` 然后 `self.app.include_router(self._router)`
3. **SQLAlchemy 2.0 ORM**：`Mapped[type]` + `mapped_column()`；严禁旧式 `Column()`。
4. **路由前缀硬约束**：`/api/v1/plugins/ddw-channel-auth/`，**所有** `@router.get/post` 路径必须以 `/` 开头相对路径（FastAPI 自动拼前缀）。
5. **依赖与现有体系一致**：所有 ORM 继承 `core.database.models.Base, TenantMixin, TimestampMixin`，数据库访问用 `core.database.session.session_scope()` 异步上下文。
6. **测试**：`pytest tests/ -v`，编号用 `test_*`，**禁止中文圈号**。
7. **DDW API 红色边界**：`importlib.import_module("plugins.ddw_esg_payment")` 是已验证可工作的模式（ddw_license_core 同结构）。可参考它的 `__init__.py` `plugin.py` `router.py` `models.py` `services.py` `schemas.py` 七件套。
8. **TASK_SPEC 是任务交付物**：用户原话"这要是交给开发,一定是浪费我的token!"——TASK_SPEC 必须自包含零歧义。

---

## 一、目录结构（精确到每个文件）

```
plugins/ddw_channel_auth/
├── manifest.yaml            # 插件元数据
├── __init__.py              # PLUGIN_NAME + VERSION（顶层常量）
├── plugin.py                # Plugin(PluginBase) 主类
├── router.py                # build_router() 返回 APIRouter
├── models.py                # SQLAlchemy 2.0 ORM（七张表）
├── schemas.py               # Pydantic 请求/响应模型（V1 至少 12 个）
├── services.py              # 业务逻辑（state machine + swap broadcast + POC report）
├── signature_adapters.py    # 5 家电子签适配器抽象 + V1 e签宝 stub
├── trial_poc.py             # 30 天试用 + POC 报告 docx/pdf 本地生成
├── README.md                # 中文说明（含资源声明）
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # 共享 fixtures（async db + http client）
│   ├── test_accounts.py
│   ├── test_claims.py
│   ├── test_license_codes.py
│   ├── test_payments.py
│   ├── test_signature_adapters.py
│   ├── test_trials.py
│   ├── test_one_level_redline.py
│   └── test_difficult_customers.py
```

---

## 二、Pydantic 模型（12 个，V1 必备）

```python
# schemas.py —— 必须实现
from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

# 1. 账号
class PartnerMeResp(BaseModel):
    id: int
    name: str
    type: str                                # "personal" / "company"
    parent_partner_id: Optional[int]
    banner_required: bool                    # 一级分销红线横幅未确认
    contract_signed_at: Optional[datetime]

class BannerSeenReq(BaseModel):
    ack_version: str                         # 前端传来的横幅版本

# 2. 报备
class ClaimCreateReq(BaseModel):
    company_full_name: str = Field(..., min_length=4, max_length=100)
    company_credit_code: str = Field(..., pattern=r"^[0-9A-HJ-NPQRTUWXY]{18}$")
    notes: Optional[str] = None

class ClaimResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_full_name: str
    company_credit_code: str
    partner_id: int
    state: str                               # claimed / contract_uploaded / contract_signed / paid / released / archived
    claimed_at: datetime
    contract_uploaded_at: Optional[datetime]
    paid_at: Optional[datetime]
    released_at: Optional[datetime]
    is_first_to_upload_contract: bool = False
    is_first_to_pay: bool = False

class ClaimHistoryItem(BaseModel):
    claim_id: int
    partner_name: str                        # 含蓄提示"难缠"时脱敏为"经销商 A"
    claimed_at: datetime
    outcome: str                             # won / released / pending

# 3. 电子签
class SignatureDispatchReq(BaseModel):
    provider: str                            # 严格枚举 5 家
    document_name: str
    signers: List[dict]                      # [{name, contact, role}]
    callback_url: str

class SignatureResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider: str
    status: str
    external_request_id: Optional[str]
    document_name: str
    completed_at: Optional[datetime]

# 4. 支付
class PaymentAutoVerifyReq(BaseModel):
    external_trade_no: str                   # 支付宝/微信返回
    amount_cents: int                        # 实收金额（分）
    quote_id: int                            # 关联报价单 ID
    channel: str                             # "alipay" / "wechat"
    signature: str                           # 第三方签名（V1 mock 校验）

class PaymentRecordResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    claim_id: int
    channel: str
    amount_cents: int
    quote_amount_cents: int
    verified: bool
    reconciled_by: Optional[int]
    reconciled_at: Optional[datetime]
    license_code_id: Optional[int]

# 5. 注册码 + 换码
class LicenseCodeIssueReq(BaseModel):
    license_id: int                          # 关联 ddw_license_core
    company_id: int

class LicenseCodeResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    license_id: int
    company_id: int
    deployment_fingerprint: Optional[str]
    activated_at: Optional[datetime]
    valid_to: Optional[date]
    is_current: bool
    swap_grace_until: Optional[datetime]
    revoke_status: str                       # active / grace_countdown / revoked

class SwapReq(BaseModel):
    new_license_id: int                      # 新许可证（已签发但未激活）

class BroadcastLogItem(BaseModel):
    node_id: str
    sent_at: datetime
    acked_at: Optional[datetime]

# 6. 试用
class TrialStartReq(BaseModel):
    plugin_id: str = Field(..., pattern=r"^ddw-[a-z][a-z0-9-]*$")

class TrialResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    plugin_id: str
    started_at: datetime
    expires_at: datetime
    days_remaining: int
    status: str
    poc_report_doc_path: Optional[str]
    poc_report_pdf_path: Optional[str]

class TrialMetricsResp(BaseModel):
    plugin_id: str
    invocation_count: int
    work_orders_processed: int
    estimated_hours_saved: float
    estimated_labor_cost_saved_cents: int
```

---

## 三、API 端点（30 个，逐一落地）

> 路径前缀：`/api/v1/plugins/ddw-channel-auth`

### accounts
- `GET /health`
- `GET /accounts/me`
- `POST /accounts/{partner_id}/banner/seen`
- `GET /accounts/banner/check`

### claims
- `POST /claims`
- `GET /claims`
- `GET /claims/{id}`
- `POST /claims/{id}/upload-contract`（multipart，PDF/JPG ≤10MB）
- `POST /claims/{id}/sign-auth-contract`
- `POST /claims/{id}/pay`
- `POST /claims/{id}/release`
- `GET /claims/{id}/history`
- `POST /difficult-customers/{company_id}/flag`

### signatures
- `GET /signatures/providers`
- `POST /signatures/dispatch`
- `GET /signatures/{id}`
- `POST /signatures/{id}/callback/{provider}`
- `POST /signatures/{id}/manual-upload`（multipart）

### payments
- `POST /payments/auto-verify`
- `GET /payments/pending-reconcile`
- `POST /payments/{id}/reconcile`

### license_codes
- `POST /license-codes/issue`
- `POST /license-codes/{id}/activate`
- `POST /license-codes/{id}/swap`
- `GET /license-codes/revoke-list`
- `POST /license-codes/{id}/re-activate`
- `GET /license-codes/{id}/broadcast-log`

### trials
- `GET /trials/available`
- `POST /trials/{plugin_id}/start`
- `GET /trials/me`
- `POST /trials/{plugin_id}/cancel`
- `POST /trials/{plugin_id}/generate-poc-report`
- `GET /trials/{plugin_id}/metrics`

### portal
- `GET /portal/banner`
- `GET /portal/dashboard`

---

## 四、核心逻辑（关键 Python 代码片段）

### 4.1 报备状态机服务（services.py）

```python
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from .models import ClaimRecord, CustomerAssignment

class ClaimService:
    """报备状态机 V1 实现：claim → contract → pay → 锁定 30 天或释放。"""

    CONTRACT_PRIORITY_DAYS = 7      # 0-7 天：合同优先
    LOCK_AFTER_PRIORITY_DAYS = 30   # 30 天无合同 → 释放

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_claim(self, partner_id: int, req: ClaimCreateReq) -> dict:
        """新建报备 + 同公司 7 天前已有报备 → 返回历史列表。"""
        existing = await self._find_existing_open_claims(req.company_credit_code)
        claim = ClaimRecord(
            partner_id=partner_id,
            company_full_name=req.company_full_name,
            company_credit_code=req.company_credit_code,
            state="claimed",
            claimed_at=datetime.utcnow(),
        )
        self.db.add(claim)
        await self.db.commit()
        return {"id": claim.id, "history": existing}

    async def mark_contract_uploaded(self, claim_id: int, pdf_path: str) -> dict:
        """上传合同 → 若在公司 7 天窗口内首个上传 = 锁定。"""
        claim = await self._get_claim(claim_id)
        # 铁律：contract_uploaded_at 非空 = 唯一锁定权（最早者）
        async with self.db.begin():
            claim.contract_uploaded_at = datetime.utcnow()
            claim.contract_pdf_path = pdf_path
            # 检查是否同公司 7 天内第一个上传
            existing = await self._find_same_company_claims_with_contract(
                claim.company_credit_code, before=claim.contract_uploaded_at
            )
            claim.state = "contract_uploaded"
            if not existing:
                claim.state = "contract_signed"  # 锁定
                await self._lock_customer(claim)
            await self.db.commit()
        return {"is_first_to_upload_contract": not existing}

    async def mark_paid(self, claim_id: int) -> dict:
        """付款到账 → 锁 + 自动发码。"""
        claim = await self._get_claim(claim_id)
        async with self.db.begin():
            claim.paid_at = datetime.utcnow()
            claim.state = "paid"
            await self._lock_customer(claim)
            await self.db.commit()
            # 自动发码（占位实现：业务侧由 license_codes 服务接管）
        return {"is_first_to_pay": True}

    async def release_expired(self, claim_id: int) -> dict:
        """30 天无合同 → 释放（DDW 定时任务调用）。"""
        claim = await self._get_claim(claim_id)
        async with self.db.begin():
            if claim.state in ("claimed",) and (
                datetime.utcnow() - claim.claimed_at
            ) > timedelta(days=self.LOCK_AFTER_PRIORITY_DAYS):
                claim.state = "released"
                claim.released_at = datetime.utcnow()
                await self.db.commit()
        return {"released": claim.state == "released"}
```

### 4.2 换码广播服务（services.py）

```python
class CodeSwapService:
    """注册码换码 + 网内广播。"""

    GRACE_DAYS = 7

    async def swap(self, old_code_id: int, req: SwapReq) -> dict:
        """换码流程：
        1. 新码生成（issue）
        2. 网内广播（mock：写入 broadcast log）
        3. 旧码标记 grace_countdown + 7 天倒计时
        4. 7 天后定时任务把旧码 → revoked
        """
        old = await self._get_code(old_code_id)
        new = await self._issue_new_code(req.new_license_id, old.company_id)
        broadcast = CodeSwapBroadcast(
            old_code_id=old.id,
            new_code_id=new.id,
            broadcast_at=datetime.utcnow(),
            grace_until=datetime.utcnow() + timedelta(days=self.GRACE_DAYS),
            ack_nodes=[{"node_id": "self", "sent_at": datetime.utcnow().isoformat()}],
        )
        async with self.db.begin():
            old.is_current = False
            old.revoke_status = "grace_countdown"
            old.swap_grace_until = broadcast.grace_until
            new.is_current = True
            new.revoke_status = "active"
            self.db.add(broadcast)
            await self.db.commit()
        return {
            "old_code_id": old.id,
            "new_code_id": new.id,
            "grace_until": broadcast.grace_until,
            "broadcast_id": broadcast.id,
        }
```

### 4.3 POC 报告本地生成（trial_poc.py）

```python
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from docx import Document
import io
import os

# 字体注册（macOS PingFang fallback to Linux Noto）
def _register_chinese_font():
    candidates = [
        ("PingFang", "/System/Library/Fonts/PingFang.ttc"),
        ("NotoSansCJK", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        ("WenQuanYi", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    ]
    for name, path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
                return name
            except Exception:
                continue
    raise RuntimeError("No Chinese font available for POC PDF rendering")

CHINESE_FONT = _register_chinese_font()

def render_poc_pdf(trial: "PluginTrial", metrics: dict) -> bytes:
    """生成 POC 报告 PDF（本地算法，不调 LLM）。"""
    buf = io.BytesIO()
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(buf, pagesize=A4)

    # 标题
    c.setFont(CHINESE_FONT, 18)
    c.drawString(72, 800, f"DDW 试用 POC 报告 — {trial.plugin_id}")
    c.setFont(CHINESE_FONT, 12)
    c.drawString(72, 770, f"试用时间: {trial.started_at.date()} → {trial.expires_at.date()}")

    # ROI 确定性公式
    invocation_count = metrics.get("invocation_count", 0)
    hours_saved_per_call = 0.25  # 每次调用节省 15 分钟人工
    hours_saved = invocation_count * hours_saved_per_call
    labor_cost_per_hour = 50  # 元
    cost_saved_cents = int(hours_saved * labor_cost_per_hour * 100)

    y = 730
    for line in [
        f"业务调用次数: {invocation_count}",
        f"节省工时: {hours_saved:.1f} 小时",
        f"替代人工成本: ¥{cost_saved_cents/100:.2f}",
        f"ROI = 节省金额 / 试用期间插件调用成本",
    ]:
        c.drawString(72, y, line)
        y -= 20

    # LLM 润色可选（占位：V2 实现）
    c.drawString(72, y - 20, "（本报告由本地算法生成；LLM 润色可选，开启后走客户自有 LLM 网关）")
    c.save()
    return buf.getvalue()


def render_poc_docx(trial: "PluginTrial", metrics: dict) -> bytes:
    """生成 Word 版 POC 报告。"""
    doc = Document()
    doc.add_heading(f"DDW 试用 POC 报告 — {trial.plugin_id}", 0)
    doc.add_paragraph(f"试用时间: {trial.started_at.date()} → {trial.expires_at.date()}")
    doc.add_heading("业务指标", 1)
    doc.add_paragraph(f"业务调用次数: {metrics.get('invocation_count', 0)}")
    doc.add_paragraph(f"节省工时: {metrics.get('estimated_hours_saved', 0):.1f} 小时")
    doc.add_paragraph(f"替代人工成本: ¥{metrics.get('estimated_labor_cost_saved_cents', 0)/100:.2f}")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

### 4.4 5 适配器电子签（signature_adapters.py）

```python
from abc import ABC, abstractmethod

class BaseSignatureAdapter(ABC):
    """电子签 provider 统一抽象。"""
    name: str

    @abstractmethod
    async def create_request(
        self, document_name: str, signers: list, callback_url: str
    ) -> dict:
        """返回：{external_request_id, sign_url?, expires_at}"""

    @abstractmethod
    async def verify_callback(self, payload: dict, signature: str) -> bool:
        """校验第三方回调签名。"""

    @abstractmethod
    async def fetch_signed_pdf(self, external_request_id: str) -> bytes:
        """下载已签 PDF。"""


class EsignAdapter(BaseSignatureAdapter):
    """e签宝适配器（V1 stub：仅返回 mock external_request_id）。"""
    name = "esign"

    async def create_request(self, document_name, signers, callback_url):
        return {
            "external_request_id": f"ESIGN-MOCK-{document_name[:20]}",
            "sign_url": f"https://open.esign.cn/sign/{document_name}",
            "expires_at": None,
        }

    async def verify_callback(self, payload, signature):
        # V1 mock 校验：开发期直接通过；V2 实现 RSA 验签
        return len(signature) > 0

    async def fetch_signed_pdf(self, external_request_id):
        return b"%PDF-1.4\n% mock e签宝 signed PDF\n"


class FadadaAdapter(BaseSignatureAdapter):
    name = "fadada"
    # 实现同上（占位 stub）


class TencentAdapter(BaseSignatureAdapter):
    name = "tencent"


class QiyuesuoAdapter(BaseSignatureAdapter):
    name = "qiyuesuo"
    # 私有化部署变体：通过内网 HTTP 调用而非公网


class ShangshangqianAdapter(BaseSignatureAdapter):
    name = "shangshangqian"


ADAPTERS = {
    cls.name: cls()
    for cls in [EsignAdapter, FadadaAdapter, TencentAdapter, QiyuesuoAdapter, ShangshangqianAdapter]
}
```

### 4.5 一级分销红线（plugin.py / router.py）

```python
# 在 services.py 或 router.py 中落实
async def create_sub_agent_attempt(db, parent_id):
    """铁律：禁止任何下级分销入口。"""
    raise HTTPException(
        status_code=403,
        detail="一级分销红线：禁止发展下级分销（DDW 渠道体系仅一级）"
    )
```

---

## 五、SQLAlchemy 2.0 ORM 模型（7 张表）

文件：`plugins/ddw_channel_auth/models.py`

继承 DDW 平台：
```python
from core.database.models import Base, TenantMixin, TimestampMixin
from sqlalchemy.orm import Mapped, mapped_column
```

7 张表（详见 PRD §四）：ChannelPartner, CustomerAssignment, ClaimRecord, DifficultCustomerFlag, SignatureRequest, PaymentRecord, LicenseCodeInstance, CodeSwapBroadcast, PluginTrial。

---

## 六、测试用例（10 条，pytest + httpx AsyncClient）

`tests/conftest.py`：
```python
import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from core.database.models import Base

@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def client(db):
    from plugins.ddw_channel_auth.router import build_router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(build_router(), prefix="/api/v1/plugins/ddw-channel-auth")
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
```

10 条测试用例：
1. `test_accounts_me_returns_partner_with_banner_required` — GET /health + /accounts/me
2. `test_claim_state_machine_transitions_claimed_to_paid` — 全链路
3. `test_claim_first_to_upload_contract_wins` — 同公司 7 天内有 2 个 claim，第二个上传不会抢到
4. `test_claim_first_to_pay_wins_in_release_window` — 释放后付款者得
5. `test_swap_broadcast_marks_old_code_grace_then_revoked` — 换码产生 grace_countdown
6. `test_payment_amount_mismatch_returns_422` — 金额不符
7. `test_trial_starts_30_days_full_features` — 试用期 30 天
8. `test_poc_report_generates_pdf_and_docx_locally` — PDF + DOCX 非空字节
9. `test_one_level_distribution_redline_blocks_subagent_creation` — 调 create_sub_agent → 403
10. `test_difficult_customer_flagged_when_threshold_reached` — 被报备 ≥3 次+跨度 >6 月自动标记

---

## 七、验收标准（任务完成判定）

### 必须通过（否则视为未完成）

1. `python3 -m py_compile plugins/ddw_channel_auth/{__init__,plugin,router,models,schemas,services,signature_adapters,trial_poc}.py` 全部 exit 0
2. `ruff check plugins/ddw_channel_auth/ --select=E,W,F` 0 errors（官方安全 auto-fix 允许：`ruff check --fix`）
3. `pytest plugins/ddw_channel_auth/tests/ -v` **10 passed**（独立计数；详见四件套）
4. `grep -c "config_schema" plugins/ddw_channel_auth/manifest.yaml` == 0（旧格式已淘汰）
5. `grep -c "engine: plugin_base" plugins/ddw_channel_auth/manifest.yaml` == 1
6. `grep -c "def build_router" plugins/ddw_channel_auth/router.py` == 1
7. `grep -c "PLUGIN_NAME" plugins/ddw_channel_auth/__init__.py` >= 1

### 完整性证据（落到交付记录）

- `pytest --collect-only` 独立计数 10 条
- `ruff check` 输出（清洁）
- 关键路由实测：curl /health 返回 JSON

---

## 八、约束与禁止

- **禁止**用红色圈号编号测试名（用 ASCII `1. 2. 3.`）
- **禁止**硬编码 API Key / 真实凭证
- **禁止**直接调任何云端 LLM API（POC 报告本地计算）
- **禁止**翻译调用 mimo / DeepSeek 的 API 调用（无 LLM 调用需求）
- **必须**所有文件 UTF-8 + 中文注释 + 中文业务命名（合作伙伴/客户/试用）
- **必须**`register(app)` 在 `__init__.py` 暴露（即便 V1 已用 `plugin.py` 内部类）

---

## 九、推送与提交

- 写完代码后 commit：`feat(channel-auth): v1.0.0 - 渠道授权与结算插件最小可用核心`
- 不推 GitHub（商业插件，红线）
- 不推 Gitea（用户未确认）
- 仅本地落盘 + PRD / 交付记录到位
