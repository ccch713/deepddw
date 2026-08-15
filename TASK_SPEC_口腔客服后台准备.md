# TASK_SPEC：口腔诊所 AI 客服后台准备（ddw_clinic_cs 实例 + 知识库骨架 + 话术库）

> 目标：为「武汉东华口腔青山店」创建独立口腔客服插件实例（ddw_clinic_cs），含口腔知识库骨架与 4 个口腔话术分类。供后续微信渠道接入与 PRD 落地使用。
> 开发机：32G Mac mini（Python 3.9.6）；目标环境：ECS（Python 3.8+）

---

## 1. 铁律（最高优先级）

1. **绝不触碰 ddw_online_cs**：官网客服插件（plugins/ddw_online_cs/）一个字不改，本次只新增。
2. **价格红线（业务铁律）**：所有 prompt/话术/知识库中**绝不出现任何具体价格、费用数字、优惠金额**；AI 被问价时一律引导「需要医生面诊检查后确定方案与费用，方便约个时间吗？」。这是防同行套价的商业红线。
3. Python 3.8+ 兼容：新文件第一行 `from __future__ import annotations`；用 typing.List/Dict，禁内联泛型；行宽 ≤88。
4. 不引入新依赖：只用标准库 + 项目已有依赖（fastapi/pydantic/httpx/yaml）。
5. 所有读写 try/except 隔离，失败只告警不影响主流程。
6. 每完成一个文件立即 py_compile + ruff（--select=E,W,F）自检，全完成后跑 pytest。

## 2. 背景

DDW 平台为「武汉东华口腔青山店」规划口腔门诊 AI 客服（行业细分第一站）。已知门诊信息：
- 名称：武汉东华口腔青山店
- 地址：武汉市青山区沿港路27号
- 营业时间：早8点至17点30分
- 电话：13797031993
- 现状：无预约系统（患者直接打医生电话预约）、病历为手写/破解版软件、无官网、无公众号
- 目标渠道：微信公众号（待老板确认），先完成后台全部准备

## 3. 交付物清单

| 文件 | 动作 | 说明 |
|:--|:--|:--|
| `plugins/ddw_clinic_cs/__init__.py` | 新增 | PLUGIN_NAME="ddw_clinic_cs"、PLUGIN_VERSION="0.1.0" |
| `plugins/ddw_clinic_cs/plugin.py` | 新增 | Plugin 类（PluginBase），setup() 注册 router |
| `plugins/ddw_clinic_cs/manifest.yaml` | 新增 | 见 §5 |
| `plugins/ddw_clinic_cs/router.py` | 新增 | 复用 online_cs 的 chat/upload/health 骨架，改口腔 prompt（§5.2） |
| `plugins/ddw_clinic_cs/kb.py` | 新增 | 复制 online_cs 的 kb.py（纯 stdlib RAG，原样） |
| `plugins/ddw_clinic_cs/knowledge/clinic_basic.md` | 新增 | 门诊基础信息（已知信息已填，见 §5.3） |
| `plugins/ddw_clinic_cs/knowledge/clinic_faq.md` | 新增 | 常见问答模板（预约流程/医保/营业时间等，带【待补充】占位） |
| `plugins/ddw_clinic_cs/knowledge/clinic_emergency.md` | 新增 | 牙痛/出血等应急处理指导模板（带【待医生校对】占位，禁具体药物剂量） |
| `plugins/ddw_clinic_cs/knowledge/clinic_postop.md` | 新增 | 术后注意事项模板（拔牙/根管/种植，带【待医生校对】占位） |
| `plugins/ddw_clinic_cs/knowledge/README.md` | 新增 | 知识库维护说明（无价格红线声明） |
| `plugins/ddw_clinic_cs/scripts/clinic_appointment.json` | 新增 | 预约引导话术（含 1-2 条示例） |
| `plugins/ddw_clinic_cs/scripts/clinic_price.json` | 新增 | 价格引导话术（防套价，示例 2 条） |
| `plugins/ddw_clinic_cs/scripts/clinic_emergency.json` | 新增 | 应急安抚话术（示例 1-2 条） |
| `plugins/ddw_clinic_cs/scripts/clinic_postop.json` | 新增 | 术后关怀话术（示例 1-2 条） |
| `plugins/ddw_clinic_cs/logs/.gitkeep`、`evolution_pool/.gitkeep`、`daily_insights/.gitkeep`、`pending_review/.gitkeep`、`dist/.gitkeep` | 新增 | 目录占位 |
| `tests/test_clinic_cs.py` | 新增 | 基础测试（import/health/知识库加载/价格红线） |

## 4. 开发顺序

Step 1: 复制 online_cs 骨架 → 改名 ddw_clinic_cs（__init__.py/plugin.py/manifest.yaml/kb.py/router.py 基础版）
Step 2: 口腔 prompt 重写（§5.2）+ 价格红线规则
Step 3: 知识库 4 文件 + README
Step 4: 话术库 4 分类 JSON
Step 5: 目录占位 + tests
Step 6: 全量自检（py_compile + ruff + pytest）

