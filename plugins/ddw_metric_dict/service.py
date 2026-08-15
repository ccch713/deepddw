"""B9 指标口径字典 - 核心业务逻辑"""
from __future__ import annotations

from typing import Optional

from plugins.ddw_metric_dict.models import (
    MetricAdjudicationRequest,
    MetricAdjudicationResult,
    MetricDefinition,
    MetricFormula,
    MetricRouteRequest,
    MetricRouteResponse,
)

# 内存存储（生产环境可替换为持久化）
_metrics: dict[str, MetricDefinition] = {}

# 部门口径偏好映射：{(metric_name, department) -> caliber_id}
_dept_caliber_prefs: dict[tuple[str, str], str] = {}


class MetricNotFoundError(KeyError):
    pass


class CaliberNotFoundError(KeyError):
    pass


def create_metric(metric: MetricDefinition) -> MetricDefinition:
    if not metric.default_caliber_id and metric.calibers:
        metric.default_caliber_id = metric.calibers[0].caliber_id
    if metric.metric_id in _metrics:
        raise MetricNotFoundError(f'Metric {metric.metric_id} already exists — use PUT to update')
    _metrics[metric.metric_id] = metric
    return metric


def list_metrics() -> list[MetricDefinition]:
    return list(_metrics.values())


def get_metric(metric_id: str) -> MetricDefinition:
    if metric_id not in _metrics:
        raise MetricNotFoundError(f"指标 {metric_id} 不存在")
    return _metrics[metric_id]


def add_caliber(metric_id: str, formula: MetricFormula) -> MetricDefinition:
    metric = get_metric(metric_id)
    metric.calibers.append(formula)
    return metric


def set_dept_caliber(metric_name: str, department: str, caliber_id: str) -> None:
    _dept_caliber_prefs[(metric_name, department)] = caliber_id


def route_metric(req: MetricRouteRequest) -> MetricRouteResponse:
    target: Optional[MetricDefinition] = None
    for m in _metrics.values():
        if m.name == req.metric_name:
            target = m
            break
    if target is None:
        raise MetricNotFoundError(f"指标 {req.metric_name} 不存在")

    # 优先按部门偏好选择口径
    pref_key = (req.metric_name, req.department)
    selected_id = _dept_caliber_prefs.get(pref_key)
    selected: Optional[MetricFormula] = None
    reason = ""

    if selected_id:
        for c in target.calibers:
            if c.caliber_id == selected_id:
                selected = c
                reason = f"部门 {req.department} 的偏好口径"
                break

    # 其次按 context 中的 tag 匹配
    if selected is None and req.context.get("tag"):
        tag = req.context["tag"]
        for c in target.calibers:
            if tag in c.caliber_id:
                selected = c
                reason = f"按上下文 tag={tag} 匹配"
                break

    # 兜底使用默认口径
    if selected is None:
        for c in target.calibers:
            if c.caliber_id == target.default_caliber_id:
                selected = c
                reason = "使用默认口径"
                break
        if selected is None and target.calibers:
            selected = target.calibers[0]
            reason = "使用首个可用口径"

    if selected is None:
        raise CaliberNotFoundError(f"指标 {req.metric_name} 无可选口径")

    return MetricRouteResponse(
        metric_id=target.metric_id,
        metric_name=target.name,
        selected_caliber=selected,
        reason=reason,
    )


def adjudicate(req: MetricAdjudicationRequest) -> MetricAdjudicationResult:
    target: Optional[MetricDefinition] = None
    for m in _metrics.values():
        if m.name == req.metric_name:
            target = m
            break
    if target is None:
        raise MetricNotFoundError(f"指标 {req.metric_name} 不存在")

    if len(target.calibers) < 2:
        default = target.calibers[0] if target.calibers else MetricFormula(
            caliber_id="none", formula="N/A"
        )
        return MetricAdjudicationResult(
            metric_id=target.metric_id,
            metric_name=target.name,
            conflict_description="仅有一条口径，无冲突",
            suggested_caliber=default,
            suggestion_reason="唯一口径，无争议",
        )

    # 选择数据源最多、公式最长的口径作为建议（启发式）
    best = max(
        target.calibers,
        key=lambda c: (len(c.data_source), len(c.formula)),
    )
    conflict_desc = (
        f"部门 {req.department_a} 与 {req.department_b} 对指标 "
        f"「{req.metric_name}」存在 {len(target.calibers)} 条口径分歧"
    )
    return MetricAdjudicationResult(
        metric_id=target.metric_id,
        metric_name=target.name,
        conflict_description=conflict_desc,
        suggested_caliber=best,
        suggestion_reason="数据源覆盖最广、公式描述最完整",
    )


def clear_all() -> None:
    """测试辅助：清空所有数据"""
    _metrics.clear()
    _dept_caliber_prefs.clear()
