# TASK_SPEC: KB-E ebook-distill 方法论蒸馏引擎（内嵌 DDW 知识库）

> **版本**：v1.0
> **日期**：2026-08-11
> **预计工作量**：3 人天
> **目标**：把 ebook-distill 的 RIA-TV++ 方法论（五类提取+三重验证+RIA++六段构造）做成 DDW 知识库的可调用 API，让企业上传文档后自动产出"可执行的方法论 skill"，而非简单摘要。
> **上游文档**：Obsidian `_02_资产/05_知识蒸馏/华为韬定律二次蒸馏A-B对比报告-20260811.md`（A/B 测试证明 RIA-TV++ 形态完胜普通笔记）
> **开发方式**：MiMo Code CLI（`~/.mimocode/bin/mimo`），完成后独立验证（pytest + ruff + 契约检查）

---

## E.1 功能概述

在 `ddw_knowledge_hierarchy` 插件中新增 **方法论蒸馏引擎**（methodology distill engine）：用户上传文档（规章制度/岗位SOP/流程规范/产品手册/案例/电子书）后，系统按 RIA-TV++ 流水线产出：

1. **五类候选提取**：框架/原则/案例/反例/术语（每个带原文引用+出处）
2. **三重验证筛选**：V1跨域 / V2预测力 / V3独特性 → verified + rejected（附原因）
3. **RIA++ 六段构造**：R(原文≤150字)/I(改写)/A1(书中案例)/A2(触发场景)/E(执行步骤)/B(边界) → 每个方法论单元一个 skill 卡片
4. **入库**：skill 卡片存入知识库（可检索、可引用、可被 Pal 调用）

**差异化定位**：竞品知识库都是"存文档+搜段落"；DDW 是"提炼方法论+可执行"。

## E.2 数据模型

```python
# 新增表：kh_distill_jobs（蒸馏任务）
class KhDistillJob(Base):
    __tablename__ = "kh_distill_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False)  # 源文档
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # status: queued | extracting | verifying | constructing | completed | failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

# 新增表：kh_methodology_units（方法论单元 = skill 卡片）
class KhMethodologyUnit(Base):
    __tablename__ = "kh_methodology_units"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    distill_job_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    unit_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # unit_type: framework | principle | case | counter_example | glossary
    title: Mapped[str] = mapped_column(String(256), nullable=False)  # 方法论名称
    trigger_words: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # A2 触发词
    r_section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # R 原文引用(≤150字)
    i_section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # I 方法论骨架
    a1_section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # A1 书中案例
    e_section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # E 执行步骤
    b_section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # B 边界
    v1_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    v2_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    v3_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="verified")
    # status: verified | rejected
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_chapter: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

## E.3 API 端点设计

### E.3.1 POST /distill/methodology/start — 启动方法论蒸馏任务

**请求**：
```json
{
    "knowledge_base_id": 1,
    "document_id": "doc-xxx",
    "strict_mode": true
}
```
- `strict_mode: true` = 三重验证严格模式（淘汰率 40-60% 属正常）；`false` = 宽松模式（全部保留）

**响应**（201）：
```json
{
    "job_id": "a1b2c3d4-...",
    "status": "queued",
    "document_id": "doc-xxx",
    "knowledge_base_id": 1,
    "estimated_steps": 4
}
```

**处理逻辑**：
1. 验证 document_id 属于该知识库且用户有权限
2. 创建 KhDistillJob（status=queued）
3. 异步执行流水线（BackgroundTasks 或 asyncio.create_task）
4. 返回 job_id

### E.3.2 GET /distill/methodology/{job_id} — 查询蒸馏进度

**响应**：
```json
{
    "job_id": "a1b2c3d4-...",
    "status": "extracting",
    "progress": 45,
    "phase_detail": "五类提取完成 3/5 (framework/principle/case)",
    "units_count": 12,
    "verified_count": 5,
    "rejected_count": 7
}
```

### E.3.3 GET /distill/methodology/{job_id}/units — 获取方法论单元列表

**响应**：
```json
{
    "items": [
        {
            "id": "unit-1",
            "unit_type": "framework",
            "title": "τ优先诊断法",
            "trigger_words": "性能瓶颈、找瓶颈、慢在哪",
            "v1_passed": true,
            "v2_passed": true,
            "v3_passed": true,
            "status": "verified"
        }
    ],
    "total": 6
}
```

### E.3.4 GET /distill/methodology/units/{unit_id} — 单元详情（RIA++ 六段全文）

### E.3.5 POST /distill/methodology/units/{unit_id}/reject — 人工驳回单元（可捞回）

### E.3.6 GET /distill/methodology/units?status=rejected — 被淘汰单元（含原因，支持捞回）

## E.4 核心逻辑 — 蒸馏流水线

```
distill_document(document_id, strict_mode):
    阶段1 五类提取（并行/串行 LLM 调用）:
        prompt 模板见 services/distill_prompts.py
        每类提取候选单元（title + 原文引用 + 出处章节）
    阶段1.5 三重验证:
        对每个候选单元，LLM 判定 V1/V2/V3:
        V1 跨域: 文档中≥2个独立段落有佐证?
        V2 预测力: 能回答文档没明说的新问题?
        V3 独特性: 不是任何聪明人都说的常识?
        strict_mode=False 时 V3 可放宽
        通过 → verified；不通过 → rejected + reject_reason
    阶段2 RIA++ 构造:
        对每个 verified 单元，LLM 生成六段:
        R 原文引用(≤150字) / I 改写骨架 / A1 文档案例 / A2 触发词 / E 1-2-3步骤 / B 边界
    阶段3 入库:
        写入 kh_methodology_units，完成 job
