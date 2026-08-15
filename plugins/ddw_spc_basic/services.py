"""Business logic for SPC Basic plugin."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .models import ControlChart, ProcessCapability


class SPCService:
    """Core service for Statistical Process Control analysis."""

    def __init__(self, db_session: Session):
        self.db = db_session

    # === Control Chart Analysis ===

    def create_control_chart(self, data: List[float], chart_type: str = "I-MR",
                             parameter_name: str = "", product_name: str = "",
                             usl: Optional[float] = None,
                             lsl: Optional[float] = None) -> ControlChart:
        """Create a control chart analysis."""
        if chart_type == "I-MR":
            cl, ucl, lcl = self._calc_imr_limits(data)
        elif chart_type == "Xbar-R":
            cl, ucl, lcl = self._calc_xbar_r_limits(data)
        elif chart_type == "Xbar-S":
            cl, ucl, lcl = self._calc_xbar_s_limits(data)
        else:
            cl, ucl, lcl = self._calc_imr_limits(data)

        violations = self._detect_violations(data, cl, ucl, lcl)

        cp = self._calc_cp(data, usl, lsl)
        cpk = self._calc_cpk(data, usl, lsl)
        pp = self._calc_pp(data, usl, lsl)
        ppk = self._calc_ppk(data, usl, lsl)

        interpretation = self._generate_interpretation(
            data, cl, ucl, lcl, usl, lsl, violations, cp, cpk)

        chart = ControlChart(
            chart_type=chart_type, parameter_name=parameter_name,
            product_name=product_name, data_points=data,
            center_line=round(cl, 4), ucl=round(ucl, 4), lcl=round(lcl, 4),
            usl=usl, lsl=lsl, violations=violations,
            cp=round(cp, 4) if cp else None,
            cpk=round(cpk, 4) if cpk else None,
            pp=round(pp, 4) if pp else None,
            ppk=round(ppk, 4) if ppk else None,
            interpretation=interpretation,
        )
        self.db.add(chart)
        self.db.commit()
        self.db.refresh(chart)
        return chart

    def get_control_chart(self, chart_id: int) -> Optional[ControlChart]:
        return self.db.query(ControlChart).get(chart_id)

    def list_control_charts(self, parameter_name: Optional[str] = None,
                            limit: int = 50) -> List[ControlChart]:
        q = self.db.query(ControlChart)
        if parameter_name:
            q = q.filter(ControlChart.parameter_name == parameter_name)
        return q.order_by(ControlChart.created_at.desc()).limit(limit).all()

    # === Process Capability Study ===

    def calculate_capability(self, data: List[float], parameter_name: str = "",
                             product_name: str = "",
                             usl: Optional[float] = None,
                             lsl: Optional[float] = None) -> ProcessCapability:
        """Perform process capability study."""
        n = len(data)
        mean = sum(data) / n
        std_dev = math.sqrt(sum((x - mean) ** 2 for x in data) / (n - 1))

        cp = self._calc_cp(data, usl, lsl)
        cpk = self._calc_cpk(data, usl, lsl)
        pp = self._calc_pp(data, usl, lsl)
        ppk = self._calc_ppk(data, usl, lsl)

        grade = self._grade_capability(cpk)

        interpretation = self._generate_capability_interpretation(
            cp, cpk, pp, ppk, grade, mean, std_dev, usl, lsl)

        study = ProcessCapability(
            parameter_name=parameter_name, product_name=product_name,
            sample_size=n, mean=round(mean, 4), std_dev=round(std_dev, 4),
            usl=usl, lsl=lsl,
            cp=round(cp, 4) if cp else None,
            cpk=round(cpk, 4) if cpk else None,
            pp=round(pp, 4) if pp else None,
            ppk=round(ppk, 4) if ppk else None,
            capability_grade=grade, interpretation=interpretation,
        )
        self.db.add(study)
        self.db.commit()
        self.db.refresh(study)
        return study

    # === Statistical Calculations ===

    def _calc_imr_limits(self, data: List[float]) -> Tuple[float, float, float]:
        """Individual-Moving Range chart limits."""
        mean = sum(data) / len(data)
        moving_ranges = [abs(data[i] - data[i-1]) for i in range(1, len(data))]
        mr_bar = sum(moving_ranges) / len(moving_ranges) if moving_ranges else 0
        d2 = 1.128  # d2 for n=2
        sigma_est = mr_bar / d2
        ucl = mean + 3 * sigma_est
        lcl = mean - 3 * sigma_est
        return mean, ucl, lcl

    def _calc_xbar_r_limits(self, data: List[float], subgroup_size: int = 5) -> Tuple[float, float, float]:
        """Xbar-R chart limits (assumes data grouped by subgroups)."""
        subgroups = [data[i:i+subgroup_size] for i in range(0, len(data), subgroup_size)
                     if len(data[i:i+subgroup_size]) == subgroup_size]
        if not subgroups:
            return self._calc_imr_limits(data)
        x_bars = [sum(sg) / len(sg) for sg in subgroups]
        ranges = [max(sg) - min(sg) for sg in subgroups]
        x_bar_bar = sum(x_bars) / len(x_bars)
        r_bar = sum(ranges) / len(ranges)
        A2 = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483,
              7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308}.get(subgroup_size, 0.577)
        ucl = x_bar_bar + A2 * r_bar
        lcl = x_bar_bar - A2 * r_bar
        return x_bar_bar, ucl, lcl

    def _calc_xbar_s_limits(self, data: List[float], subgroup_size: int = 5) -> Tuple[float, float, float]:
        """Xbar-S chart limits."""
        subgroups = [data[i:i+subgroup_size] for i in range(0, len(data), subgroup_size)
                     if len(data[i:i+subgroup_size]) == subgroup_size]
        if not subgroups:
            return self._calc_imr_limits(data)
        x_bars = [sum(sg) / len(sg) for sg in subgroups]
        s_devs = [math.sqrt(sum((x - sum(sg)/len(sg))**2 for x in sg) / (len(sg)-1)) for sg in subgroups]
        x_bar_bar = sum(x_bars) / len(x_bars)
        s_bar = sum(s_devs) / len(s_devs)
        A3 = {2: 2.659, 3: 1.954, 4: 1.628, 5: 1.427, 6: 1.287}.get(subgroup_size, 1.427)
        ucl = x_bar_bar + A3 * s_bar
        lcl = x_bar_bar - A3 * s_bar
        return x_bar_bar, ucl, lcl

    def _detect_violations(self, data: List[float], cl: float,
                           ucl: float, lcl: float) -> List[Dict]:
        """Detect Nelson rules violations."""
        violations = []
        # Rule 1: Point beyond 3σ
        for i, x in enumerate(data):
            if x > ucl or x < lcl:
                violations.append({"rule": 1, "index": i, "value": x,
                                   "description": "超出控制限"})

        # Rule 2: 9 consecutive points on same side of center
        for i in range(len(data) - 8):
            segment = data[i:i+9]
            if all(x > cl for x in segment) or all(x < cl for x in segment):
                violations.append({"rule": 2, "index": i,
                                   "description": "连续9点在同一侧"})

        # Rule 3: 6 consecutive points steadily increasing or decreasing
        for i in range(len(data) - 5):
            segment = data[i:i+6]
            if all(segment[j] < segment[j+1] for j in range(5)):
                violations.append({"rule": 3, "index": i,
                                   "description": "连续6点递增"})
            elif all(segment[j] > segment[j+1] for j in range(5)):
                violations.append({"rule": 3, "index": i,
                                   "description": "连续6点递减"})

        return violations

    def _calc_cp(self, data, usl, lsl):
        if usl is None or lsl is None:
            return None
        mean = sum(data) / len(data)
        sigma = math.sqrt(sum((x - mean)**2 for x in data) / (len(data) - 1))
        return (usl - lsl) / (6 * sigma) if sigma > 0 else None

    def _calc_cpk(self, data, usl, lsl):
        if usl is None or lsl is None:
            return None
        mean = sum(data) / len(data)
        sigma = math.sqrt(sum((x - mean)**2 for x in data) / (len(data) - 1))
        if sigma <= 0:
            return None
        cpu = (usl - mean) / (3 * sigma)
        cpl = (mean - lsl) / (3 * sigma)
        return min(cpu, cpl)

    def _calc_pp(self, data, usl, lsl):
        return self._calc_cp(data, usl, lsl)  # Same formula, different interpretation

    def _calc_ppk(self, data, usl, lsl):
        return self._calc_cpk(data, usl, lsl)

    def _grade_capability(self, cpk):
        if cpk is None:
            return ""
        if cpk >= 1.67:
            return "A"
        elif cpk >= 1.33:
            return "B"
        elif cpk >= 1.0:
            return "C"
        else:
            return "D"

    def _generate_interpretation(self, data, cl, ucl, lcl, usl, lsl,
                                  violations, cp, cpk):
        parts = []
        n = len(data)
        mean = sum(data) / n
        parts.append(f"数据量: {n}个, 均值: {mean:.4f}")
        parts.append(f"控制限: UCL={ucl:.4f}, CL={cl:.4f}, LCL={lcl:.4f}")

        if violations:
            parts.append(f"⚠️ 发现 {len(violations)} 个判异规则违反")
            for v in violations[:3]:
                parts.append(f"  - 规则{v['rule']}: {v['description']}")
        else:
            parts.append("✅ 过程处于统计受控状态")

        if cp is not None:
            parts.append(f"Cp={cp:.4f}, Cpk={cpk:.4f}")
            if cpk >= 1.67:
                parts.append("✅ 过程能力优秀(A级)")
            elif cpk >= 1.33:
                parts.append("✅ 过程能力良好(B级)")
            elif cpk >= 1.0:
                parts.append("⚠️ 过程能力勉强合格(C级)")
            else:
                parts.append("❌ 过程能力不足(D级), 需改进")

        return "\n".join(parts)

    def _generate_capability_interpretation(self, cp, cpk, pp, ppk, grade,
                                             mean, std_dev, usl, lsl):
        parts = [f"样本均值: {mean:.4f}, 标准差: {std_dev:.4f}"]
        if cp and cpk:
            parts.append(f"Cp={cp:.4f}, Cpk={cpk:.4f}")
            parts.append(f"Pp={pp:.4f}, Ppk={ppk:.4f}")
            parts.append(f"能力等级: {grade}")
            if cp - cpk > 0.2:
                parts.append("⚠️ Cp与Cpk差距较大，过程可能偏心，建议调整过程中心")
        return "\n".join(parts)
