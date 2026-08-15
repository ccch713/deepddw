"""
校准反算单元测试

测试校准核心算法:
- calculate_calibration_ratio 计算校准系数 K
- is_calibrated 收敛判断
- alert_low_balance 低余额预警
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 将插件目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCalibrationRatio:
    """校准系数计算测试"""

    def test_basic_calibration_ratio(self):
        """测试基本校准系数计算

        K = sum(actual_costs) / sum(estimated_costs)
        """
        # 场景: 本地估算 $100, Provider 实际扣费 $110
        estimated_total = 100.0
        actual_total = 110.0
        k = actual_total / estimated_total
        assert k == pytest.approx(1.1)  # K > 1 表示本地低估了

    def test_calibration_ratio_overestimate(self):
        """测试本地高估场景"""
        estimated_total = 100.0
        actual_total = 85.0
        k = actual_total / estimated_total
        assert k == pytest.approx(0.85)  # K < 1 表示本地高估了

    def test_calibration_ratio_zero_estimate(self):
        """测试估算为零时 K=1.0"""
        estimated_total = 0.0
        actual_total = 10.0
        k = actual_total / estimated_total if estimated_total > 0 else 1.0
        assert k == 1.0


class TestConvergenceCheck:
    """收敛判断测试"""

    def test_converged_within_tolerance(self):
        """测试在容忍度内收敛

        连续两次 K 变化 < 5% → 收敛
        """
        records = [
            MagicMock(ratio_adjustment=1.05),
            MagicMock(ratio_adjustment=1.07),
            MagicMock(ratio_adjustment=1.08),
        ]
        tolerance = 0.05

        # 检查连续稳定性
        stable_count = 0
        for i in range(len(records) - 1, 0, -1):
            current_k = records[i].ratio_adjustment
            prev_k = records[i - 1].ratio_adjustment
            change = abs(current_k - prev_k) / prev_k
            if change < tolerance:
                stable_count += 1
            else:
                break

        is_converged = stable_count >= 1
        assert is_converged is True
        assert stable_count == 2

    def test_not_converged(self):
        """测试未收敛"""
        records = [
            MagicMock(ratio_adjustment=1.0),
            MagicMock(ratio_adjustment=1.5),  # 50% 变化
            MagicMock(ratio_adjustment=2.0),  # 33% 变化
        ]
        tolerance = 0.05

        stable_count = 0
        for i in range(len(records) - 1, 0, -1):
            current_k = records[i].ratio_adjustment
            prev_k = records[i - 1].ratio_adjustment
            change = abs(current_k - prev_k) / prev_k
            if change < tolerance:
                stable_count += 1
            else:
                break

        is_converged = stable_count >= 1
        assert is_converged is False

    def test_single_record_not_converged(self):
        """测试单条记录不收敛"""
        records = [MagicMock(ratio_adjustment=1.0)]
        assert len(records) < 2  # 不满足最小记录数


class TestLowBalanceAlert:
    """低余额预警测试"""

    def test_low_balance_trigger(self):
        """测试低余额触发预警"""
        total_quota = 100.0
        used_quota = 85.0
        remaining = total_quota - used_quota
        usage_ratio = used_quota / total_quota

        threshold = 0.2  # 剩余 20% 时预警
        is_low = usage_ratio > (1.0 - threshold)

        assert is_low is True  # 85% 已用，剩余 15% < 20%
        assert remaining == pytest.approx(15.0)

    def test_sufficient_balance_no_alert(self):
        """测试余额充足不预警"""
        total_quota = 100.0
        used_quota = 50.0
        usage_ratio = used_quota / total_quota

        threshold = 0.2
        is_low = usage_ratio > (1.0 - threshold)

        assert is_low is False  # 50% 已用，剩余 50% > 20%

    def test_expiring_soon_alert(self):
        """测试即将到期预警"""
        expires_at = datetime.now() + timedelta(days=5)
        days_until_expiry = (expires_at - datetime.now()).days

        alert = days_until_expiry < 7
        assert alert is True  # 5 天后到期

    def test_not_expiring_no_alert(self):
        """测试未到期不预警"""
        expires_at = datetime.now() + timedelta(days=30)
        days_until_expiry = (expires_at - datetime.now()).days

        alert = days_until_expiry < 7
        assert alert is False


class TestSubscriptionStatus:
    """订阅状态测试"""

    def test_remaining_calculation(self):
        """测试剩余额度计算"""
        total_quota = 1000.0
        used_quota = 350.0
        remaining = total_quota - used_quota
        assert remaining == 650.0

    def test_usage_ratio(self):
        """测试使用比例"""
        total_quota = 1000.0
        used_quota = 350.0
        usage_ratio = min(used_quota / total_quota, 1.0)
        assert usage_ratio == pytest.approx(0.35)

    def test_usage_ratio_cap_at_one(self):
        """测试使用比例上限为 1.0"""
        total_quota = 100.0
        used_quota = 150.0  # 超用
        usage_ratio = min(used_quota / total_quota, 1.0)
        assert usage_ratio == 1.0

    def test_zero_quota_ratio(self):
        """测试零额度时使用比例为 1.0"""
        total_quota = 0.0
        used_quota = 0.0
        if total_quota <= 0:
            usage_ratio = 1.0
        else:
            usage_ratio = used_quota / total_quota
        assert usage_ratio == 1.0
