"""DDW 岗位设计器 - 5 因素加权决策路由引擎（v2.0 新增）。

设计理念：基于 5 个维度计算"该决策可被 Agent 自动化"的概率。
高分 = 可被 Agent 自动处理；低分 = 需人工介入。

权重（合计 1.0）：
- risk_level     0.35  风险等级（财务/法律/安全）
- explainability 0.25  可解释性要求（监管/合规）
- complexity     0.20  任务复杂度（模糊/创新）
- urgency        0.10  时效性（正向：越高越可自动化）
- precedent      0.10  历史案例覆盖（正向：越高越可自动化）
"""

from __future__ import annotations

from typing import Literal

DecisionTypeStr = Literal["auto", "suggest", "human", "escalate"]


class DecisionRouter:
    """5 因素加权决策路由引擎。"""

    WEIGHTS = {
        "risk_level": 0.35,        # 风险等级（高风险 → 更需人工）
        "explainability": 0.25,    # 可解释性要求（高要求 → 更需人工）
        "complexity": 0.20,        # 任务复杂度（高复杂度 → 更需人工）
        "urgency": 0.10,           # 时效性（高紧急 → 可自动化）正向
        "precedent": 0.10,         # 历史案例覆盖（高覆盖 → 可自动化）正向
    }

    def recommend(self, factors: dict) -> DecisionTypeStr:
        """根据 5 因素分值返回推荐的决策类型。

        factors 取值 0-1：
        - risk_level: 0=无风险, 1=致命风险
        - explainability: 0=无解释要求, 1=必须可解释
        - complexity: 0=极简任务, 1=高度复杂/创新
        - urgency: 0=不限时间, 1=秒级响应
        - precedent: 0=无先例, 1=完全可复用

        返回：
        - auto:      Agent 自动执行
        - suggest:   Agent 建议，人确认
        - human:     人工决策，Agent 辅助
        - escalate:  升级审批
        """
        # 反向因素：越高越要人工
        reverse_factors = sum(
            (1 - factors.get(k, 0.5)) * w
            for k, w in self.WEIGHTS.items()
            if k not in ("urgency", "precedent")
        )
        # 正向因素：越高越可自动
        forward_factors = (
            factors.get("urgency", 0.5) * self.WEIGHTS["urgency"]
            + factors.get("precedent", 0.5) * self.WEIGHTS["precedent"]
        )
        # 总分越高，越倾向自动化
        score = reverse_factors + forward_factors

        if score >= 0.70:
            return "auto"
        elif score >= 0.40:
            return "suggest"
        elif score >= 0.20:
            return "human"
        else:
            return "escalate"

    def explain(self, factors: dict) -> dict:
        """返回带解释的推荐结果（供前端展示用）。"""
        decision = self.recommend(factors)

        # 计算各因素贡献
        contributions = {}
        for k, w in self.WEIGHTS.items():
            v = factors.get(k, 0.5)
            if k in ("urgency", "precedent"):
                contributions[k] = round(v * w, 3)  # 正向
            else:
                contributions[k] = round((1 - v) * w, 3)  # 反向

        rationale_map = {
            "auto": "Agent 可全权处理，人工监督即可",
            "suggest": "Agent 给建议，人最终确认",
            "human": "人主导决策，Agent 辅助提供信息",
            "escalate": "超出 Agent 决策边界，需要升级审批",
        }

        return {
            "decision": decision,
            "rationale": rationale_map[decision],
            "factors": factors,
            "weights": self.WEIGHTS,
            "contributions": contributions,
        }


# ---------------------------------------------------------------------------
# 默认决策类型建议（基于业务场景关键词）
# ---------------------------------------------------------------------------

DEFAULT_DECISION_TYPES = {
    "报价": "suggest",         # Agent 建议，人确认
    "客户投诉": "suggest",     # Agent 建议，人确认
    "数据录入": "auto",         # Agent 自动
    "合同签署": "human",        # 人工决策
    "退款审批": "escalate",     # 升级审批
    "客户开发": "suggest",     # Agent 建议
    "订单处理": "auto",         # 自动化
    "应急响应": "escalate",     # 升级
    "数据分析": "auto",         # 自动化
    "方案设计": "human",        # 人工
}


def suggest_decision_type(scenario: str) -> str:
    """根据业务场景关键词建议决策类型。"""
    if not scenario:
        return "suggest"
    for kw, dt in DEFAULT_DECISION_TYPES.items():
        if kw in scenario:
            return dt
    return "suggest"


# ---------------------------------------------------------------------------
# 按部门推荐 Agent
# ---------------------------------------------------------------------------

AGENT_RECOMMENDATIONS = {
    "销售部": ["CRM Agent", "数据分析 Agent", "客服 Agent", "报价 Agent"],
    "市场部": ["内容生成 Agent", "数据分析 Agent", "社媒运营 Agent", "活动策划 Agent"],
    "客服部": ["在线客服 Agent", "工单 Agent", "知识库 Agent", "情绪识别 Agent"],
    "生产部": ["巡检 Agent", "排产 Agent", "质量检测 Agent", "设备维护 Agent"],
    "研发部": ["代码生成 Agent", "知识库 Agent", "数据分析 Agent", "测试 Agent"],
    "质量部": ["SPC Agent", "数据分析 Agent", "质量报告 Agent", "审核 Agent"],
    "采购部": ["供应商 Agent", "成本分析 Agent", "库存 Agent", "比价 Agent"],
    "人力资源部": ["简历筛选 Agent", "面试 Agent", "培训 Agent", "薪酬分析 Agent"],
    "财务部": ["发票 Agent", "应收预警 Agent", "报表 Agent", "预算 Agent"],
    "IT 部": ["运维 Agent", "安全 Agent", "代码生成 Agent", "知识库 Agent"],
    "行政部": ["法务 Agent", "文档管理 Agent", "流程自动化 Agent", "审批 Agent"],
}


def recommend_agents(department: str, limit: int = 5) -> list[str]:
    """按部门推荐 Agent 组合。"""
    if not department:
        return ["数据分析 Agent", "知识库 Agent", "流程自动化 Agent"]
    for k, agents in AGENT_RECOMMENDATIONS.items():
        if k in department or department in k:
            return agents[:limit]
    return ["数据分析 Agent", "知识库 Agent", "流程自动化 Agent"]


__all__ = [
    "DecisionRouter",
    "DecisionTypeStr",
    "DEFAULT_DECISION_TYPES",
    "suggest_decision_type",
    "AGENT_RECOMMENDATIONS",
    "recommend_agents",
]
