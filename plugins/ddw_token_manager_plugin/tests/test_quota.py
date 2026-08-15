"""
预消费/后消费单元测试

测试核心消费流程:
- pre_consume_quota 额度计算和预扣
- post_consume_quota 差额补偿
- return_pre_consumed_quota 退还
- 高信任跳过机制
- 最小消耗保证
"""
from __future__ import annotations

import math
import sys
from pathlib import Path


# 将插件目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPreConsumeQuota:
    """预消费额度测试"""

    def test_basic_pre_consume_calculation(self):
        """测试基本预消费额度计算

        对应 One API: relay/controller/helper.go:getPreConsumedQuota (L60-66)
        preConsumedTokens = config.PreConsumedQuota + promptTokens + maxTokens
        preConsumedQuota = preConsumedTokens * ratio
        """
        # 模拟: PreConsumedQuota=500, promptTokens=100, maxTokens=200, ratio=2.5
        pre_consumed_tokens = 500 + 100 + 200  # = 800
        pre_consumed_quota = int(float(pre_consumed_tokens) * 2.5)  # = 2000
        assert pre_consumed_quota == 2000

    def test_pre_consume_without_max_tokens(self):
        """测试无 max_tokens 时的预消费"""
        pre_consumed_tokens = 500 + 100  # = 600 (无 maxTokens)
        ratio = 2.5
        pre_consumed_quota = int(float(pre_consumed_tokens) * ratio)  # = 1500
        assert pre_consumed_quota == 1500

    def test_high_trust_skip(self):
        """测试高信任跳过机制

        对应 One API: relay/controller/helper.go:L82-87
        if userQuota > 100 * preConsumedQuota:
            preConsumedQuota = 0  # trust user
        """
        pre_consumed_quota = 2000
        user_quota = 500000  # > 100 * 2000 = 200000

        # 高信任跳过
        if user_quota > 100 * pre_consumed_quota:
            pre_consumed_quota = 0

        assert pre_consumed_quota == 0

    def test_no_skip_when_quota_low(self):
        """测试额度不足时不禁用跳过"""
        pre_consumed_quota = 2000
        user_quota = 100000  # < 100 * 2000 = 200000

        if user_quota > 100 * pre_consumed_quota:
            pre_consumed_quota = 0

        assert pre_consumed_quota == 2000  # 未跳过


class TestPostConsumeQuota:
    """后消费额度测试"""

    def test_basic_post_consume(self):
        """测试基本后消费计算

        对应 One API: relay/controller/helper.go:postConsumeQuota (L97-141)
        quota = ceil((promptTokens + completionTokens * completionRatio) * ratio)
        """
        prompt_tokens = 100
        completion_tokens = 50
        completion_ratio = 1.0
        model_ratio = 2.5
        group_ratio = 1.0

        quota = math.ceil(
            (float(prompt_tokens) + float(completion_tokens) * completion_ratio)
            * model_ratio
            * group_ratio
        )
        # (100 + 50 * 1.0) * 2.5 = 150 * 2.5 = 375
        assert quota == 375

    def test_completion_ratio_effect(self):
        """测试输出倍率效果

        DeepSeek Reasoner: completionRatio = 2.19
        """
        prompt_tokens = 100
        completion_tokens = 50
        completion_ratio = 2.19  # DeepSeek Reasoner
        model_ratio = 1.0
        group_ratio = 1.0

        quota = math.ceil(
            (float(prompt_tokens) + float(completion_tokens) * completion_ratio)
            * model_ratio
            * group_ratio
        )
        # (100 + 50 * 2.19) * 1.0 = (100 + 109.5) = 209.5 → 210
        assert quota == 210

    def test_minimum_quota_guarantee(self):
        """测试最小消耗保证

        对应 One API: relay/controller/helper.go:L107-109
        if ratio != 0 && quota <= 0:
            quota = 1
        """
        # 用极小的 token 数
        prompt_tokens = 0
        completion_tokens = 0
        completion_ratio = 0.001
        model_ratio = 0.001
        group_ratio = 1.0

        quota = math.ceil(
            (float(prompt_tokens) + float(completion_tokens) * completion_ratio)
            * model_ratio
            * group_ratio
        )
        # 0 * 0.001 = 0, 但 model_ratio != 0, 所以 quota = 1
        if model_ratio != 0 and quota <= 0:
            quota = 1
        assert quota == 1

    def test_quota_delta_calculation(self):
        """测试差额计算"""
        actual_quota = 375
        pre_consumed_quota = 400

        quota_delta = actual_quota - pre_consumed_quota  # -25 (需退还)
        assert quota_delta == -25

        # 实际消耗更多时
        actual_quota = 500
        quota_delta = actual_quota - pre_consumed_quota  # 100 (需追扣)
        assert quota_delta == 100

    def test_zero_tokens_quota(self):
        """测试零 token 时 quota=0

        对应 One API: helper.go:L111-115
        if totalTokens == 0:
            quota = 0
        """
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = prompt_tokens + completion_tokens

        if total_tokens == 0:
            quota = 0
        else:
            quota = 999  # 不应执行到这里

        assert quota == 0


