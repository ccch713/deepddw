# Socratopia 教学法 YAML Schema

> 来源：2026-08-01 用户需求定义 + OpenMAIC 源码分析推导
> 用途：ddw-training 插件的教学法配置文件
> 路径：ddw-training/config/pedagogy/ 下的 4 个 YAML 文件

---

## 1. craft-your-textbook 6 阶段造书

```yaml
# config/pedagogy/craft_your_textbook.yaml
name: craft-your-textbook
version: "1.0"
description: "从教材 PDF → 结构化多媒体课件的 6 阶段造书流程"

stages:
  - id: 1
    name: extract
    display: "提取"
    description: "从 PDF/教材中提取文本、公式、图表、章节结构"
    input: raw_pdf
    output: structured_content
    tools: [pdf_parser, ocr_engine, formula_extractor]
    
  - id: 2
    name: analyze
    display: "分析"
    description: "识别核心概念、学习目标、知识图谱、难度层级"
    input: structured_content
    output: concept_map
    tools: [concept_extractor, bloom_taxonomy_classifier, difficulty_estimator]
    
  - id: 3
    name: blueprint
    display: "蓝图"
    description: "生成教学蓝图：6 思维动作 + 12 图景映射"
    input: concept_map
    output: teaching_blueprint
    tools: [six_moves_planner, twelve_vignettes_mapper]
    
  - id: 4
    name: generate
    display: "生成"
    description: "生成多媒体课件：幻灯片 + 交互仿真 + 测验 + PBL"
    input: teaching_blueprint
    output: multimedia_courseware
    tools: [slide_generator, interactive_generator, quiz_generator, pbl_generator]
    
  - id: 5
    name: narrate
    display: "配音"
    description: "为课件生成 AI 教师语音讲解 + 白板演示动画"
    input: multimedia_courseware
    output: narrated_courseware
    tools: [tts_engine, whiteboard_engine]
    
  - id: 6
    name: deliver
    display: "交付"
    description: "编排课件序列 → 课堂模式交付（多 Agent 互动）"
    input: narrated_courseware
    output: classroom_session
    tools: [director_agent, teacher_agent, student_agents]
```

## 2. socratic-lens 4 维度教学审计

```yaml
# config/pedagogy/socratic_lens.yaml
name: socratic-lens
version: "1.0"
description: "苏格拉底教学审计的 4 个维度——评估教学质量"

dimensions:
  - id: conceptual_clarity
    name: 概念清晰度
    weight: 0.30
    description: "学生是否真正理解了核心概念（不只是记忆）"
    metrics:
      - name: definition_accuracy
        description: "学生用自己的话准确解释概念的比例"
        threshold: 0.7
      - name: misconception_detection
        description: "教师识别并纠正学生误解的次数"
        threshold: 1
      - name: transfer_test
        description: "学生能否将概念应用到新场景"
        threshold: 0.6

  - id: reasoning_depth
    name: 推理深度
    weight: 0.30
    description: "学生的思维是否从记忆/理解上升到分析/评价/创造"
    metrics:
      - name: bloom_level_distribution
        description: "对话中 Bloom 各层级的分布（目标：分析/评价/创造 > 40%）"
        threshold: 0.4
      - name: evidence_chain_length
        description: "学生给出理由链的平均长度"
        threshold: 2
      - name: counterargument_rate
        description: "学生提出反驳或替代解释的频率"
        threshold: 0.1

  - id: engagement_quality
    name: 参与质量
    weight: 0.20
    description: "学生是主动参与还是被动回答"
    metrics:
      - name: student_initiated_questions
        description: "学生主动提问占比（vs 被动回答教师提问）"
        threshold: 0.3
      - name: curiosity_signals
        description: "好奇心信号（'为什么'、'如果...'、'那...'）的频率"
        threshold: 0.2
      - name: session_completion_rate
        description: "课件完成率（中途退出 = 参与度低）"
        threshold: 0.8

  - id: pedagogical_alignment
    name: 教学法对齐度
    weight: 0.20
    description: "教学是否遵循了 6 思维动作 + 12 图景的结构化路径"
    metrics:
      - name: six_moves_coverage
        description: "6 思维动作的实际覆盖比例"
        threshold: 0.8
      - name: vignette_diversity
        description: "使用的不同图景数量（目标：≥4/12）"
        threshold: 4
      - name: pacing_score
        description: "节奏评分：每个图景的停留时间是否合理"
        threshold: 0.6
```

## 3. 6 思维动作

