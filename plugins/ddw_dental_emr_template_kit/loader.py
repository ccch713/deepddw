"""DDW Dental EMR Template Kit - 模板加载器.

支持从 templates/*.yaml 加载模板配置，结构：
  type: extraction
  name: 拔牙病历
  version: "1.0"
  required_fields: [...]
  fields: {field_name: {label, type, max_length, options, required, required_if, ...}}
  display_order: [...]
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"

# 内置 9 类诊疗的兜底模板（当 templates/*.yaml 缺失时使用）
_FALLBACK_TEMPLATES: dict[str, dict[str, Any]] = {
    "extraction": {
        "type": "extraction",
        "name": "拔牙病历",
        "version": "1.0",
        "required_fields": [
            "chief_complaint", "present_illness", "tooth_position",
            "extraction_reason", "difficulty_level", "anesthesia_type",
            "anticoagulant_use", "contraindications",
        ],
        "fields": {
            "chief_complaint": {"label": "主诉", "type": "text", "max_length": 200, "required": True},
            "present_illness": {"label": "现病史", "type": "text", "max_length": 1000, "required": True},
            "past_history": {"label": "既往史", "type": "text", "max_length": 500, "required": False},
            "tooth_position": {"label": "牙位", "type": "select",
                               "options": ["右上1-8", "左上1-8", "右下1-8", "左下1-8"],
                               "required": True},
            "extraction_reason": {"label": "拔牙原因", "type": "select",
                                   "options": ["impaction", "caries", "periodontal", "orthodontic", "trauma"],
                                   "required": True},
            "difficulty_level": {"label": "难度", "type": "select",
                                 "options": ["simple", "surgical", "complex"], "required": True},
            "anesthesia_type": {"label": "麻醉", "type": "select",
                                "options": ["local", "intraligamentary", "inferior_alveolar", "general"],
                                "required": True},
            "anticoagulant_use": {"label": "抗凝药", "type": "boolean", "required": True},
            "anticoagulant_drug": {"label": "抗凝药名", "type": "text", "required_if": "anticoagulant_use == true"},
            "contraindications": {"label": "禁忌症", "type": "text", "required": True},
            "intraoperative_notes": {"label": "术中记录", "type": "text", "max_length": 1000, "required": False},
            "postop_instructions": {"label": "术后医嘱", "type": "text", "max_length": 500, "required": True},
        },
        "display_order": [
            "chief_complaint", "present_illness", "past_history", "tooth_position",
            "extraction_reason", "difficulty_level", "anesthesia_type",
            "anticoagulant_use", "anticoagulant_drug", "contraindications",
            "intraoperative_notes", "postop_instructions",
        ],
    },
}


def list_template_files() -> list[Path]:
    if not TEMPLATE_DIR.exists():
        return []
    return sorted(TEMPLATE_DIR.glob("*.yaml"))


def load_template(treatment_type: str) -> Optional[dict[str, Any]]:
    """加载单个模板（先看 YAML 文件，否则用兜底）."""
    p = TEMPLATE_DIR / f"{treatment_type}.yaml"
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data.setdefault("type", treatment_type)
            return data
        except yaml.YAMLError as e:
            logger.warning("yaml parse failed for %s: %s", p, e)
    return _FALLBACK_TEMPLATES.get(treatment_type)


def list_templates() -> list[dict[str, Any]]:
    """列出所有可用模板（去重 + 兜底）."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    # 先看 yaml 文件
    for p in list_template_files():
        try:
            with open(p, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            tt = data.get("type") or p.stem
            if tt in seen:
                continue
            seen.add(tt)
            out.append(_summarize(data, source="yaml", file=p.name))
        except yaml.YAMLError as e:
            logger.warning("skip invalid yaml %s: %s", p, e)
    # 再补兜底
    for tt, data in _FALLBACK_TEMPLATES.items():
        if tt in seen:
            continue
        seen.add(tt)
        out.append(_summarize(data, source="builtin", file=""))
    out.sort(key=lambda x: x["type"])
    return out


def _summarize(data: dict[str, Any], *, source: str, file: str) -> dict[str, Any]:
    return {
        "type": data.get("type", ""),
        "name": data.get("name", ""),
        "version": data.get("version", "1.0"),
        "required_fields_count": len(data.get("required_fields", [])),
        "fields_count": len(data.get("fields", {})),
        "source": source,
        "file": file,
    }


def get_template_full(treatment_type: str) -> Optional[dict[str, Any]]:
    """获取模板的完整定义（fields + display_order + required_fields）."""
    return load_template(treatment_type)


def validate_required_fields(
    treatment_type: str, data: dict[str, Any]
) -> list[dict[str, Any]]:
    """校验必填字段. 返回缺失字段列表."""
    tpl = load_template(treatment_type)
    if tpl is None:
        return [{"field": "_template", "error": f"未知诊疗类型: {treatment_type}"}]
    missing: list[dict[str, Any]] = []
    for fname in tpl.get("required_fields", []):
        if fname not in data or data[fname] is None:
            missing.append({"field": fname, "error": "必填字段缺失"})
        elif isinstance(data[fname], str) and not data[fname].strip():
            missing.append({"field": fname, "error": "必填字段为空"})
    # required_if 条件检查
    fields_def = tpl.get("fields", {})
    for fname, fdef in fields_def.items():
        cond = fdef.get("required_if")
        if not cond:
            continue
        # 简单解析 "field == value"，value 支持 true/false 字符串自动转 bool
        if "==" in cond:
            ref, _, val = cond.partition("==")
            ref, val = ref.strip(), val.strip()
            val_stripped = val.strip('"').strip("'").lower()
            if val_stripped in ("true", "false"):
                target: Any = val_stripped == "true"
            else:
                target = val_stripped
            if data.get(ref) == target and not data.get(fname):
                missing.append({"field": fname, "error": f"条件必填 ({cond})"})
    return missing
