# DDW AI 培训 V0.3 重写提示词（发给 16G 上的 MiniMax Code）

> 使用方式：复制以下内容到 16G 设备上 MiniMax Code 的对话窗口
> 这是一份**完整自包含**的提示词，MiniMax Code 无需额外上下文即可执行

---

## 任务

基于以下架构纠正，重写 DDW AI 培训的整体开发策划 V0.3。

## 纠正一：插件组合式架构（最高优先级）

DDW 已验证的插件组合式架构规范（见 `ddw-plugin-dev-workflow` §零）：

> **核心原则：每个插件是最小可用单元，客户的业务场景落地 = 多个插件的组合装配。**

参照 DDW 已验证的模式：
```
客户"AI 智能客服"部署 = 
  ddw-smart-cs（1 个核心插件）
  + ddw-adapter-dingtalk（配套适配器）
  + ddw-adapter-feishu（配套适配器）
  + ddw-cs-knowledge（配套知识库插件）
```

培训产品应该完全一样：**只有 1 个核心培训插件（ddw-training）+ 4 个配套插件**，不是 5 个独立的核心插件。

### 不要做的事（V0.2 的错误）

❌ DDW-Tutor、DDW-Subject、DDW-Training、DDW-EduSaaS、DDW-Parent 作为 5 个独立核心插件开发
❌ 按客户类型划分独立开发轨道
❌ DDW-Subject 里实现"上传课本 + 学科 prompt"，DDW-Training 里也实现"上传 SOP + 培训 prompt"（90% 重复）

### 正确的架构

✅ ddw-training 是唯一核心培训插件，处理所有教学逻辑
✅ "学科"（物理/化学/数学）和"年级"是 ddw-training 的 YAML 配置参数，不是独立插件
✅ "客户类型"的差异通过配套插件组合来实现，不重写培训引擎
✅ 配套插件通过 DDW EventBus v2 订阅 `training.*` 事件来解耦协作

## 纠正二：HRIS 和微信是平台底座能力，不是独立插件

DDW 平台底座已有：
- `core/events/event_bus_v2.py` — EventBus 支持通配符订阅（`training.*` 匹配所有培训事件）+ 幂等去重
- `core/im_adapters/` — BaseIMAdapter 基类，飞书/钉钉/企微已实现
- `ddw-adapter-registry` 插件 — 适配器注册中心

**HRIS 数据路由**（培训记录写入北森/用友/SAP）= 平台底座的适配器层能力（`core/hris_adapters/`），不是独立插件。ddw-training 只管发事件，HRIS 适配器由平台底座路由。

**微信服务号推送** = 新增 `core/im_adapters/wechat/adapter.py`，和飞书/钉钉/企微完全同级。不是独立插件。

### 修正后的插件组合矩阵

| 场景 | ddw-training | ddw-report | ddw-employee-roster | ddw-kpi | ddw-saas-billing |
|:---|:---:|:---:|:---:|:---:|:---:|
| A. 自家孩子（初三物理/化学） | ✅ | ✅ | — | — | — |
| B. 同学家长（C 端 SaaS） | ✅ | ✅ | — | — | ✅ |
| C. 企业（独立部署） | ✅ | ✅ | ✅ | ✅ | — |
| D. 企业（SaaS 订阅） | ✅ | ✅ | ✅ | ✅ | ✅ |

**平台底座负责**（不占插件开发资源）：
- HRIS 数据路由 → `core/hris_adapters/`（订阅 EventBus `training.*` 事件）
- 微信/飞书/钉钉/企微推送 → `core/im_adapters/`

## 纠正三：ddw-training 必须包含多媒体课件生成能力

这是最关键的纠正。ddw-training 不能只有苏格拉底文字对话——那是红海竞争。

**OpenMAIC 的核心能力**（已从源码验证）：

| 能力 | 说明 | 场景类型 |
|:---|:---|:---|
| 幻灯片生成 | PDF/教材 → 结构化 PPT（文字+图表+公式） | `slide` |
| 测验生成 | 单选/多选/简答题，自动评分 | `quiz` |
| 交互式仿真 | 自包含 HTML 页面（iframe），物理/化学实验模拟 | `interactive` |
| 项目式学习 | 完整 PBL 模块：角色、问题、协作（15-30 分钟） | `pbl` |
| 3D 可视化 | 3D 图表/模型渲染 | `visualization3d` |
| 游戏化内容 | 互动游戏（物理模拟器等） | `game` |
| 白板演示 | 教师画图、写公式、逐步揭示动画 | whiteboard |
| TTS 语音 | AI 教师朗读讲解 | speech |
| 图片/视频生成 | 配图、教学视频 | image/video |
| 多 Agent 编排 | Director 决定哪个 Agent 发言 | multi-agent |