```yaml
# config/pedagogy/six_moves.yaml
name: six-thinking-moves
version: "1.0"
description: "苏格拉底教学中的 6 个核心思维动作（对应 Bloom 认知层级）"

moves:
  - id: 1
    name: observe
    display: "观察"
    prompt_template: "请仔细观察这个现象/图表/公式，你注意到了什么？"
    cognitive_level: remember
    socratic_strategy: "引导学生从被动接受转为主动观察"
    
  - id: 2
    name: question
    display: "提问"
    prompt_template: "关于你观察到的，你有什么疑问？什么让你感到困惑？"
    cognitive_level: understand
    socratic_strategy: "鼓励学生提出自己的问题，培养好奇心"
    
  - id: 3
    name: hypothesize
    display: "假设"
    prompt_template: "根据你已有的知识，你认为可能的解释是什么？"
    cognitive_level: apply
    socratic_strategy: "让学生基于已有知识建立假设"
    
  - id: 4
    name: investigate
    display: "探究"
    prompt_template: "我们来设计一个实验/推理来验证你的假设"
    cognitive_level: analyze
    socratic_strategy: "引导学生通过实验或逻辑推理验证假设"
    
  - id: 5
    name: evaluate
    display: "评价"
    prompt_template: "你的假设被验证了吗？证据支持还是反驳了你的想法？"
    cognitive_level: evaluate
    socratic_strategy: "让学生面对证据，修正或坚持自己的观点"
    
  - id: 6
    name: synthesize
    display: "综合"
    prompt_template: "总结我们今天学到了什么，以及它和之前学过的知识有什么联系？"
    cognitive_level: create
    socratic_strategy: "帮助学生将新知识整合到已有知识体系中"
```

## 4. 12 图景

```yaml
# config/pedagogy/twelve_vignettes.yaml
name: twelve-vignettes
version: "1.0"
description: "苏格拉底教学中的 12 个知识呈现图景——决定每个知识点用什么方式讲"

vignettes:
  - id: 1
    name: concrete_example
    display: "具体实例"
    description: "用生活中的真实场景解释抽象概念"
    best_for: ["概念引入", "初学者"]
    media_type: slide+image
    
  - id: 2
    name: analogy
    display: "类比"
    description: "用学生已熟悉的事物类比新概念"
    best_for: ["难点突破", "跨学科关联"]
    media_type: slide
    
  - id: 3
    name: visual_diagram
    display: "可视化图解"
    description: "用图表/流程图/结构图呈现关系"
    best_for: ["系统性知识", "因果关系"]
    media_type: slide+diagram
    
  - id: 4
    name: interactive_simulation
    display: "交互仿真"
    description: "让学生动手操作仿真模型（调节参数看结果）"
    best_for: ["物理实验", "化学反应", "数学建模"]
    media_type: interactive
    
  - id: 5
    name: counter_example
    display: "反例"
    description: "展示'如果不是这样会怎样'"
    best_for: ["澄清误解", "深化理解"]
    media_type: slide+quiz
    
  - id: 6
    name: historical_context
    display: "历史脉络"
    description: "讲这个概念是怎么被发现/发明的"
    best_for: ["科学史", "激发兴趣"]
    media_type: slide+tts
    
  - id: 7
    name: problem_solving
    display: "解题演练"
    description: "逐步解一道典型题，展示思维过程"
    best_for: ["应用训练", "考试准备"]
    media_type: whiteboard+tts
    
  - id: 8
    name: debate
    display: "辩论"
    description: "让 AI 学生 Agent 持不同观点辩论"
    best_for: ["批判性思维", "多角度理解"]
    media_type: multi-agent
    
  - id: 9
    name: experiment_design
    display: "实验设计"
    description: "让学生设计一个实验来验证某个假设"
    best_for: ["科学方法", "探究能力"]
    media_type: pbl
    
  - id: 10
    name: concept_map
    display: "概念地图"
    description: "用思维导图呈现概念之间的关系网络"
    best_for: ["知识整合", "复习"]
    media_type: interactive
    
  - id: 11
    name: game_challenge
    display: "游戏挑战"
    description: "用游戏化方式检验掌握程度"
    best_for: ["巩固练习", "保持兴趣"]
    media_type: game
    
  - id: 12
    name: real_world_application
    display: "现实应用"
    description: "展示这个知识在工程/技术/生活中的真实应用"
    best_for: ["学习动机", "职业关联"]
    media_type: slide+video
```

---

## 使用方式

这 4 个 YAML 文件是 ddw-training 插件的配置文件。插件在启动时加载它们，用于：

1. **craft-your-textbook**: 控制从 PDF 到课堂的 6 阶段流水线
2. **socratic-lens**: 在每次课堂结束后，LLM 审计教学质量的 4 个维度
3. **six-thinking-moves**: AI 教师在对话中使用的 6 种提问策略
4. **twelve-vignettes**: AI 教师为每个知识点选择最佳呈现方式的决策依据

### 加学科示例

要新增一个学科（如高中物理），只需：
```yaml
# config/subjects/physics_high.yaml
name: physics_high
display: "高中物理"
grade_level: high
default_vignettes: [4, 7, 3, 1, 8]  # 优先使用交互仿真、解题演练、图解、实例、辩论
assessment_rubric:
  conceptual_clarity: 0.35  # 物理概念理解权重更高
  reasoning_depth: 0.30
  engagement_quality: 0.15
  pedagogical_alignment: 0.20
```

零代码改动，只需加一个 YAML 文件。
