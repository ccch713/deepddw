# OpenMAIC 多媒体课件生成架构（DDW 翻译参考）

> 来源：2026-08-01 对 OpenMAIC 源码 `/Users/chenye/OpenMAIC/lib/prompts/` 的完整分析
> 用途：为 ddw-training 插件的多媒体课件生成器提供设计参考
> 许可证：OpenMAIC 开源项目，设计思想可参考，代码需用 Python/FastAPI 全新实现

---

## 一、OpenMAIC 核心能力矩阵

| 能力 | 场景类型 | prompt 模板 | 输出格式 | DDW 翻译方案 |
|:---|:---|:---|:---|:---|
| 幻灯片生成 | `slide` | `slide-content/system.md` | PPT 页面（文字+图表+公式） | slide_generator.py |
| 测验生成 | `quiz` | `quiz-content/system.md` | 单选/多选/简答 | quiz_generator.py |
| 交互式仿真 | `interactive` | `simulation-content/system.md` + `interactive-outlines/system.md` | 自包含 HTML iframe | interactive_generator.py |
| 项目式学习 | `pbl` | `pbl-design/system.md` + `pbl-actions/system.md` | 完整 PBL 模块（角色/问题/协作） | pbl_generator.py |
| 3D 可视化 | `visualization3d` | `visualization3d-content/system.md` | 3D 图表/模型 | viz3d_generator.py |
| 游戏化内容 | `game` | `game-content/system.md` | 互动游戏（物理模拟器等） | game_generator.py |
| 代码演示 | `code` | `code-content/system.md` | 代码片段+运行结果 | code_generator.py |
| 图表/流程图 | `diagram` | `diagram-content/system.md` | Mermaid/图表 | diagram_generator.py |

## 二、多 Agent 编排架构

OpenMAIC 的 Director prompt（`director/system.md`）定义了课堂内的多 Agent 路由：

| Agent 角色 | 职责 | DDW 翻译 |
|:---|:---|:---|
| **Teacher** | 主讲教师，回答问题、讲解概念 | 主 Agent（socratic_engine.py） |
| **Student (AI)** | AI 学生，提问、补充、不同视角 | EventBus 路由的子 Agent |
| **Assistant** | 助手，辅助解释、记笔记 | EventBus 路由的子 Agent |
| **Student (Human)** | 真实用户 | 用户输入 |
| **Director** | 决定下一个发言者 | multi_agent.py 的路由逻辑 |

**Director 关键规则**（从 prompt 提取）：
1. 用户提问必须由 Teacher 回答（规则 13 覆盖所有其他规则）
2. 不重复已发言的 Agent（规则 3）
3. 角色多样性：Teacher → Student → Assistant → Teacher（规则 Routing Quality）
4. 讨论推进：explain → question → deeper explanation → different perspective → summary
5. 话题完成时输出 END（规则 4）
6. 白板状态影响路由决策（规则 8-9）

## 三、白板引擎

`agent-system-wb-teacher/system.md` 定义了白板教学的关键模式：

| 功能 | 说明 | DDW 翻译 |
|:---|:---|:---|
| 元素绘制 | 1-3 个元素/轮，保守使用 | whiteboard_engine.py |
| 动画逐步揭示 | step1 → delete → step2（不一次性画完） | animated_reveal |
| 代码演示 | `wb_draw_code` + `wb_edit_code`（增量编辑） | code_whiteboard |
| 布局冲突检测 | 重叠 > 30% 时必须先删再画 | layout_manager |
| 白板生命周期 | 不要在讲解结束时关闭白板（学生需要阅读时间） | lifecycle_rules |

## 四、课件生成流程（requirements-to-outlines）

`requirements-to-outlines/system.md` 定义了从需求到课件大纲的生成流程：

### 输入
- 用户自由文本需求（"创建一个关于量子力学的入门课堂"）
- 可选 PDF 内容
- 可选语言设置（默认 zh-CN）
- 可选功能开关（webSearch / imageGeneration / videoGeneration / TTS）

### 处理
1. **语言推断**：从需求文本推断教学语言
2. **场景大纲生成**：结构化 SceneOutline 序列
3. **默认假设**：课程时长 15-20 分钟、目标受众 = 通用学习者、风格 = 互动

### 输出
```json
{
  "scenes": [
    {
      "type": "slide",
      "title": "...",
      "content": "...",
      "duration": "1-3min"
    },
    {
      "type": "interactive",
      "title": "...",
      "simulation": "HTML iframe content"
    },
    {
      "type": "quiz",
      "questions": [...]
    },
    {
      "type": "pbl",
      "title": "...",
      "duration": "15-30min",
      "roles": [...],
      "issues": [...]
    }
  ]
}
```

## 五、TTS 语音讲解

`speech-guidelines.md` 定义了语音讲解规则：
- 教师 Agent 的讲解应自然、口语化
- 避免读出 Markdown 标记
- 重要公式/定义用稍慢语速强调
- DDW 翻译：走 DDW LLM Gateway 的 TTS 能力

## 六、DDW 翻译要点

| OpenMAIC 实现 | DDW 翻译方案 |
|:---|:---|
| Next.js + React 19 | FastAPI + Jinja2 模板（或 Vue SPA 作为独立前端） |
| LangGraph 状态机 | DDW EventBus v2 事件驱动 |
| TypeScript prompt 模板 | Python f-string + YAML 配置 |
| Vercel 部署 | DDW 插件规范（PluginBase 继承） |
| BYOK（自带 API Key） | DDW LLM Gateway（统一管理） |
| 多 Agent 路由（Director） | multi_agent.py + EventBus publish/subscribe |

## 七、差异化壁垒分析

| 维度 | 红海产品（多数 AI 辅导） | DDW-Training（差异化） |
|:---|:---|:---|
| 输入 | 粘贴文字/PDF | 上传 PDF → 6 阶段造书全流程 |
| 输出 | 纯文字对话 | 幻灯片 + 交互仿真 + 测验 + PBL + 白板 + TTS + 3D + 游戏 |
| 教学法 | 通用苏格拉底 | Socratopia：4 维度审计 + 6 思维动作 + 12 图景 |
| 多 Agent | 无 | Director + Teacher + Student + Assistant |
| 评估 | 简单对错 | socratic-lens 4 维度教学质量审计 |
| 学科适配 | 通用 prompt | 每学科独立 YAML 配置 |
