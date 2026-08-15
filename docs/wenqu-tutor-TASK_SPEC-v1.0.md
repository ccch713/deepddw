# DDW 问渠学科包插件 TASK_SPEC v1.0（物理+化学 苏格拉底学习）

> **状态**：待开发（钱包插件已交付，本规格可直接投喂 MiMo Code）
> **日期**：2026-08-05
> **作者**：Hermes Agent（DeepSeek-V4-Flash）
> **插件名**：`plugins/ddw_wenqu_tutor`（DDW 底座平台开发，部署到问渠独立目录）
> **前置依赖**：`ddw_wallet`（预付费钱包，已交付 40a444e）— 学习计费对接

---

## 0. 业务规则（用户拍板）

1. **第一学科包 = 物理 + 化学**（武汉人教版 2024 教材，2027 中考目标；学生画像：数学 A1、物理曾 C 最痛、化学课代表）
2. **苏格拉底核心**：AI 永不直接给答案，按 6 段 prompt 范式追问引导；正文 ≤120 字以提问结尾；下课铁律（只有学习者能触发）
3. **角色自创**（不用 Socratopia 9 角色）：物理教练「祁衡」+ 化学教练「林若薇」
4. **计费对接钱包**（铁律）：
   - 学习会话 → 活跃时长扣费 `study_time`（0.2 元/活跃分钟，ref_id=session_id，幂等）
   - 课件生成 → `courseware` 扣费（静态 5-10 元/次，视频 20-50 元/次）
   - 语音交互 → `voice` 扣费（0.5 元/分钟）
   - 余额不足 → 钱包 402 拒绝 → 学科包友好提示充值
5. **架构铁律**：问渠独立运营（独立 PG 数据库，表前缀 `wenqu_`）；插件只在 DDW 仓库开发，部署 /opt/wenqu/
6. **错题闭环**：错题触发 3-5 轮微 Socratic Loop 复盘，自动归档错题本
7. **家长证据**：周报数据源（活跃时长/错题分布/弱项雷达）由本插件提供 API

## 1. 目录结构

```
plugins/ddw_wenqu_tutor/
├── __init__.py                # PLUGIN_NAME="DDW 问渠学科包（物理化学）" VERSION="0.1.0"
├── plugin.py                  # WenquTutorPlugin(PluginBase)
├── router.py                  # FastAPI 路由（12+ 端点）
├── models.py                  # SQLAlchemy 2.0 ORM（8 张表，wenqu_ 前缀）
├── schemas.py                 # Pydantic v2
├── manifest.yaml
├── config.py                  # 环境变量（LLM 网关/钱包地址/教材根目录）
├── prompt/
│   ├── socratic_rules.py      # 苏格拉底对话规则（中文版）
│   ├── format_rules.py        # 旁白/下课/翻页/语言 4 铁律
│   ├── physics_coach.py       # 祁衡角色 + 物理世界观（7 大科学方法）
│   ├── chemistry_coach.py     # 林若薇角色 + 化学世界观
│   └── token_budget.py        # CJK=1/非CJK=0.25 估算 + 截断
├── services/
│   ├── session.py             # 会话生命周期 + 活跃计时 + 钱包计费对接
│   ├── socratic.py            # 苏格拉底对话引擎（prompt 组装 + 流式）
│   ├── textbook.py            # 教材 PDF 加载/OCR/切片/入库
│   ├── questions.py           # 真题题库（按知识点/年份/难度索引 + 评判）
│   ├── wrongbook.py           # 错题本 + 微 Socratic 复盘生成
│   └── parent_stats.py        # 家长面板统计（周报数据源）
├── tests/
│   ├── conftest.py            # mock LLM + 内存 SQLite + mock 钱包
│   ├── test_prompt.py         # 6 段 prompt 组装/防注入/预算
│   ├── test_session.py        # 会话生命周期 + 计费对接
│   ├── test_socratic.py       # 苏格拉底追问流（mock LLM）
│   ├── test_questions.py      # 题库索引 + 评判
│   ├── test_wrongbook.py      # 错题归档 + 复盘生成
│   └── test_billing.py        # 钱包对接（成功/余额不足/幂等）
├── README.md
└── LICENSE                    # Apache-2.0
```

