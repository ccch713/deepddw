"""DDW Dental EMR Plugin.

口腔病历主插件：基于模板的病历创建、查询、状态流转。
依赖：ddw_clinical_asr（实体抽取）、ddw_dental_emr_template_kit（模板套件）。
服务：武汉东华口腔青山店（沿港路27号，14医生）
"""
from __future__ import annotations

PLUGIN_NAME = "ddw_dental_emr"
VERSION = "0.1.0"
__all__ = ["PLUGIN_NAME", "VERSION"]
