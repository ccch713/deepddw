# TASK_SPEC：DDW AI 在线客服「自进化系统」

> 来源 PRD：`/Users/chenye/workspace/DDW底座平台/ddw-prd/PRD_客服自进化系统_v1.0_20260805.md`
> 目标插件：`plugins/ddw_online_cs/`（v1.0.0 → v1.1.0）
> 开发机：32G Mac mini（Python 3.9.6）；目标运行环境：ECS（Python 3.8+）

---

## 1. 铁律（最高优先级，违反即返工）

1. **不破坏现有客服主流程**：chat/upload/health 端点的行为、响应格式、prompt 结构不得改变。所有新增功能用 try/except 隔离，**任何失败都不影响用户对话**（只写 logger.warning）。
2. **Python 3.8+ 兼容**：所有新文件第一行 `from __future__ import annotations`；禁止 `list[...]`/`dict[...]` 内联泛型（用 `typing.List`/`typing.Dict`）；禁止 match-case、f-string 内嵌赋值等 3.10+ 语法。
3. **行宽 ≤88 字符**：所有代码行不超 88 字符。长 dict/subprocess 调用必须换行，一个 key 一行。
4. **不引入新依赖**：只用标准库 + 项目已有依赖（fastapi/pydantic/httpx/yaml）。LLM 调用用 `urllib.request`（脚本场景）或 httpx（异步场景）。
5. **Key 三源读取**：MiniMax API key 按顺序读：①环境变量 `DDW_MINIMAX_API_KEY` → ②`config/deployment.yaml` 的 `llm.providers.minimax.api_key` → ③`~/.hermes/config.yaml` 的 `providers.minimax-cn.api_key`。**key 永不打印、不落日志、不进 git**。
6. **文件读写失败降级**：日志/话术库/进化池的所有读写都 try/except，失败只告警不崩溃。
7. **每完成一个文件立即自检**：`py_compile` + `ruff check --select=E,W,F`，通过后才写下一个文件（边干边评，AHE 铁律）。全部完成后跑全量 pytest。

## 2. 项目背景

DDW AI Hub 的官网在线客服插件（ddw_online_cs）目前：会话只存内存不落盘、无洞察挖掘、话术写死在 router.py 的两段 prompt 中、无法打包交付。本次开发为其增加「自进化系统」：全量对话日志 → 每日 LLM 洞察 → 话术库 few-shot 注入 → 混合审核 → 资产包备份，让客服越用越像人、越用越会安抚，并形成可交付的「客服资产包」。

工作副本在 `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/`（git remote = gitea，分支 main）。

## 3. 交付物清单（文件级）

| 文件 | 动作 | 说明 |
|:--|:--|:--|
| `plugins/ddw_online_cs/log_store.py` | 新增 | 对话日志落盘（JSONL 追加写、按天切分、30 天轮转） |
| `plugins/ddw_online_cs/insights.py` | 新增 | 独立脚本：读日志 → LLM 评估 → 进化池 + 日报（可被 cron 调用） |
| `plugins/ddw_online_cs/curator.py` | 新增 | 混合审核：高置信自动入库 + 周审池管理 + 话术库淘汰 |
| `plugins/ddw_online_cs/asset_builder.py` | 新增 | 资产包构建（prompt+scripts+knowledge+config+README 打包 tar.gz） |
| `plugins/ddw_online_cs/router.py` | 修改 | ① chat 端点接入 log_store 落盘；② `_get_system_prompt` 增加 few-shot 注入 |
| `plugins/ddw_online_cs/manifest.yaml` | 修改 | config.optional 增加 5 个新配置项（见 §5） |
| `tests/test_online_cs_evolution.py` | 新增 | 进化系统测试（见 §6） |
| `plugins/ddw_online_cs/scripts/.gitkeep` | 新增 | 话术库目录占位（目录结构随 asset 打包） |

## 4. 开发顺序（严格依赖链）

