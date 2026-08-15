"""Tests for SPC Basic service."""



class TestControlChart:
    def test_imr_chart(self, service, normal_data):
        chart = service.create_control_chart(
            data=normal_data, chart_type="I-MR",
            parameter_name="DHA含量", product_name="藻油DHA",
            usl=106, lsl=94
        )
        assert chart.id is not None
        assert chart.chart_type == "I-MR"
        assert chart.ucl > chart.center_line > chart.lcl
        assert chart.cp is not None
        assert chart.cpk is not None

    def test_xbar_r_chart(self, service, normal_data):
        chart = service.create_control_chart(
            data=normal_data, chart_type="Xbar-R",
            parameter_name="ARA含量"
        )
        assert chart.id is not None
        assert chart.chart_type == "Xbar-R"

    def test_chart_with_violations(self, service):
        # Data with obvious trend violation
        data = [10.0] * 5 + [10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7]
        chart = service.create_control_chart(data=data, parameter_name="test")
        assert chart.violations is not None

    def test_list_charts(self, service, normal_data):
        service.create_control_chart(data=normal_data, parameter_name="P1")
        service.create_control_chart(data=normal_data, parameter_name="P2")
        charts = service.list_control_charts()
        assert len(charts) == 2

    def test_get_chart(self, service, normal_data):
        chart = service.create_control_chart(data=normal_data, parameter_name="P1")
        fetched = service.get_control_chart(chart.id)
        assert fetched.parameter_name == "P1"


class TestProcessCapability:
    def test_capability_normal(self, service, normal_data):
        study = service.calculate_capability(
            data=normal_data, parameter_name="DHA含量",
            product_name="藻油DHA", usl=106, lsl=94
        )
        assert study.id is not None
        assert study.cp is not None
        assert study.cpk is not None
        assert study.capability_grade in ["A", "B", "C", "D"]

    def test_capability_without_specs(self, service, normal_data):
        study = service.calculate_capability(data=normal_data, parameter_name="test")
        assert study.cp is None  # No spec limits
        assert study.capability_grade == ""

    def test_capability_excellent(self, service):
        # Tight distribution well within spec
        data = [100.0 + 0.1 * (i % 5 - 2) for i in range(50)]
        study = service.calculate_capability(
            data=data, parameter_name="test", usl=105, lsl=95
        )
        assert study.capability_grade == "A"


class TestStatisticalCalculations:
    def test_cp_formula(self, service):
        data = [100.0] * 30 + [101.0] * 10 + [99.0] * 10
        study = service.calculate_capability(data=data, usl=103, lsl=97)
        assert study.cp > 0
        assert study.cp < 10  # Sanity check

    def test_cpk_less_than_cp_when_offcenter(self, service):
        data = [101.0 + 0.5 * (i % 3) for i in range(50)]
        study = service.calculate_capability(data=data, usl=104, lsl=96)
        if study.cp and study.cpk:
            assert study.cpk <= study.cp