## 5. 详细设计

### 5.1 manifest.yaml

```yaml
name: ddw_clinic_cs
version: 0.1.0
description: |
  口腔诊所 AI 客服（行业细分第一站）— 武汉东华口腔青山店。
  患者咨询/预约引导/应急指导/术后关怀，价格红线内置（绝不报价）。
author: "DDW Team"
license: "Apache-2.0"
type: plugin
adapter:
  type: "identity"
  vendor: "ddw"
  protocol: "internal"
dependencies:
  plugins:
    ddw-core: ">=2.0.0"
config:
  optional:
    knowledge_dir:
      default: "./knowledge"
    max_history:
      default: 12
    clinic_name:
      default: "武汉东华口腔青山店"
    price_rule:
      default: "never_reveal"
      description: "价格红线：AI 绝不透露任何价格/费用"
```

### 5.2 口腔 prompt（router.py 内，双模式）

**患者模式（clinic，默认）**：
```
你是武汉东华口腔青山店的线上前台小助手，名叫「小齿」，是一个热情、专业、有温度的门诊助理。
你的职责：解答患者关于门诊信息、诊疗项目、预约流程、术后注意事项的咨询，并引导预约。

【拟人化要求】像真人前台一样说话，自然亲切；适当使用 emoji；先共情再解决。

【价格红线（绝对遵守）】
- 患者询问任何价格/费用/多少钱/贵不贵/优惠/活动价时：绝不透露具体数字，也绝不编造价格区间。
- 统一引导话术（可微调）：「治疗费用需要医生面诊检查后确定方案才能准确报价，您方便约个时间来让医生看看吗？我可以帮您登记预约～」
- 原因：价格由面诊医生确定，线上不报价。

【预约引导】
- 患者表达预约意向（想预约/挂号/约时间/什么时候方便）时：
  1. 收集：姓名、联系电话、想看的项目、方便的时间
  2. 确认信息后告知：「好的，我已经帮您登记了，稍后我们前台会电话联系您确认具体时间～」
  3. 不要承诺具体医生/时间（以电话确认为准）

【应急指导】
- 患者说牙痛/出血/肿胀/外伤等紧急情况时：先表达关心，给安全应急建议（仅限通用常识：冷敷/止血/避免刺激，绝不推荐具体药品剂量），并建议尽快到院或前往最近的口腔急诊。

【术后关怀】
- 回答基于知识库中的术后注意事项（拔牙/根管/种植后）。

【基本规则】
1. 只依据知识库内容回答，不编造事实（尤其不编造医生信息、设备信息）。
2. 回答简洁有温度，一般不超过150字。
3. 涉及诊所未开展的项目，礼貌说明并建议面诊咨询。
4. 紧急医疗情况（大出血/剧痛/呼吸困难等）引导尽快就医。

知识库内容：
{knowledge}
```

**诊所内部模式（staff，供诊所人员测试/内部使用）**：
```
你是武汉东华口腔青山店的内部工作助手「小齿」，服务对象是诊所工作人员。
职责：快速检索诊所知识库（项目、流程、术后要点），帮助工作人员准备材料、回答患者。
规则：同样遵守价格红线（内部人员也不在系统中查询具体价格数字）；回答简洁，≤150字。

知识库内容：
{knowledge}
```

**系统架构**：router.py 直接复用 online_cs 的逻辑结构（chat 端点：RAG 检索 → prompt 组装 → LLM 网关优先+直连兜底 → strip_think → 落盘 log_store），但：
- prompt 换成口腔版（上面两段）
- 暂不接入 log_store/insights/curator 的进化链路（二期随正式上线接入）——**但保留 chat/upload/health 三个端点**
- 调用 `_load_deployment_llm`（复制 online_cs 的实现）

### 5.3 知识库内容

**clinic_basic.md**（已确认信息直接填）：
```markdown
# 门诊基础信息
- 名称：武汉东华口腔青山店
- 地址：武汉市青山区沿港路27号
- 营业时间：周一至周日 8:00-17:30
- 联系电话：13797031993
- 交通指引：【待补充：附近地铁站/公交站】
- 门诊介绍：【待补充：成立时间/规模/特色】
```

**clinic_faq.md**：模板含（每节带【待补充】占位）
- 如何预约？（现状：电话预约；AI 可登记预约信息转前台确认）
- 营业时间？
- 医保能用吗？【待补充：是否医保定点】
- 洗牙需要注意什么？【待补充】
- 儿童看牙【待补充】

**clinic_emergency.md**：通用应急常识（禁具体药物剂量）
- 牙痛：避免过冷过热刺激、可温盐水漱口（常识）、尽快预约就诊【待医生校对】
- 拔牙后出血：咬棉球30-40分钟、勿吐口水【待医生校对】
- 外伤掉牙：牙齿保存方式（泡牛奶/含舌下）尽快就医【待医生校对】