**Step 1 — log_store.py**（无依赖）
**Step 2 — router.py 接入落盘 + manifest.yaml 新配置**（依赖 Step 1）
**Step 3 — insights.py**（依赖 Step 1 的日志格式）
**Step 4 — curator.py**（依赖 Step 3 的进化池格式）
**Step 5 — router.py few-shot 注入 + scripts/.gitkeep**（依赖 Step 4 的话术库格式）
**Step 6 — asset_builder.py + tests**（依赖全部）
**Step 7 — 全量自检**：py_compile 全部 + ruff 全部 + pytest 全过

每步完成后按铁律 7 立即自检，不通过不进入下一步。

## 5. 详细设计

### 5.1 log_store.py

```python
# 职责：追加写 JSONL，按天切分，保留 N 天
LOG_DIR = Path(__file__).resolve().parent / "logs"       # plugins/ddw_online_cs/logs/
RETENTION_DAYS = 30

def log_today_path() -> Path:            # logs/YYYY-MM-DD.jsonl
def append_chat(session_id, mode, user_msg, ai_reply, source, duration_ms, has_attachment): 
    # 组装 dict → json.dumps(ensure_ascii=False) → 追加写（mode='a', encoding='utf-8'）
    # 行格式：{"ts": ISO8601+08:00, "session_id", "mode", "user_msg", "ai_reply", "source", "duration_ms", "has_attachment"}
    # 任何异常 logger.warning 后 return，绝不 raise
def read_day(date_str) -> List[dict]:   # 读回某天全部行（用于 insights），文件不存在返回 []
def cleanup():                          # 删除超过 RETENTION_DAYS 的旧文件（启动时 + 每次 append 前抽样调用）
```

### 5.2 router.py 修改（Step 2：仅落盘）

在 `chat()` 端点 return 之前（`_log_feedback` 之后）加：

```python
try:
    from .log_store import append_chat
    append_chat(session_id, req.mode or "presales", message, answer, source,
                int((time.time() - _t0) * 1000), has_attachment=False)
except Exception as exc:
    logger.warning("ddw_online_cs: log_store append failed: %s", exc)
```

注意：`_t0` 在函数开头 `time.time()` 记录。**不改动** _ask_llm、_get_history、_append、_log_feedback、prompt 文本、ChatRequest/ChatResponse。

manifest.yaml config.optional 新增：

```yaml
    log_retention_days:
      default: 30
      description: "对话日志保留天数"
    script_top_k:
      default: 3
      description: "few-shot 话术注入条数（每分类）"
    auto_approve_threshold:
      default: 0.9
      description: "洞察自动入库置信度阈值"
    asset_version_prefix:
      default: "v1"
      description: "资产包版本前缀"
```

### 5.3 insights.py（独立脚本，CLI 可跑）

```python
# 用法：python3 insights.py --date 2026-08-05 [--minimax-key env]
# 流程：
# 1. 读 logs/<date>.jsonl（read_day）
# 2. 按 session_id 分组还原会话（user_msg + ai_reply 配对）
# 3. 每会话调 MiniMax-M3 评估（urllib 同步调用，max_tokens=400, temperature=0.2）
#    Prompt 要求严格 JSON 输出，解析失败重试 1 次，再失败跳过该会话（logger.warning）
# 4. 输出：
#    - evolution_pool/<date>.json      # 进化池（原始评估结果，curator 消费）
#    - daily_insights/<date>.md        # 人类可读日报（见 §5.3.2 格式）
# 全部 try/except：单个会话失败不影响其他会话；整个脚本失败退出码 0（cron 友好）
```

**5.3.1 评估 Prompt 要点**（写死在 insights.py 内）：