```

**LLM 网关调用**：走 DDW 现有 LLM 网关（Token 广场），默认 MiniMax-M3 或平台配置模型。`max_tokens` 建议 ≥8000（M3 think 吃预算，见记忆铁律）。

## E.5 文件清单

```
plugins/ddw_knowledge_hierarchy/
├── distill_router.py          # 新增：蒸馏端点（E.3.1-E.3.6）
├── services/
│   ├── distill_pipeline.py    # 新增：蒸馏流水线编排（E.4）
│   ├── distill_prompts.py     # 新增：五类提取+三重验证+RIA++ 的 prompt 模板
│   └── distill_llm.py         # 新增：LLM 调用封装（异步、重试、JSON解析）
├── models.py                  # 修改：+ KhDistillJob + KhMethodologyUnit
└── plugin.py                  # 修改：注册 distill_router
```

## E.6 测试用例（8条）

1. `test_distill_start` — 启动任务返回 job_id，DB 有记录
2. `test_distill_progress` — 查询进度，状态转换正确
3. `test_distill_units_list` — 完成后单元列表返回，含 verified/rejected 统计
4. `test_distill_unit_detail` — 单元详情含 RIA++ 六段
5. `test_distill_reject_unit` — 人工驳回后 status=rejected
6. `test_distill_permission` — 无权限用户访问其他租户 job 被拒（403）
7. `test_distill_document_not_found` — document_id 不存在返回 404
8. `test_distill_pipeline_mock` — mock LLM 返回，流水线从 queued→completed，单元入库

## E.7 验收标准

- [ ] pytest 8/8 通过 + ruff clean
- [ ] 端点按契约返回（{items,total} 信封）
- [ ] 租户隔离：job/unit 都带 tenant_id 且查询强制校验
- [ ] LLM 失败时 job 进入 failed 状态（非静默挂起），可重试
- [ ] 六段结构完整性校验：verified 单元必须 R/I/A1/A2/E/B 六段齐全，缺段自动重试一次
- [ ] prompt 模板支持中文文档
- [ ] 前端无需改动（本批只做后端，前端由 KB-C 另行开发）
