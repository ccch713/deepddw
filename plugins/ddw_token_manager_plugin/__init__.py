"""
DDW Token Manager 插件

基于 One API (songquanpeng/one-api) 额度管理系统，
为 DDW AI Hub 提供 Token 额度管理能力。

核心功能:
- 预消费/后消费机制（对应 relay/controller/helper.go）
- 批量更新优化（对应 model/utils.go）
- 校准反算算法（DDW差异化核心）
- 订阅感知路由
- 模型倍率配置加载（569个模型）
"""
from __future__ import annotations

try:
    from .main import TokenManagerPlugin
except ImportError:
    # 独立运行时（非包导入），忽略相对导入
    pass