**ddw-training 必须翻译这些能力为 DDW 插件规范**（不直接 fork OpenMAIC 的 Next.js 代码，而是把设计思想翻译成 Python/FastAPI + DDW EventBus 实现）。

### ddw-training 完整边界

```
ddw-training（唯一核心培训插件，PluginBase 继承）
│
├── 教学法内核（Socratopia）
│   ├── craft-your-textbook 6 阶段造书（extract→analyze→blueprint→generate→narrate→deliver）
│   ├── socratic-lens 4 维度教学审计（概念清晰度/推理深度/参与质量/教学法对齐度）
│   ├── 6 思维动作（观察→提问→假设→探究→评价→综合）
│   └── 12 图景（具体实例/类比/可视化图解/交互仿真/反例/历史脉络/解题演练/辩论/实验设计/概念地图/游戏挑战/现实应用）
│
├── ★ 多媒体课件生成器（翻译自 OpenMAIC）
│   ├── slide_generator.py      ← PDF/教材 → 结构化幻灯片
│   ├── quiz_generator.py       → 单选/多选/简答测验
│   ├── interactive_generator.py → 物理/化学交互式仿真（HTML iframe）
│   ├── pbl_generator.py        → 项目式学习模块
│   ├── viz3d_generator.py      → 3D 可视化
│   ├── game_generator.py       → 游戏化内容
│   ├── whiteboard_engine.py    → 白板绘图 + 动画逐步揭示
│   ├── tts_engine.py           → AI 教师语音讲解（走 DDW TTS 能力）
│   └── media_pipeline.py       → 图片/视频生成（走 DDW LLM Gateway）
│
├── 苏格拉底对话引擎
│   ├── socratic_engine.py      → 流式对话（走 DDW LLM Gateway）
│   └── history_manager.py      → 对话历史 + 学习记录
│
├── 评估引擎
│   ├── assessment_engine.py    → AI 出题 + 自动评分
│   ├── metrics_collector.py    → 学时计量（token → 学时）
│   └── audit.py                → socratic-lens 4 维度审计
│
├── 配置（YAML 驱动，不是代码分支）
│   ├── subjects/               → physics.yaml / chemistry.yaml / math.yaml / ...
│   ├── grade_levels/           → middle.yaml / high.yaml / ...
│   └── pedagogy/               → craft_your_textbook.yaml / socratic_lens.yaml / six_moves.yaml / twelve_vignettes.yaml
│
└── 事件发布（DDW EventBus v2）
    ├── training.session.started
    ├── training.session.completed
    ├── training.assessment.completed
    └── training.progress.updated
```

## 纠正四：Socratopia 教学法 YAML Schema

以下是 Socratopia 教学法的 4 个核心数据结构定义。**直接写入 ddw-training 的 config/pedagogy/ 目录。**

### craft-your-textbook 6 阶段

```yaml
# config/pedagogy/craft_your_textbook.yaml
name: craft-your-textbook
stages:
  - id: 1; name: extract;   display: "提取"; description: "从 PDF 提取文本/公式/图表/章节结构"
  - id: 2; name: analyze;   display: "分析"; description: "识别核心概念/学习目标/知识图谱/难度层级"
  - id: 3; name: blueprint; display: "蓝图"; description: "生成教学蓝图：6 思维动作 + 12 图景映射"
  - id: 4; name: generate;  display: "生成"; description: "生成多媒体课件：幻灯片+交互仿真+测验+PBL"
  - id: 5; name: narrate;   display: "配音"; description: "AI 教师语音讲解 + 白板演示动画"
  - id: 6; name: deliver;   display: "交付"; description: "编排课件序列 → 课堂模式（多 Agent 互动）"
```

### socratic-lens 4 维度

```yaml
# config/pedagogy/socratic_lens.yaml
name: socratic-lens
dimensions:
  - id: conceptual_clarity;    name: "概念清晰度";  weight: 0.30; desc: "学生是否真正理解核心概念"
  - id: reasoning_depth;       name: "推理深度";    weight: 0.30; desc: "思维是否从记忆上升到分析/评价/创造"
  - id: engagement_quality;    name: "参与质量";    weight: 0.20; desc: "学生是主动参与还是被动回答"
  - id: pedagogical_alignment; name: "教学法对齐度"; weight: 0.20; desc: "是否遵循 6 思维动作 + 12 图景结构化路径"
```

### 6 思维动作

