# TASK_SPEC: ddw_position_designer 插件 v1.0

> 人机协同岗位设计器 —— 从传统JD升级为四维设计

## 1. 插件信息

| 项 | 值 |
|----|-----|
| 插件名 | ddw_position_designer |
| 目录名 | ddw_position_designer |
| 版本 | 1.0.0 |
| 优先级 | P0 |
| 来源 | Best Consulting「AI原生组织」第3张PPT——岗位从JD转向四维设计 |

## 2. 产品定位

传统岗位说明书（JD）描述「过程动作」（负责客户开发、负责CRM录入），AI原生岗位设计描述「结果+责任+协同+权限」四维组合。

核心公式：**岗位 = Outcome × 人的责任 × Agent Stack × Decision Rights**

## 3. 数据模型

```python
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class DecisionType(str, Enum):
    AUTO = "auto"          # Agent自动执行
    SUGGEST = "suggest"    # Agent建议，人确认
    HUMAN = "human"        # 人工决策
    ESCALATE = "escalate"  # 升级审批

class DecisionRight(BaseModel):
    scenario: str          # 业务场景（如"常规报价"）
    human_right: str       # 人类权限（如"审批/监督"）
    agent_right: str       # Agent权限（如"自动生成/执行"）
    decision_type: DecisionType  # 决策类型

class PositionDesign(BaseModel):
    id: Optional[str] = None
    tenant_id: str
    name: str                          # 岗位名称
    department: Optional[str] = None   # 所属部门
    report_to: Optional[str] = None    # 汇报对象
    # 维度1: Outcome
    outcomes: List[str] = []           # 业务结果列表
    # 维度2: 人的责任
    human_responsibilities: List[str] = []  # 人的责任列表
    # 维度3: Agent Stack
    agent_stack: List[str] = []        # Agent组合列表
    # 维度4: 决策权限
    decision_rights: List[DecisionRight] = []  # 决策权限矩阵
    # 维度5: 能力标准（v2.0新增）
    human_capability: Optional[str] = None     # 人类核心能力要求
    agent_capability: Optional[str] = None     # Agent能力边界
    handoff_protocol: Optional[str] = None     # 人机交接协议
    # 维度6: 风险管控（v2.0新增）
    risk_controls: List[str] = []              # 风控措施列表
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
```

## 4. API端点

```yaml
POST /api/v1/plugins/ddw-position-designer/positions
  # 创建岗位设计
  body: PositionDesign
  response: PositionDesign (含id)

GET /api/v1/plugins/ddw-position-designer/positions
  # 列表（按tenant_id过滤）
  query: ?department=销售部&page=1&size=20
  response: { items: [PositionDesign], total: int }

GET /api/v1/plugins/ddw-position-designer/positions/{id}
  # 详情
  response: PositionDesign

PUT /api/v1/plugins/ddw-position-designer/positions/{id}
  # 更新
  body: PositionDesign
  response: PositionDesign

DELETE /api/v1/plugins/ddw-position-designer/positions/{id}
  # 删除
  response: { ok: true }

GET /api/v1/plugins/ddw-position-designer/positions/{id}/export
  # 导出为HTML（与静态模板一致的格式）
  response: HTML

GET /api/v1/plugins/ddw-position-designer/health
  # 健康检查
  response: { "status": "ok", "positions_count": int }

GET /api/v1/plugins/ddw-position-designer/config
  # 返回配置（决策类型枚举、默认Agent列表等）
  response: { decision_types: [...], default_agents: [...] }
```

## 5. 前端页面

### 5.1 岗位列表页
- 表格：岗位名、部门、Outcome数量、Agent数量、创建时间
- 操作：编辑、删除、导出HTML
- 新建按钮

### 5.2 岗位设计器页（核心）
- 四栏表单布局（参考已有HTML模板 `/Users/chenye/workspace/商务物料/人机协同岗位设计/human-agent-position-designer.html`）
- 左上：Outcome（动态列表，可增删）
- 右上：人的责任（动态列表）
- 左下：Agent组合（动态列表，下拉可选已注册Agent）
- 右下：决策权限矩阵（表格，含场景/人类权限/Agent权限/决策类型下拉）
- 底部：实时预览区 + 导出按钮

### 5.3 与ddw_opc_departments联动
- 在部门配置中可查看该部门下所有岗位设计
- 岗位设计中的Agent列表自动关联已注册的DDW插件

## 6. 核心逻辑

### 6.1 Agent推荐
根据岗位所属部门，自动推荐可调度的Agent：
```python
AGENT_RECOMMENDATIONS = {
    "销售部": ["CRM Agent", "数据分析 Agent", "客服 Agent"],
    "客服部": ["在线客服 Agent", "工单 Agent", "知识库 Agent"],
    "财务部": ["发票 Agent", "应收预警 Agent", "报表 Agent"],
    "生产部": ["巡检 Agent", "排产 Agent", "质量检测 Agent"],
}
```

### 6.2 决策类型默认值
根据业务场景自动建议决策类型：
```python
DEFAULT_DECISION_TYPES = {
    "报价": "suggest",      # Agent建议，人确认
    "客户投诉": "suggest",  # Agent建议，人确认
    "数据录入": "auto",     # Agent自动
    "合同签署": "human",    # 人工决策
    "退款审批": "escalate", # 升级审批
}
```