```
你是客服对话分析师。分析下面的客户-AI客服对话，输出严格 JSON：
{"type": "improvement|demand|praise|poor_answer|none",
 "confidence": 0.0-1.0, "summary": "≤30字", "evidence": "用户原话关键句",
 "suggestion": "改进建议或新需求描述（≤50字）"}
判定标准：
- improvement：用户表达不满/AI答错/功能缺陷/流程卡点（如"太慢""难用""报错""不对""失望"）
- demand：用户询问本产品没有的功能（如"有没有X""能不能做X""你们做X吗"）
- praise：用户明确满意/感谢/好评（如"谢谢""很好""满意"）
- poor_answer：AI答非所问/用户重复追问同一问题/AI回答与问题无关
- none：普通咨询、闲聊、价格问询等无价值内容
只输出 JSON，不要任何其他文字。
```

MiniMax 调用：`POST {api_base}/text/chatcompletion_v2`，headers `Authorization: Bearer {key}`，body `{"model": "MiniMax-M3", "messages": [...], "max_tokens": 400, "temperature": 0.2}`。api_base 默认 `https://api.minimaxi.com/v1`。响应取 `choices[0].text` 或 `choices[0].message.content`（双格式兼容，同 router.py 既有逻辑）。**必须剥离 `<think>...</think>`**（正则 `re.compile(r"<think>.*?</think>", re.DOTALL)`）。

**5.3.2 日报格式**（daily_insights/YYYY-MM-DD.md）：

```markdown
# 客服洞察日报 2026-08-05

- 会话总数：N ｜ 有效价值：N 条（改进 X / 需求 Y / 好评 Z / 差答 W）

## 一、产品改进点
1. [置信度] 摘要 — evidence
2. ...

## 二、新需求信号
1. [置信度] 摘要 — evidence

## 三、高满意回答（话术候选）
1. [置信度] 场景：摘要 — evidence

## 四、差回答诊断
1. 问题：... ｜ 建议：...

## 五、统计
- 命中话术分类分布：presales_emotion: n / ...
```

### 5.4 curator.py（混合审核）

```python
# 职责：消费 evolution_pool/<date>.json，产出话术库 + 待审池
SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"      # 话术库目录
PENDING_DIR = Path(__file__).resolve().parent / "pending_review"
CATEGORIES = ["presales_emotion", "presales_persuasion", "postsales_trouble",
              "postsales_complaint", "postsales_suggestion", "general_empathy"]
MAX_PER_CATEGORY = 5

# 分类规则（praise/poor_answer 按场景关键词映射到 CATEGORIES）：
#   "价格/贵/便宜/预算" → presales_emotion
#   "推荐/组合/选型/方案/行业" → presales_persuasion
#   "报错/怎么用/配置/安装/卡/失败" → postsales_trouble
#   "投诉/不满/垃圾/难用/退" → postsales_complaint
#   "建议/优化/希望/能不能" → postsales_suggestion
#   其他 praise → general_empathy

def process_day(date_str):
    # 读 evolution_pool/<date>.json
    # confidence >= auto_approve_threshold 且 type in (praise,) → 直接入库（status: auto_approved）
    #   写入 scripts/<category>.json：{"category", "title", "exemplar_qa": {"user","ai"}, "source_session", "approved_at", "hit_count": 0}
    #   入库前去重：同 session 同 evidence 不重复写；同分类已有相同 exemplar_qa.ai 跳过
    # type in (improvement, demand) → 写 evolution_pool/<date>.json 原样保留（供日报/周报消费），不自动入库
    # 其余 → 丢弃
    # 每分类超 MAX_PER_CATEGORY 时按 hit_count 淘汰最低（保留前 5）

def weekly_review_report() -> str:
    # 汇总 pending_review/ 全部待审条目 → markdown 报告（周审用，格式自定但含 编号/类型/evidence/建议）
    # 输出到 pending_review/weekly_YYYY-MM-DD.md

def apply_review(accept_ids: List[str], reject_ids: List[str]):
    # 接受 → 入话术库（同入库逻辑）；拒绝 → 删除条目
```