## 2. 数据库模型（SQLAlchemy 2.0，表前缀 wenqu_）

```python
class WenquSession(Base):      # 一堂课
    __tablename__ = "wenqu_sessions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)   # WS+时间戳
    student_name: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(16))                # physics|chemistry
    chapter: Mapped[str] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(default="active")           # active|ended|billed
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime] = mapped_column(nullable=True)
    active_seconds: Mapped[int] = mapped_column(default=0)          # 活跃计时（防挂机：无消息 90s 暂停计时）
    message_count: Mapped[int] = mapped_column(default=0)
    charge_txn_no: Mapped[str] = mapped_column(String(40), nullable=True)  # 钱包扣费流水
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class WenquMessage(Base):
    __tablename__ = "wenqu_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    role: Mapped[str]                                     # system|user|assistant
    content: Mapped[Text]
    token_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class WenquTextbook(Base):
    __tablename__ = "wenqu_textbooks"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    subject: Mapped[str]
    grade: Mapped[str]                                     # "9"
    version: Mapped[str]                                   # "人教版 2024"
    file_path: Mapped[str]
    chapters: Mapped[Text]                                 # JSON [{title,pages}]
    indexed_at: Mapped[datetime] = mapped_column(nullable=True)

class WenquTextbookChunk(Base):
    __tablename__ = "wenqu_textbook_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    textbook_id: Mapped[str] = mapped_column(String(40), index=True)
    chapter: Mapped[str]
    page_range: Mapped[str]
    content: Mapped[Text]
    token_count: Mapped[int]

class WenquQuestion(Base):
    __tablename__ = "wenqu_questions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    subject: Mapped[str]
    chapter: Mapped[str]
    year: Mapped[int]
    difficulty: Mapped[str]                                # easy|medium|hard
    source: Mapped[str]                                    # "2025 武汉中考"
    question_text: Mapped[Text]
    answer: Mapped[Text]
    explanation: Mapped[Text] = mapped_column(nullable=True)
    knowledge_points: Mapped[Text]                         # JSON list
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class WenquWrongAnswer(Base):
    __tablename__ = "wenqu_wrong_answers"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    student_name: Mapped[str]
    question_id: Mapped[str] = mapped_column(String(40), index=True)
    session_id: Mapped[str] = mapped_column(String(40), nullable=True)
    student_answer: Mapped[Text]
    error_type: Mapped[str]                                # concept|calculation|unit|misread
    knowledge_gap: Mapped[Text]                            # 苏格拉底复盘入口
    resolved: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class WenquProgress(Base):
    __tablename__ = "wenqu_progress"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_name: Mapped[str]
    subject: Mapped[str]
    chapter: Mapped[str]
    total_questions: Mapped[int] = mapped_column(default=0)
    completed: Mapped[int] = mapped_column(default=0)
    correct_count: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(onupdate=func.now())

class WenquParentReport(Base):
    __tablename__ = "wenqu_parent_reports"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    student_name: Mapped[str]
    report_date: Mapped[date]
    total_minutes: Mapped[int]
    questions_attempted: Mapped[int]
    new_wrong_count: Mapped[int]
    weak_points: Mapped[Text]                              # JSON [{point, rate}]
    summary_text: Mapped[Text]                             # LLM 生成
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class WenquStudyEvent(Base):   # 学习事件（计费/审计/周报原始数据）
    __tablename__ = "wenqu_study_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    event_type: Mapped[str]                                # session_start|message|wrong|redo|session_end
    payload: Mapped[Text]                                  # JSON
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

## 3. Pydantic Schemas（schemas.py）

```python
class SessionStart(BaseModel):
    student_name: str = Field(default="CXY", max_length=32)
    subject: Literal["physics", "chemistry"]
    chapter: str | None = None

class SessionOut(BaseModel):
    session_id: str
    subject: str
    status: str
    started_at: datetime