```yaml
# config/pedagogy/six_moves.yaml
name: six-thinking-moves
moves:
  - {id: 1, name: observe,     display: "观察", prompt: "请仔细观察这个现象/图表，你注意到了什么？", level: remember}
  - {id: 2, name: question,    display: "提问", prompt: "关于你观察到的，你有什么疑问？", level: understand}
  - {id: 3, name: hypothesize, display: "假设", prompt: "根据已有知识，你认为可能的解释是什么？", level: apply}
  - {id: 4, name: investigate, display: "探究", prompt: "我们来设计一个实验/推理来验证你的假设", level: analyze}
  - {id: 5, name: evaluate,    display: "评价", prompt: "你的假设被验证了吗？证据支持还是反驳了你的想法？", level: evaluate}
  - {id: 6, name: synthesize,  display: "综合", prompt: "总结我们今天学到了什么，和之前的知识有什么联系？", level: create}
```

### 12 图景

```yaml
# config/pedagogy/twelve_vignettes.yaml
name: twelve-vignettes
vignettes:
  - {id: 1,  name: concrete_example,    display: "具体实例",   media: "slide+image",     best_for: "概念引入"}
  - {id: 2,  name: analogy,             display: "类比",       media: "slide",           best_for: "难点突破"}
  - {id: 3,  name: visual_diagram,      display: "可视化图解", media: "slide+diagram",    best_for: "因果关系"}
  - {id: 4,  name: interactive_sim,     display: "交互仿真",   media: "interactive",      best_for: "物理/化学实验"}
  - {id: 5,  name: counter_example,     display: "反例",       media: "slide+quiz",       best_for: "澄清误解"}
  - {id: 6,  name: historical_context,  display: "历史脉络",   media: "slide+tts",        best_for: "科学史"}
  - {id: 7,  name: problem_solving,     display: "解题演练",   media: "whiteboard+tts",   best_for: "考试准备"}
  - {id: 8,  name: debate,              display: "辩论",       media: "multi-agent",      best_for: "批判性思维"}
  - {id: 9,  name: experiment_design,   display: "实验设计",   media: "pbl",              best_for: "科学方法"}
  - {id: 10, name: concept_map,         display: "概念地图",   media: "interactive",      best_for: "知识整合"}
  - {id: 11, name: game_challenge,      display: "游戏挑战",   media: "game",             best_for: "巩固练习"}
  - {id: 12, name: real_world_app,      display: "现实应用",   media: "slide+video",      best_for: "学习动机"}
```

## 纠正五：16G Mac mini 不需要 Docker

DDW AI Hub v5.6 可以直接在 macOS 上用 Homebrew 原生运行：

```bash
brew install postgresql@16 redis python@3.11
brew services start postgresql@16
brew services start redis
createdb ddw_hub
cd ~/workspace/ddw-ai-hub
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**内存估算**：macOS(~3G) + PG(~200M) + Redis(~50M) + DDW(~500M) + 开发工具(~2.5G) = **~6.3GB**，剩余 ~9.7GB 充裕。比 Docker 方案省 1.5GB。

## 纠正六：DDW-Training 是差异化壁垒，不是红海产品

如果 ddw-training 只有"上传 PDF → 苏格拉底文字对话"，那就是市面上几十个"AI 辅导"产品的复制品。

**差异化壁垒 = 多媒体课件生成 + 教学法深度**：

| 维度 | 红海产品（多数） | DDW-Training（我们的） |
|:---|:---|:---|
| 输入 | 粘贴文字/PDF | 上传 PDF → 6 阶段造书全流程 |
| 输出 | 文字对话 | 幻灯片 + 交互仿真 + 测验 + PBL + 白板 + TTS + 3D + 游戏 |
| 教学法 | 通用苏格拉底 | Socratopia：4 维度审计 + 6 思维动作 + 12 图景 |
| 多 Agent | 无 | Director + 教师 Agent + 学生 Agent + 助手 Agent |
| 评估 | 简单对错 | socratic-lens 4 维度教学质量审计 |
| 学科适配 | 通用 prompt | 每学科独立 YAML 配置（prompt 模板 + 评估标准） |

## 输出要求

请基于以上 6 条纠正，重写 DDW AI 培训策划 V0.3。要求：

1. **只定义 1 个核心插件（ddw-training）+ 4 个配套插件（report / employee-roster / kpi / saas-billing）**
2. **ddw-training 的边界必须包含多媒体课件生成器**（slide/quiz/interactive/PBL/3D/game/whiteboard/TTS）
3. **HRIS 和微信推送标注为"平台底座能力"，不作为独立插件**
4. **Socratopia 4 个 YAML Schema 直接写入策划文档**
5. **16G 部署方案用 Homebrew 原生，不提 Docker**
6. **开发优先级按插件依赖关系排列，不按客户类型排列**
7. **必须遵守 DDW 插件规范**：PluginBase 继承、走 DDW LLM Gateway、禁止 LangChain/LlamaIndex、工具名以 ddw. 开头、EventBus v2 事件驱动
8. **文件保存到** `/Users/chenye/Documents/Obsidian Vault/_00_Inbox/2026-08-01_DDW-AI培训_整体开发策划_V0.3.md`