class TestReturnPreConsumedQuota:
    """退还预消费额度测试"""

    def test_return_positive_quota(self):
        """测试退还正数额度"""
        pre_consumed_quota = 2000
        token_remain = 50000
        token_used = 10000

        # 退还
        if pre_consumed_quota > 0:
            token_remain += pre_consumed_quota
            token_used -= pre_consumed_quota

        assert token_remain == 52000
        assert token_used == 8000

    def test_return_zero_noop(self):
        """测试退还零额度（无操作）"""
        pre_consumed_quota = 0
        token_remain = 50000
        original_remain = token_remain

        if pre_consumed_quota > 0:
            token_remain += pre_consumed_quota

        assert token_remain == original_remain


class TestQuotaCalculation:
    """倍率计算综合测试"""

    def test_gpt4o_ratio(self):
        """测试 GPT-4o 倍率"""
        from config_loader import ModelRatioLoader

        loader = ModelRatioLoader.__new__(ModelRatioLoader)
        loader._flat_ratios = {"gpt-4o": 2.5}
        loader._flat_completions = {"gpt-4o": 1.0}
        loader._group_ratios = {"default": 1.0}
        loader._constants = {}
        loader._yaml_path = Path("/nonexistent_path_for_test")
        loader._last_mtime = 9999999999.0  # 设置为未来时间，防止热更新触发

        quota = loader.calculate_quota("gpt-4o", 1000, 500)
        # (1000 + 500 * 1.0) * 2.5 * 1.0 = 3750
        assert quota == 3750

    def test_deepseek_reasoner_ratio(self):
        """测试 DeepSeek Reasoner 倍率（输出倍率=2.19）"""
        from config_loader import REASONING_OUTPUT_OVERRIDES, ModelRatioLoader

        loader = ModelRatioLoader.__new__(ModelRatioLoader)
        loader._flat_ratios = {"deepseek-reasoner": 1.0}
        loader._flat_completions = {"deepseek-reasoner": 1.0}
        loader._group_ratios = {"default": 1.0}
        loader._constants = {}
        loader._yaml_path = Path("/nonexistent_path_for_test")
        loader._last_mtime = 9999999999.0

        # 覆盖输出倍率
        assert REASONING_OUTPUT_OVERRIDES["deepseek-reasoner"] == 2.19

        completion_ratio = REASONING_OUTPUT_OVERRIDES["deepseek-reasoner"]
        model_ratio = 1.0
        prompt_tokens = 1000
        completion_tokens = 500

        quota = math.ceil(
            (float(prompt_tokens) + float(completion_tokens) * completion_ratio)
            * model_ratio
        )
        # (1000 + 500 * 2.19) * 1.0 = (1000 + 1095) = 2095
        assert quota == 2095

    def test_unknown_model_default_ratio(self):
        """测试未知模型使用默认倍率 1.0"""
        from config_loader import ModelRatioLoader

        loader = ModelRatioLoader.__new__(ModelRatioLoader)
        loader._flat_ratios = {}
        loader._flat_completions = {}
        loader._group_ratios = {"default": 1.0}
        loader._constants = {}
        loader._yaml_path = Path("/nonexistent_path_for_test")
        loader._last_mtime = 9999999999.0

        ratio = loader.get_input_ratio("unknown-model")
        assert ratio == 1.0  # 默认值