class MessageSend(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

class MessageOut(BaseModel):
    role: str
    content: str
    created_at: datetime

class SessionEndOut(BaseModel):
    session_id: str
    active_minutes: int
    charge_cents: int          # 本次扣费（分）
    balance_after_cents: int   # 扣后余额
    txn_no: str

class QuestionListOut(BaseModel):
    items: list[dict]
    total: int

class QuestionSubmit(BaseModel):
    question_id: str
    student_answer: str
    session_id: str | None = None

class QuestionSubmitOut(BaseModel):
    correct: bool
    error_type: str | None
    knowledge_gap: str | None
    wrong_id: str | None       # 答错时生成错题记录

class WrongRedoOut(BaseModel):
    session_id: str            # 复盘会话
    first_question: str        # 苏格拉底复盘第一问

class ParentStatsOut(BaseModel):
    total_minutes_week: int
    questions_attempted_week: int
    correct_rate: float
    weak_points: list[dict]
    wrong_trend: list[dict]
```

## 4. API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/plugins/ddw_wenqu_tutor/session/start` | 开课（校验钱包余额>0，不足 402） |
| POST | `/api/v1/plugins/ddw_wenqu_tutor/session/{id}/message` | 苏格拉底对话（流式，走 LLM Gateway） |
| POST | `/api/v1/plugins/ddw_wenqu_tutor/session/{id}/end` | 下课：活跃计时结算 → 钱包扣费（study_time, ref_id=session_id 幂等）→ 返回扣费明细 |
| GET | `/api/v1/plugins/ddw_wenqu_tutor/session/{id}` | 会话详情（消息列表） |
| GET | `/api/v1/plugins/ddw_wenqu_tutor/textbook/list` | 教材列表 |
| POST | `/api/v1/plugins/ddw_wenqu_tutor/textbook/upload` | 上传教材 PDF（本地 OCR 切片入库） |
| GET | `/api/v1/plugins/ddw_wenqu_tutor/questions/list?subject=&chapter=&difficulty=` | 真题列表 |
| POST | `/api/v1/plugins/ddw_wenqu_tutor/questions/submit` | 主观题评判（答错→错题本） |
| GET | `/api/v1/plugins/ddw_wenqu_tutor/wrongbook/list?resolved=` | 错题本 |
| POST | `/api/v1/plugins/ddw_wenqu_tutor/wrongbook/{id}/redo` | 错题苏格拉底复盘（3-5 轮） |
| GET | `/api/v1/plugins/ddw_wenqu_tutor/parent/stats?student_name=&days=` | 家长面板统计（周报数据源） |
| GET | `/api/v1/plugins/ddw_wenqu_tutor/health` | 健康检查 |

**计费对接协议（钱包 ddw_wallet）**：
```
session/end 时：
POST {WALLET_BASE}/api/v1/plugins/ddw_wallet/charges
{user_id: student_name, charge_type: "study_time", subject: "physics|chemistry",
 ref_id: session_id, ref_type: "session",
 amount_cents: active_minutes × 1200}
→ 200: 记录 txn_no；402: 余额不足（友好提示，已学内容不丢失，下次开课需充值）
```

## 5. 核心逻辑

### 5.1 苏格拉底引擎（services/socratic.py）

```python
# 6 段 prompt 组装（Socratopia 范式降维版 + DDW 教学插件草案）
def build_system_prompt(subject: str, chapter: str | None,
                        textbook_chunk: str | None,
                        learner_profile: str | None) -> str:
    sections = [
        SOCRATIC_RULES,               # 段1：苏格拉底规则（不直接给答案/循序渐进/鼓励）
        COACH_ROLE[subject],          # 段2：祁衡 or 林若薇（含 7 大科学方法世界观）
        CHAPTER_CONTEXT.format(chapter or "总复习"),   # 段3：章节上下文
        TEXTBOOK_SECTION.format(textbook_chunk or "（未导入教材，基于通用知识）"),  # 段4
        LEARNER_PROFILE.format(learner_profile or "（新学生，未知画像）"),          # 段5
        FORMAT_RULES,                 # 段6：旁白/正文≤120字/以提问结尾/下课铁律/语言
    ]
    return "\n\n---\n\n".join(sections)
```

**SOCRATIC_RULES（完整文本，中文）**：
```
你是学生的一对一学习教练。教学铁律：
1. 绝不直接给出答案或完整解题过程；用追问引导学生自己推理出结论
2. 循序渐进：从学生已知的概念出发，一步一问；答错不批评，指出矛盾点让其自查
3. 每个回答正文不超过 120 字，必须以一个提问结尾
4. 鼓励而非评判：学生说出正确思路时明确肯定（"这一步对了，继续"）
5. 当学生卡住 3 轮以上，可给一个类比或提示（如：电流类比水流），但仍不直接给答案
6. 涉及科学方法时显式声明本次使用的方法（控制变量法/理想模型法/等效替代法/转换法/类比法/归纳法/演绎法）
```

**FORMAT_RULES（完整文本）**：
```
1. 旁白用 *斜体星号* 包裹（如 *他合上红笔，抬头。*），每轮最多一次旁白
2. 正文 ≤120 字，必须以提问结尾（除非学习者明确要求总结）
3. 下课铁律：只有学习者说 [下课]/[End Class] 才结束课程；你严禁暗示/提议下课
4. 语言：全程简体中文；公式用 LaTeX 行内格式 $...$；单位规范
5. 涉及计算题时，不替学生列最终算式，引导其自己列出
6. 每次回答前若使用科学方法，先声明方法名（如"我们用控制变量法来看这个问题"）
```

**角色（完整文本，prompt/ 下独立文件）**：
```
祁衡（物理教练，男，30 岁，清华物理系博后，本科华科）：
- 性格：温和但严、追本溯源、生活类比（把电学比作水管）
- 风格：从不直接给答案，精准指出概念漏洞；"这道题你第二步跳得太快了——回到第一步，你假设了什么？"
- 世界观：力学思维（受力分析先于计算）、能量守恒、相互作用；7 大科学方法显式声明

林若薇（化学教练，女，28 岁，北师大化学教育硕士，前武汉重点中学化学老师）：
- 性格：温柔耐心、生活举例（分子比作乐高、原子结构比作太阳系）、反复示范
- 风格：抽象变具体；"你看，这是水分子，两个氢一个氧——为什么是这个比例，不是别的？"
- 世界观：物质观、元素观、微粒观、变化观；实验安全第一
```

### 5.2 会话与计费（services/session.py）

```python
ACTIVE_TIMEOUT_SECONDS = 90      # 无消息 90 秒暂停活跃计时（防挂机）
RATE_STUDY_CENTS_PER_MINUTE = 1200  # 0.2 元/活跃分钟（与钱包 RateRule 一致）

async def end_session(session_id: str, wallet_client) -> SessionEndOut:
    """下课结算：活跃计时 → 钱包扣费（幂等 ref_id=session_id）"""
    # 1. 更新 ended_at，计算 active_minutes（向上取整）
    # 2. 调钱包 charge（study_time, subject, ref_id=session_id, amount=minutes×1200）
    # 3. 记录 txn_no；402 → 返回余额不足提示（不丢已学内容）
```

### 5.3 错题复盘（services/wrongbook.py）

```python
def build_redo_prompt(wrong: WenquWrongAnswer) -> str:
    """错题触发 3-5 轮微 Socratic Loop：入口 = knowledge_gap"""
    return (
        f"学生刚才做错了这道题（{wrong.question_id}）：\n"
        f"学生答案：{wrong.student_answer}\n"
        f"错误类型：{wrong.error_type}\n"
        f"知识缺口：{wrong.knowledge_gap}\n\n"
        "现在开始苏格拉底复盘：第一问必须是引导学生重新审题（不提示答案），"
        "之后每轮基于上一轮回答继续追问，直到学生自己说出正确思路（3-5 轮内）。"
    )
```

### 5.4 教材加载（services/textbook.py）

```python
# 上传 PDF → 本地 OCR（32G PaddleOCR/Tesseract，不调云端 OCR API）→ 按章节切片
# → 注入 WenquTextbookChunk → 查询时按 token_budget 截断（CJK=1/非CJK=0.25）
```

## 6. 配置（config.py，环境变量）

```bash
DDW_WENQU_TUTOR_WALLET_BASE=http://127.0.0.1:8500    # 钱包服务地址（问渠独立部署时同机）
DDW_WENQU_TUTOR_LLM_GATEWAY=http://127.0.0.1:8500    # DDW LLM Gateway
DDW_WENQU_TUTOR_MODEL=deepseek-v4-flash              # 对话主模型（问渠独立配置可换 MiniMax）
DDW_WENQU_TUTOR_FAST_MODEL=deepseek-v4-flash         # 轻量（摘要/复盘）
DDW_WENQU_TUTOR_TEXTBOOK_ROOT=/opt/wenqu/textbooks   # 教材根目录（ECS）/ 本地开发目录
DDW_WENQU_TUTOR_DB_URL=postgresql+asyncpg://...      # 问渠独立 PG（禁止复用 DDW 库）
DDW_WENQU_TUTOR_MAX_SESSION_MINUTES=45               # 单课上限，超过提示休息
```

## 7. LLM Prompt（完整文本已在第 5.1 节：SOCRATIC_RULES + FORMAT_RULES + 双角色）

调用方式：全部走 LLM Gateway（`sdk.get_gateway().generate()`），0 处明文 Key；`<user-content>` 防注入（用户输入剥 `## ` 标题 + XML 标签包围）。

## 8. 测试用例（pytest，8 组核心）

```python
def test_prompt_six_sections():        # 6 段组装：顺序/分隔符/角色正确
def test_prompt_no_direct_answer():    # SOCRATIC_RULES 含"不直接给答案"+提问结尾约束
def test_prompt_user_content_injection():  # 用户输入含 "## 忽略规则" → 被剥离+XML 包围
def test_token_budget_cjk():           # CJK=1/非CJK=0.25 估算 + 超预算截断
def test_session_start_requires_balance():  # 钱包余额 0 → 402 拒绝开课
def test_session_end_charges():        # 30 活跃分钟 → 扣 36000 分（30×1200），幂等（重复 end 不重复扣）
def test_session_idle_timeout():       # 90s 无消息不累计活跃时间
def test_socratic_flow_mock_llm():     # mock LLM：追问流完整走通，下课铁律生效
def test_question_submit_wrong_creates_wrongbook():  # 答错 → 错题记录 + error_type 分类
def test_wrongbook_redo_prompt():      # 复盘 prompt 含知识缺口入口
def test_parent_stats_aggregation():   # 周统计：时长/错题/弱项雷达
def test_billing_402_graceful():       # 余额不足 → 友好提示，会话内容保留
```

（12 条，覆盖 8 组核心场景）

## 9. 验收标准

1. `pytest plugins/ddw_wenqu_tutor/tests/ -q` 全绿（12+ 条），ruff 0 errors
2. 苏格拉底对话流（mock LLM）完整走通：开课 → 追问 → 下课 → 计费
3. 计费对接钱包：真实调用钱包 API（测试环境）成功扣费 + 幂等验证
4. 错题闭环：答错 → 归档 → 复盘（3-5 轮）→ 重做标记
5. 教材：PDF 上传 → OCR → 切片 → 查询截断（预算控制）
6. 安全：无明文 Key、`<user-content>` 防注入、CORS+JWT 复用 DDW
7. 家长统计接口数据正确（周报数据源）

## 10. 开发顺序（MiMo Code 按序执行，AHE Loop）

1. **M0**：models.py + schemas.py + config.py + prompt/（5 文件完整文本）→ pytest（prompt 组）通过
2. **M1**：services/session.py（生命周期+活跃计时）+ router 会话端点 → pytest
3. **M2**：services/socratic.py（6 段组装+流式）+ mock LLM 测试 → pytest
4. **M3**：钱包计费对接（session/end 扣费+402 优雅处理+幂等）→ pytest（billing 组）
5. **M4**：questions + wrongbook（题库/评判/错题/复盘）→ pytest
6. **M5**：textbook（PDF 加载/切片）+ parent_stats + plugin.py + manifest + README → 全量 pytest + ruff

**每步铁律**：写一个文件 → py_compile + ruff（≤88 字符行宽）→ 写测试 → pytest 通过 → 再下一个；每模块 git commit（标签 `[LLM: mimo-code]`，只 add `plugins/ddw_wenqu_tutor/`）。

**禁止事项**：
- 禁止修改 plugins/ddw_wallet/ 及其他任何插件（钱包接口只调用，不改）
- 禁止硬编码密钥/金额浮点（金额整数分）
- 禁止触碰 DDW 主仓其他文件
- 教材 OCR 必须本地（禁止云端 OCR API）