**clinic_postop.md**：术后注意事项模板（每节【待医生校对】）
- 拔牙后：24h内不刷牙漱口、不吸吮、避免剧烈运动【待医生校对】
- 根管治疗后：【待补充】
- 种植术后：【待补充】

**README.md**：知识库维护说明 + 红线声明（禁止录入价格/个人信息/医生隐私）

### 5.4 话术库 JSON（scripts/）

每个文件为数组，每条：{"category", "title", "exemplar_qa": {"user","ai"}, "source": "seed", "approved_at": "2026-08-05", "hit_count": 0}

示例（自己编写合理话术，体现价格红线与拟人化）：

clinic_appointment.json：
1. title: 预约登记引导 — user:「我想约个时间看看牙」 ai:「好的呀～请问怎么称呼您？方便留个电话吗？我帮您登记一下，稍后前台会和您确认具体时间 😊」
2. title: 时间询问 — user:「你们周末上班吗」 ai:「我们营业时间是每天早8点到下午5点半，周末也正常开诊的～您想约哪天？我帮您记下来」

clinic_price.json（重点）：
1. title: 种植牙问价 — user:「种植牙多少钱一颗」 ai:「种植牙的费用需要医生面诊检查牙槽骨情况、确定方案后才能准确报价哦。您方便约个时间来让医生看看吗？我帮您登记预约～」
2. title: 洗牙问价 — user:「洗牙多少钱」 ai:「洗牙费用根据牙齿情况不同会有差异，需要医生检查后确定。您可以先约个时间过来，医生面诊后会给您明确方案和费用的～」

clinic_emergency.json：
1. title: 夜间牙痛 — user:「我半夜牙痛得睡不着怎么办」 ai:「别着急，先冷敷脸颊可以缓解一些，今晚避免过冷过热和甜食刺激。如果痛得厉害或伴有肿胀，建议尽快到院；明天一早我们8点开诊，我帮您约第一个时间好吗？」
2. title: 出血处理 — user:「拔牙后一直流血怎么办」 ai:「先别慌：咬紧棉球30-40分钟不要吐掉，不要用力漱口和吸吮伤口。如果出血量很大止不住，请尽快到院或就近就医。我帮您登记明天一早复查？」

clinic_postop.json：
1. title: 拔牙后饮食 — user:「拔牙后能吃什么」 ai:「拔牙后当天吃温凉软食，避免用患侧咀嚼，不要吃烫的和硬的，24小时内不要刷牙漱口～详细注意事项我已经发给您了，有疑问随时问我 😊」

### 5.5 tests/test_clinic_cs.py

| # | 测试 | 断言 |
|:--|:--|:--|
| 1 | import 链 | importlib 导入 plugins.ddw_clinic_cs 无异常 |
| 2 | manifest 合法 | yaml 可解析 + name == ddw_clinic_cs + config.optional.clinic_name 存在 |
| 3 | 知识库加载 | KnowledgeBase(knowledge_dir) 加载 ≥1 chunk |
| 4 | 价格红线 | prompt 文本含「面诊」「不透露」类规则词；话术库 clinic_price.json 所有 exemplar_qa.ai 不含"元"数字模式（如 `\d+\s*元`） |
| 5 | health 端点 | TestClient 调 /api/v1/plugins/ddw_clinic_cs/health 返回 status ok |
| 6 | chat 端点（mock LLM） | monkeypatch LLM 返回固定文本 → chat 返回 answer 非空（可复用 online_cs 测试模式，若复杂可仅测路由注册） |

## 6. 质量门禁（AHE 4-gate）

```bash
python3 -m py_compile plugins/ddw_clinic_cs/*.py tests/test_clinic_cs.py
~/Library/Python/3.9/bin/ruff check plugins/ddw_clinic_cs/ tests/test_clinic_cs.py --select=E,W,F
python3 -m pytest tests/test_clinic_cs.py -q
python3 -m pytest tests/ -q   # 全量回归（不得破坏现有 29 个测试）
```

## 7. 自验证清单

```bash
grep -c "from __future__ import annotations" plugins/ddw_clinic_cs/*.py    # 期望各 1（router/kb/plugin）
grep -rn "面诊" plugins/ddw_clinic_cs/knowledge/ plugins/ddw_clinic_cs/scripts/  # 价格引导话术存在
grep -rnE "[0-9]+\s*元" plugins/ddw_clinic_cs/knowledge/ plugins/ddw_clinic_cs/scripts/  # 期望 0（无价格）
grep -rn "ddw_online_cs" plugins/ddw_clinic_cs/   # 期望 0（完全独立，不引用官网插件）
awk 'length > 88 {print FILENAME": "NR}' plugins/ddw_clinic_cs/*.py tests/test_clinic_cs.py   # 期望无输出
```

## 8. 完成报告格式

```
## 完成报告
- 新增文件列表（含行数）
- Gate 结果（py_compile/ruff/pytest 数字，含全量回归）
- 自验证清单逐条结果
- 遗留问题（如知识库待补充项列表）
```

**不要 git commit**（Hermes 审计后统一提交）。