`scripts/<category>.json` 文件格式（数组，每元素一条）：

```json
[{"category": "presales_emotion", "title": "价格犹豫安抚",
  "exemplar_qa": {"user": "你们这个多少钱？有点贵", "ai": "理解您的考虑～DDW 是插件按需装配的……"},
  "source_session": "cs_1a2b3c", "approved_at": "2026-08-05", "hit_count": 12}]
```

### 5.5 router.py few-shot 注入（Step 5）

新增模块级函数（放 `_get_system_prompt` 之后）：

```python
_SCRIPT_CACHE: Optional[Dict[str, List[Dict]]] = None   # 话术库缓存（30s 内不重读）

def _load_scripts() -> Dict[str, List[Dict]]:
    # 读 scripts/*.json 全部分类；读取失败返回 {}；文件被修改后 30s 刷新（简单 mtime 缓存）
    # 注意：千万不要把 key/隐私写进日志

def _match_categories(mode: str, message: str) -> List[str]:
    # 按 §5.4 关键词规则返回命中的分类名列表（最多 2 个，优先 mode 匹配）
    # presales → 先查 presales_*；postsales → 先查 postsales_*

def _inject_scripts(system_prompt: str, mode: str, message: str) -> str:
    # 命中分类 → 每类取 top script_top_k 条（按 hit_count 降序）
    # 在 system_prompt 末尾追加：
    #   "\n\n【优秀回答范例（参考风格，不要照抄）】\n用户：{u}\n优秀回答：{a}\n"（每条一组）
    # 无命中/库空 → 原样返回 system_prompt（零影响）
```

`_get_system_prompt(mode, message="")` 签名改为接收 message 并调用 `_inject_scripts`；`chat()` 中调用处改为 `_get_system_prompt(req.mode or "presales", message)`。**prompt 模板文本本身一个字不改**。

### 5.6 asset_builder.py

```python
# 用法：python3 asset_builder.py [--out /path]
# 构建 ruiguo-ai-cs-assets-vX.Y.Z.tar.gz（版本号 = {prefix}.1.{YYYYMMDD}）
# 包含：
#   prompt/presales.txt  + prompt/postsales.txt      # 从 router.py 提取两段 prompt（运行时读源码字符串）
#   scripts/*.json                                    # 话术库全量
#   knowledge/company.md + knowledge/*.md             # 知识库
#   config.yaml                                       # {log_retention_days, script_top_k, auto_approve_threshold, mode注入开关}
#   README.md                                         # 部署说明：解压→填MiniMax key→启动；声明不含原始对话（隐私）
# 打包用 tarfile（gz）。输出目录默认 plugins/ddw_online_cs/dist/
# 铁律：打包内容绝不含 logs/、feedback/、pending_review/、evolution_pool/ 原始对话
```

### 5.7 tests/test_online_cs_evolution.py

用 pytest + 临时目录（tmp_path fixture，不污染真实 logs/scripts）：

| # | 测试 | 断言 |
|:--|:--|:--|
| 1 | log_store append + read_day 往返 | 内容一致、JSON 合法、ts 存在 |
| 2 | log_store 跨天文件分离 | 不同日期不同文件 |
| 3 | log_store cleanup 删旧留新 | 过期文件被删、新文件保留 |
| 4 | log_store 写失败不 raise | monkeypatch 只读目录 → append 返回 None 不抛 |
| 5 | _load_scripts 空目录返回 {} | scripts 空 → {} |
| 6 | _inject_scripts 无命中零影响 | 返回 == 原 prompt |
| 7 | _inject_scripts 命中注入 | 构造临时 scripts JSON → prompt 含"优秀回答范例" |
| 8 | _inject_scripts top_k 限制 | 分类 5 条时只注入 script_top_k 条 |
| 9 | curator 高置信自动入库 | 构造 evolution_pool 输入（confidence 0.95 praise）→ scripts 出现条目 |
| 10 | curator 低置信进待审池 | confidence 0.7 → scripts 不变、pending 有记录 |
| 11 | curator 分类封顶淘汰 | 6 条同分类 → 保留 5 条（hit_count 最低被淘汰） |
| 12 | curator 去重 | 同 evidence 两次入库 → 只 1 条 |
| 13 | asset_builder 打包 | tar.gz 存在、含 5 类内容、**不含 logs/feedback/pending** |
| 14 | asset_builder README 含隐私声明 | README 含"不含原始对话"或等价表述 |
| 15 | strip_think 复用 | insights 的清理函数正确剥离 `<think>..</think>`（构造样例） |

