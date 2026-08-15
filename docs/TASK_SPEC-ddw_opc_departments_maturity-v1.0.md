# TASK_SPEC: ddw_opc_departments 升级 —— 新增「组织成熟度评估」模块

> 在现有11部门配置系统上新增10维度成熟度评估能力

## 1. 升级背景

Best Consulting的「AI原生组织」框架定义了10个组织变革维度。ddw_opc_departments已有组织契合度配置能力，需新增成熟度评估模块，让客户在配置部门的同时，能评估自己在10个维度上的成熟度，并获得DDW方案推荐。

## 2. 新增数据模型

```python
from pydantic import BaseModel
from typing import List, Optional

class DimensionScore(BaseModel):
    dimension_id: int          # 1-10
    dimension_name: str        # 维度名称
    score: int                 # 1-5
    description: str           # 用户选择的描述

class MaturityAssessment(BaseModel):
    id: Optional[str] = None
    tenant_id: str
    company_name: str
    assessor_name: Optional[str] = None
    scores: List[DimensionScore]  # 10个维度的评分
    total_score: int               # 总分 (10-50)
    level: str                     # 初始级/发展级/进阶级/领先级
    top_gaps: List[str]            # 差距最大的3个维度
    recommendations: List[str]     # DDW方案推荐
    created_at: Optional[str] = None

DIMENSIONS = [
    {"id": 1, "name": "组织设计起点", "traditional": "部门/岗位", "ai_native": "Outcome/能力/价值流"},
    {"id": 2, "name": "组织结构", "traditional": "固定部门树", "ai_native": "稳定核心+动态网络"},
    {"id": 3, "name": "工作主体", "traditional": "纯人工", "ai_native": "Human+Agent协同"},
    {"id": 4, "name": "岗位定义", "traditional": "职责集合", "ai_native": "Outcome Ownership"},
    {"id": 5, "name": "业务流程", "traditional": "人推动SOP", "ai_native": "Event-driven Agentic Workflow"},
    {"id": 6, "name": "权责分配", "traditional": "岗位权限", "ai_native": "Human-Agent Decision Rights"},
    {"id": 7, "name": "管理者角色", "traditional": "分任务/监督", "ai_native": "目标/系统/资源/例外管理"},
    {"id": 8, "name": "绩效评估", "traditional": "行为和任务", "ai_native": "业务结果+人机系统绩效"},
    {"id": 9, "name": "人才能力", "traditional": "专业技能", "ai_native": "专业×AI×判断×Orchestration"},
    {"id": 10, "name": "组织学习", "traditional": "培训+文档", "ai_native": "Human+Agent+Enterprise Memory"},
]

def calculate_level(total: int) -> str:
    if total <= 15: return "初始级"
    elif total <= 25: return "发展级"
    elif total <= 35: return "进阶级"
    else: return "领先级"

def get_recommendations(scores: List[DimensionScore]) -> List[str]:
    """根据评分差距推荐DDW方案"""
    gaps = sorted(scores, key=lambda s: 5 - s.score, reverse=True)[:3]
    rec_map = {
        1: "ddw_opc_departments（组织契合度配置）",
        2: "ddw_opc_departments（动态部门网络）",
        3: "DDW Pal（员工AI工作窗口）",
        4: "ddw_position_designer（人机协同岗位设计器）",
        5: "ddw_online_cs + Agentic Workflow（事件驱动工作流）",
        6: "ddw_position_designer（决策权限矩阵）",
        7: "ddw_sales_dashboard（管理决策看板）",
        8: "ddw_sales_dashboard（人机系统绩效看板）",
        9: "DDW Pal（AI能力赋能平台）",
        10: "知识库RAG + Enterprise Memory",
    }
    return [f"{g.dimension_name}（L{g.score}→L5）：{rec_map.get(g.dimension_id, 'DDW定制方案')}" for g in gaps]
```

## 3. 新增API端点

```yaml
POST /api/v1/plugins/ddw-opc-departments/assessments
  # 提交评估
  body: { company_name, assessor_name?, scores: [{dimension_id, score}] }
  response: MaturityAssessment (含level、top_gaps、recommendations)

GET /api/v1/plugins/ddw-opc-departments/assessments
  # 历史评估列表
  query: ?tenant_id=xxx&page=1&size=20
  response: { items: [MaturityAssessment], total: int }

GET /api/v1/plugins/ddw-opc-departments/assessments/{id}
  # 评估详情
  response: MaturityAssessment

GET /api/v1/plugins/ddw-opc-departments/assessments/{id}/export
  # 导出为HTML报告（含雷达图+条形图+方案推荐）
  response: HTML

GET /api/v1/plugins/ddw-opc-departments/dimensions
  # 返回10维度定义（供前端渲染问卷）
  response: [{ id, name, traditional, ai_native, levels: [{score, title, detail}] }]

GET /api/v1/plugins/ddw-opc-departments/health
  # 健康检查（已有，新增assessments_count字段）
  response: { "status": "ok", "departments": 11, "assessments_count": int }
```

## 4. 前端页面新增

### 4.1 评估问卷页（嵌入现有插件前端）
- 路由：`/assessment`
- 10个问题，每个5级评分
- 进度条 + 上一题/下一题导航
- 提交后跳转到结果页

### 4.2 评估结果页
- 综合评分 + 等级标签
- 雷达图（Chart.js）
- 条形图（各维度得分）
- 差距分析（每个维度：当前状态→目标状态→DDW方案）
- 推荐方案列表（Top3差距 + 对应DDW插件）
- 导出HTML报告按钮

### 4.3 与部门配置联动
- 评估结果中的推荐方案可一键跳转到对应插件配置
- 部门配置页新增「成熟度评估」标签页

## 5. 验收标准

1. 所有新增API端点正常响应
2. 评估问卷页可完成10维度打分
3. 结果页显示雷达图+条形图+方案推荐
4. 导出HTML报告可独立打开、可打印
5. 历史评估可查询
6. 与现有部门配置功能无冲突
7. `pytest` 全部通过
8. `ruff check` 无错误

## 6. 参考文件

- 成熟度评估HTML模板：`/Users/chenye/workspace/商务物料/AI原生组织评估/ai-native-maturity-assessment.html`
- 现有插件代码：`/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_opc_departments/`
- Best Consulting框架：Obsidian `_02_资产/07_AI智能体/DDW×Best_Consulting_AI原生组织10维度对照手册.md`
