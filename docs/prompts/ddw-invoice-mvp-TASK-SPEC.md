# TASK_SPEC: ddw_invoice MVP — 电子税务局手动开票 + DDW 托管

## 背景

锐果互动采用"电子税务局手动开票 + DDW 托管"的 MVP 方案：
1. 客户在 DDW 前台提交开票申请（填写抬头、税号、金额）
2. 锐果管理员在电子税务局手动开票，下载 PDF
3. 管理员在 DDW 后台上传 PDF
4. 客户在 DDW 前台自助下载发票

ddw_invoice 插件已有后端 API（8 个端点），但缺少：
- 客户自助下载的前端页面
- 开票信息预填（从企业主体自动填充）
- 发票状态变更通知（EventBus）
- 管理员批量上传功能

## 你是一个企业级 Python 全栈开发者

今晚你要为 DDW AI Hub 的 ddw_invoice 插件补充 MVP 功能。

## 技术栈

- Python >= 3.11, < 3.14
- FastAPI >= 0.110.0
- SQLAlchemy >= 2.0.30 (Async)
- pytest >= 8.0
- 前端：纯 HTML + CSS + JS（不引入 React/Vue/Angular）
- 禁止：LangChain / LlamaIndex / CrewAI

## 前端设计规范

```
锚点：Ant Design 企业 OA（泛微/蓝凌/帆软风格）
主色：#1890FF
深色导航：#001529
背景色：#F0F2F5
圆角：≤ 2px
字体：-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif

严格禁止：
❌ linear-gradient（渐变背景）
❌ box-shadow（阴影）
❌ emoji 图标（用 SVG 线条图标代替）
❌ 大圆角（>2px）
❌ AI-slop 词汇：赋能/助力/打造/闭环/护航/全方位/一站式
```

## 第零步：读取上下文（必做）

```
# 现有发票插件代码（必须完整读取）
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw_invoice/models.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw_invoice/router.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw_invoice/services.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw_invoice/schemas.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw_invoice/plugin.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw_invoice/__init__.py

# 现有前端页面参考
/Users/chenye/workspace/ddw-ai-hub/frontend/saas-register.html
/Users/chenye/workspace/ddw-ai-hub/frontend/saas-admin.html

# 企业主体插件（发票抬头来源）
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw_company_profile/models.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw_company_profile/services.py
```

---

## 任务清单

### 任务 1：完善 models.py — 增加通知和下载追踪字段

在 `Invoice` 模型中增加：

```python
# 通知追踪
notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
notification_method: Mapped[Optional[str]] = mapped_column(String(20))  # email/sms/none

# 下载追踪
download_count: Mapped[int] = mapped_column(Integer, default=0)
last_downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
last_downloaded_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

# 发票文件扩展信息
invoice_code: Mapped[Optional[str]] = mapped_column(String(50))  # 发票代码
invoice_check_code: Mapped[Optional[str]] = mapped_column(String(50))  # 校验码
file_type: Mapped[Optional[str]] = mapped_column(String(10))  # pdf/ofd/xml
file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
```

### 任务 2：完善 schemas.py — 增加客户侧 schema

```python
class InvoiceRequestByCustomerReq(BaseModel):
    """客户提交开票申请请求（简化版，从企业主体自动填充）。
    
    客户只需选择关联的订单/合同，系统自动从企业主体填充抬头和税号。
    """
    company_id: int = Field(..., description="关联客户企业 ID")
    order_id: Optional[int] = Field(None, description="关联订单 ID")
    invoice_type: str = Field("normal", description="发票类型：special/normal")
    amount: Decimal = Field(..., ge=0, description="金额（不含税）")
    tax_amount: Decimal = Field(..., ge=0, description="税额")
    total_amount: Decimal = Field(..., ge=0, description="价税合计")
    notes: Optional[str] = Field(None, description="特殊要求（如邮寄地址）")

class InvoiceDownloadResp(BaseModel):
    """发票下载响应。"""
    invoice_id: int
    invoice_no: Optional[str]
    invoice_url: str
    file_type: str  # pdf/ofd/xml
    file_size_bytes: Optional[int]
    download_url: str  # 带签名的临时下载链接
```

### 任务 3：完善 router.py — 增加 4 个新端点

```python
# 3.1 客户提交开票申请（简化版，自动填充抬头）
@router.post("/invoices/request", response_model=dict, status_code=201)
async def request_invoice(data: InvoiceRequestByCustomerReq):
    """客户提交开票申请。
    
    - 从 company_id 自动读取发票抬头和税号
    - 创建 Invoice 记录，status=requested
    - 发布 EventBus 事件 invoice.requested
    """

# 3.2 客户获取自己的发票列表
@router.get("/invoices/my", response_model=InvoiceListResp)
async def list_my_invoices(
    company_id: int = Query(..., description="企业 ID"),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """客户查看自己的发票列表。
    
    - 只返回 company_id 匹配的发票
    - 按 created_at 降序
    """

# 3.3 客户下载发票（带下载计数）
@router.get("/invoices/{invoice_id}/download")
async def download_invoice(invoice_id: int):
    """客户下载发票文件。
    
    - 只允许 status=issued 的发票
    - 增加 download_count
    - 返回 invoice_url（MVP 阶段直接返回 URL，不做签名链接）
    """

# 3.4 管理员批量上传发票文件
@router.post("/invoices/batch-upload", response_model=dict)
async def batch_upload_invoices(files: list, invoice_ids: list):
    """管理员批量上传发票文件并关联到多个开票申请。
    
    - 支持同时上传多个 PDF
    - 每个 PDF 关联到一个 invoice_id
    - 批量更新 status=requested → issued
    """
```

