"""B9 指标口径字典 - 测试"""
import pytest

from plugins.ddw_metric_dict import PLUGIN_NAME, VERSION
from plugins.ddw_metric_dict.models import (
    MetricAdjudicationRequest,
    MetricDefinition,
    MetricFormula,
    MetricRouteRequest,
)
from plugins.ddw_metric_dict.service import (
    MetricNotFoundError,
    adjudicate,
    clear_all,
    create_metric,
    get_metric,
    list_metrics,
    route_metric,
    set_dept_caliber,
)


@pytest.fixture(autouse=True)
def _clean():
    clear_all()
    yield
    clear_all()


def _sample_metric() -> MetricDefinition:
    return MetricDefinition(
        metric_id="M001",
        name="营收增长率",
        calibers=[
            MetricFormula(caliber_id="cal_fin", formula="(本期-上期)/上期", data_source="财务系统"),
            MetricFormula(caliber_id="cal_biz", formula="(本期-上期)/上期*100", data_source="业务看板", update_frequency="weekly"),
        ],
        default_caliber_id="cal_fin",
    )


# ---------- 基础 CRUD ----------

def test_version():
    assert VERSION == "0.1.0"
    assert PLUGIN_NAME == "ddw-metric-dict"


def test_create_and_get_metric():
    m = _sample_metric()
    create_metric(m)
    got = get_metric("M001")
    assert got.name == "营收增长率"
    assert len(got.calibers) == 2


def test_list_metrics():
    create_metric(_sample_metric())
    create_metric(MetricDefinition(metric_id="M002", name="毛利率"))
    assert len(list_metrics()) == 2


def test_get_metric_not_found():
    with pytest.raises(MetricNotFoundError):
        get_metric("NO_SUCH")


# ---------- 口径路由 ----------

def test_route_default_caliber():
    m = _sample_metric()
    create_metric(m)
    resp = route_metric(MetricRouteRequest(metric_name="营收增长率"))
    assert resp.selected_caliber.caliber_id == "cal_fin"
    assert "默认口径" in resp.reason


def test_route_by_department_pref():
    m = _sample_metric()
    create_metric(m)
    set_dept_caliber("营收增长率", "销售部", "cal_biz")
    resp = route_metric(MetricRouteRequest(metric_name="营收增长率", department="销售部"))
    assert resp.selected_caliber.caliber_id == "cal_biz"
    assert "销售部" in resp.reason


def test_route_by_context_tag():
    m = _sample_metric()
    create_metric(m)
    resp = route_metric(MetricRouteRequest(
        metric_name="营收增长率", context={"tag": "biz"}
    ))
    assert resp.selected_caliber.caliber_id == "cal_biz"


def test_route_metric_not_found():
    with pytest.raises(MetricNotFoundError):
        route_metric(MetricRouteRequest(metric_name="不存在"))


# ---------- 冲突裁决 ----------

def test_adjudicate_multi_caliber():
    create_metric(_sample_metric())
    result = adjudicate(MetricAdjudicationRequest(
        metric_name="营收增长率", department_a="财务部", department_b="销售部"
    ))
    assert result.metric_id == "M001"
    assert "分歧" in result.conflict_description
    # cal_biz 有 data_source + 更长 formula，应被选中
    assert result.suggested_caliber.caliber_id == "cal_biz"


def test_adjudicate_single_caliber():
    create_metric(MetricDefinition(
        metric_id="M003",
        name="客户满意度",
        calibers=[MetricFormula(caliber_id="cal_std", formula="NPS")],
    ))
    result = adjudicate(MetricAdjudicationRequest(
        metric_name="客户满意度", department_a="客服部", department_b="产品部"
    ))
    assert "仅有一条口径" in result.conflict_description