## 6. DDW生态集成点（v2.0新增）

```yaml
集成点清单:
  ddw_opc_departments:
    方向: "双向同步"
    数据: 岗位所属部门→部门下岗位列表
    触发: 部门配置变更时自动刷新岗位列表

  DDW_Pal:
    方向: "岗位设计器 → Pal"
    数据: Agent Stack配置→Pal可调度Agent列表
    触发: 岗位创建/更新时同步Agent配置

  ddw_sales_dashboard:
    方向: "双向同步"
    数据: Outcome↔OKR/KPI指标映射
    触发: 绩效周期开始时自动拉取Outcome

  ddw_online_cs:
    方向: "岗位设计器 → 客服"
    数据: Decision Rights矩阵→客服Agent权限边界
    触发: 决策权限变更时同步

  知识库RAG:
    方向: "岗位设计器 → 知识库"
    数据: 岗位设计文档→组织知识资产
    触发: 岗位发布时自动入库

  审计日志:
    方向: "双向"
    数据: Agent决策记录→决策追溯
    触发: 每次Agent执行决策时记录
```

## 7. 多因素决策路由引擎（v2.0新增）

```python
class DecisionRouter:
    """基于5因素加权的决策路由引擎"""
    
    WEIGHTS = {
        "risk_level": 0.35,        # 风险等级（财务/法律/安全）
        "explainability": 0.25,    # 可解释性要求（监管/合规）
        "complexity": 0.20,        # 任务复杂度（模糊/创新）
        "urgency": 0.10,           # 时效性（紧急场景）
        "precedent": 0.10,         # 历史案例覆盖
    }
    
    def recommend(self, factors: dict) -> str:
        """
        factors = {
            "risk_level": 0.8,        # 0-1, 越高越危险
            "explainability": 0.6,    # 0-1, 越高越需要解释
            "complexity": 0.3,        # 0-1, 越高越复杂
            "urgency": 0.9,           # 0-1, 越高越紧急
            "precedent": 0.7,         # 0-1, 越高越有先例
        }
        """
        score = sum(
            (1 - factors.get(k, 0.5)) * v  # 风险/复杂度高→score低→更需人工
            for k, v in self.WEIGHTS.items()
        )
        # 注意：urgency和precedent是正向的（越高越可自动化）
        score = score + factors.get("urgency", 0.5) * 0.1 + factors.get("precedent", 0.5) * 0.1
        
        if score >= 0.7:   return "auto"      # Agent自动执行
        elif score >= 0.4: return "suggest"    # Agent建议，人确认
        elif score >= 0.2: return "human"      # 人工决策，Agent辅助
        else:              return "escalate"   # 升级审批
```

## 8. 测试用例

```python
def test_create_position(client):
    """创建岗位设计"""
    resp = client.post("/api/v1/plugins/ddw-position-designer/positions", json={
        "tenant_id": "test",
        "name": "大客户销售经理",
        "department": "销售部",
        "outcomes": ["年度新签≥20家", "续约率≥85%"],
        "human_responsibilities": ["高层关系维护", "商务谈判"],
        "agent_stack": ["CRM Agent", "数据分析 Agent"],
        "decision_rights": [
            {"scenario": "常规报价", "human_right": "审批", "agent_right": "自动生成", "decision_type": "auto"},
            {"scenario": "合同签署", "human_right": "最终签署", "agent_right": "草拟", "decision_type": "human"}
        ]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "大客户销售经理"
    assert len(data["outcomes"]) == 2
    assert len(data["decision_rights"]) == 2

def test_list_positions(client):
    """列表查询"""
    resp = client.get("/api/v1/plugins/ddw-position-designer/positions?tenant_id=test")
    assert resp.status_code == 200
    assert "items" in resp.json()

def test_export_html(client, position_id):
    """导出HTML"""
    resp = client.get(f"/api/v1/plugins/ddw-position-designer/positions/{position_id}/export")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Outcome" in resp.text

def test_health(client):
    """健康检查"""
    resp = client.get("/api/v1/plugins/ddw-position-designer/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_decision_type_validation():
    """决策类型枚举验证"""
    assert DecisionType.AUTO.value == "auto"
    assert DecisionType.SUGGEST.value == "suggest"
```

## 8. 验收标准

1. 插件目录 `ddw_position_designer/` 含 `__init__.py`、`plugin.py`、`models.py`、`routes.py`
2. `__init__.py` 含 `PLUGIN_NAME = "ddw-position-designer"` + `VERSION = "1.0.0"`
3. `plugin.py` 的 `Plugin.__init__` 接受 `manifest` + `**kwargs`
4. 所有API端点正常响应
5. 前端页面可创建/编辑/导出岗位设计
6. `pytest` 全部通过
7. `ruff check` 无错误

## 9. 参考文件

- HTML模板：`/Users/chenye/workspace/商务物料/人机协同岗位设计/human-agent-position-designer.html`
- 插件开发规范：`/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/` 目录下的现有插件
- Best Consulting框架：`/Users/chenye/Documents/Obsidian Vault/_02_资产/07_AI智能体/DDW×Best_Consulting_AI原生组织10维度对照手册.md`