### 任务 4：完善 services.py — 增加业务逻辑

```python
# 4.1 客户开票申请（自动填充抬头）
async def request_by_customer(self, data: InvoiceRequestByCustomerReq) -> Dict:
    """从企业主体自动填充发票抬头和税号。"""
    company = await self.db.get(Company, data.company_id)
    if not company:
        raise ValueError(f"企业 {data.company_id} 不存在")
    
    invoice = Invoice(
        company_id=data.company_id,
        order_id=data.order_id,
        invoice_type=data.invoice_type,
        amount=data.amount,
        tax_amount=data.tax_amount,
        total_amount=data.total_amount,
        invoice_title=company.invoice_title or company.name,
        tax_id=company.tax_id or company.credit_code,
        status="requested",
    )
    self.db.add(invoice)
    await self.db.commit()
    await self.db.refresh(invoice)
    return _invoice_to_dict(invoice)

# 4.2 客户发票列表
async def list_by_company(self, company_id: int, status: Optional[str], page: int, page_size: int) -> InvoiceListResp:
    """按企业 ID 查询发票列表。"""
    conditions = [Invoice.company_id == company_id]
    if status:
        conditions.append(Invoice.status == status)
    
    stmt = select(Invoice).where(and_(*conditions)).order_by(Invoice.created_at.desc())
    count_stmt = select(func.count()).select_from(Invoice).where(and_(*conditions))
    
    total = (await self.db.execute(count_stmt)).scalar() or 0
    offset = (page - 1) * page_size
    items = (await self.db.execute(stmt.offset(offset).limit(page_size))).scalars().all()
    
    return InvoiceListResp(
        total=total, page=page, page_size=page_size,
        items=[InvoiceResp.model_validate(i) for i in items]
    )

# 4.3 下载计数
async def record_download(self, invoice_id: int, user_id: Optional[int]) -> str:
    """记录下载并返回 invoice_url。"""
    inv = await self.db.get(Invoice, invoice_id)
    if not inv or inv.status != "issued":
        raise ValueError("发票不存在或未开具")
    inv.download_count = (inv.download_count or 0) + 1
    inv.last_downloaded_at = datetime.now(timezone.utc)
    inv.last_downloaded_by = user_id
    await self.db.commit()
    return inv.invoice_url
```

### 任务 5：前端页面 — 客户发票自助下载页

创建 `/Users/chenye/workspace/ddw-ai-hub/frontend/invoice-portal.html`

功能：
- 左侧深色导航栏（DDW 风格）
- 发票列表（卡片式，显示：发票号、类型、金额、状态、开票日期）
- 状态筛选（全部/待开票/已开票/已作废）
- "申请开票"按钮（弹出表单：选择企业、填写金额、选择类型）
- "下载"按钮（已开具的发票可下载 PDF）
- 统计概览（总发票数、待开票、已开票、总金额）

### 任务 6：前端页面 — 管理员发票管理增强

在现有 admin 页面中增加：
- 批量上传发票文件功能
- 开票申请列表（待处理/已处理）
- 一键关联发票文件到申请
- 客户开票信息查看

### 任务 7：测试

测试用例（≥10 个）：
1. 客户提交开票申请（自动填充抬头）
2. 客户提交开票申请（企业不存在 → 404）
3. 客户发票列表（分页）
4. 客户发票列表（按状态筛选）
5. 客户下载发票（已开具）
6. 客户下载发票（未开具 → 400）
7. 管理员上传发票文件
8. 管理员批量上传
9. 下载计数递增
10. 统计概览（含新字段）

### LOOP 自循环质量保障

```bash
cd plugins/ddw_invoice

# 语法检查
python3 -m py_compile models.py router.py services.py schemas.py plugin.py __init__.py

# 代码风格
ruff check . --select=E,W,F

# 测试
pytest tests/ -v --tb=short

# 修复后重复，直到全部通过
```

---

## 交付物汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| models.py | 修改 | 增加通知/下载/文件扩展字段 |
| schemas.py | 修改 | 增加 InvoiceRequestByCustomerReq, InvoiceDownloadResp |
| router.py | 修改 | 增加 4 个新端点 |
| services.py | 修改 | 增加 request_by_customer, list_by_company, record_download |
| tests/test_invoice.py | 修改 | 增加 ≥10 个测试用例 |
| frontend/invoice-portal.html | 新建 | 客户发票自助下载页 |
| README.md | 更新 | 补充新端点说明 |

## 注意事项

- Python 版本是 3.9.6（16G）/ 3.14（32G），代码需兼容 3.9+
- 使用 `from __future__ import annotations` 在文件第一行
- 不要使用 `int | None` 语法，用 `Optional[int]`
- 不要使用 `datetime.UTC`，用 `datetime.timezone.utc`
- 前端页面严格遵守 Ant Design OA 风格
- 不要在代码中暴露 API Key、个人订阅信息