测试可以用 `monkeypatch` 把 log_store.LOG_DIR / curator.SCRIPTS_DIR 指到 tmp_path。**insights.py 的 LLM 调用不写进测试**（外部依赖），但可测其 JSON 解析函数（把解析逻辑抽成纯函数 `_parse_eval_json(text) -> dict`，LLM 返回的原始文本直接喂它）。

## 6. 质量标准（AHE 4-gate，每步必过）

```bash
# Gate 1: 全部新改文件 py_compile
python3 -m py_compile plugins/ddw_online_cs/log_store.py plugins/ddw_online_cs/insights.py plugins/ddw_online_cs/curator.py plugins/ddw_online_cs/asset_builder.py plugins/ddw_online_cs/router.py

# Gate 2: ruff（E/W/F 类 ≤3 警告；注意本机 ruff 路径可能需要 ~/Library/Python/3.9/bin/ruff）
ruff check plugins/ddw_online_cs/ tests/test_online_cs_evolution.py --select=E,W,F

# Gate 3: manifest YAML 合法 + 新配置存在
python3 -c "import yaml; d=yaml.safe_load(open('plugins/ddw_online_cs/manifest.yaml')); assert d['config']['optional']['auto_approve_threshold']"

# Gate 4: pytest（现有套件 + 新测试全过）
cd /Users/chenye/workspace/DDW底座平台/ddw-ai-hub && python3 -m pytest tests/ -q --tb=short
```

如果 ruff 不可用（command not found），用 `python3 -m ruff` 或 `~/Library/Python/3.9/bin/ruff`，都没有则跳过并在完成报告注明。

## 7. 自验证清单（完成前逐条执行）

```bash
grep -c "from __future__ import annotations" plugins/ddw_online_cs/log_store.py plugins/ddw_online_cs/insights.py plugins/ddw_online_cs/curator.py plugins/ddw_online_cs/asset_builder.py   # 期望各 1
grep -rn "list\[" plugins/ddw_online_cs/log_store.py plugins/ddw_online_cs/insights.py plugins/ddw_online_cs/curator.py plugins/ddw_online_cs/asset_builder.py   # 期望 0（禁止内联泛型）
grep -c "api_key" plugins/ddw_online_cs/insights.py          # 期望有（三源读取）
grep -rn "DDW_MINIMAX_API_KEY" plugins/ddw_online_cs/*.py    # 期望 2+（env 读取 + 引用）
grep -rn "logger.warning\|except Exception" plugins/ddw_online_cs/log_store.py  # 期望 try/except 存在
grep -c "优秀回答范例" plugins/ddw_online_cs/router.py       # 期望 1（注入模板）
awk 'length > 88 {print FILENAME": "NR}' plugins/ddw_online_cs/*.py tests/test_online_cs_evolution.py   # 期望无输出
```

## 8. 完成报告格式（最后输出）

```
## 完成报告
- 新增/修改文件列表（含行数）
- Gate 1-4 结果（py_compile/ruff/manifest/pytest 数字）
- 自验证清单逐条结果
- 遗留问题（如有）
- 建议的部署步骤（ECS 同步文件清单）
```

---

**开发完成后不要 commit**（Hermes 会审计后再提交）。只报告完成情况。
