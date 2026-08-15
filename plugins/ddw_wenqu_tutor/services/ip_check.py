"""AI 版权风险检测（2026-08-14 移植自 wenquK12 ip_check.py）。

用视觉模型判断图片是否包含 IP 版权内容（迪士尼/漫威/动画/游戏/名人等），
用于皮肤市场 UGC 上传审核（检查 IP 版权风险，防侵权合规）。
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

VISION_MODEL = os.getenv("DDW_WENQU_VISION_MODEL", "MiniMax-VL-01")
VISION_BASE_URL = os.getenv(
    "DDW_WENQU_VISION_BASE_URL", "https://api.minimaxi.com/v1"
)


@dataclass
class IPCheckResult:
    has_risk: bool
    risk_type: Optional[str] = "none"   # disney/anime/game/celebrity/other/none
    confidence: float = 0.0
    suggestion: str = "拒绝"             # 通过 / 拒绝
    details: str = ""


def _vision_api_key() -> str:
    key = os.getenv("DDW_WENQU_VISION_API_KEY", "")
    if key:
        return key
    key = os.getenv("DDW_MINIMAX_API_KEY", "")
    if key:
        return key
    try:
        with open(os.path.expanduser("~/.ddw_env")) as f:
            for line in f:
                if "MINIMAX_API_KEY" in line:
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return ""


async def check_ip_risk(
    image_url: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    description: str = "",
) -> IPCheckResult:
    """检测图片是否包含 IP 版权风险（视觉模型多模态调用）。"""
    prompt = f"""请分析这张图片是否包含IP版权风险（如迪士尼、漫威、哈利波特、
海贼王、王者荣耀、英雄联盟等知名IP的角色、标志、图案）。

用户描述：{description}

返回JSON格式：
{{
    "has_risk": true/false,
    "risk_type": "disney/anime/game/celebrity/other/none",
    "confidence": 0.0-1.0,
    "suggestion": "通过" 或 "拒绝",
    "details": "具体说明"
}}"""

    api_key = _vision_api_key()
    if not api_key:
        logger.warning("vision api key 未配置，版权检测返回默认拒绝")
        return IPCheckResult(has_risk=True, suggestion="拒绝", details="审核服务未配置")

    content = []
    if image_bytes:
        mime = "image/jpeg" if image_bytes[:2] == b"\xff\xd8" else "image/png"
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
        content.append({"type": "image_url", "image_url": {"url": data_url}})
    elif image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    content.append({"type": "text", "text": prompt})

    payload = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
        "max_tokens": 300,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{VISION_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        raw = data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        logger.error("IP check vision call failed: %s", e)
        return IPCheckResult(has_risk=True, suggestion="拒绝", details=f"审核服务异常：{e}")

    # 解析 JSON
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            d = json.loads(json_match.group())
            return IPCheckResult(
                has_risk=bool(d.get("has_risk", False)),
                risk_type=d.get("risk_type", "none"),
                confidence=float(d.get("confidence", 0.5)),
                suggestion=d.get("suggestion", "拒绝"),
                details=d.get("details", ""),
            )
        except (json.JSONDecodeError, ValueError):
            logger.error("IP check JSON parse failed")

    return IPCheckResult(has_risk=True, suggestion="拒绝", details="审核结果无法解析")


# ── 皮肤开发规范（css_vars 必须包含的核心变量） ──
SKIN_REQUIRED_VARS = [
    "--bg", "--sidebar", "--sidebar-text", "--card",
    "--text", "--text-dim", "--accent", "--line",
]

SKIN_DEV_SPEC = (
    "皮肤 = CSS 变量定义对象（css_vars），必须包含："
    + ", ".join(SKIN_REQUIRED_VARS)
    + "。参考官方预设：朱砂经典（--bg #F7F1E3 / --accent #B03A2E / --sidebar #8C2E24）。"
    "建议 1-3 元定价（上限 5 元），售卖 T+0，作者 75% / 平台 25%。"
)


def validate_skin_vars(css_vars: dict) -> Optional[str]:
    """校验皮肤变量完整性，缺失返回错误信息。"""
    missing = [v for v in SKIN_REQUIRED_VARS if v not in css_vars]
    if missing:
        return f"缺少必填颜色变量：{', '.join(missing)}"
    return None


__all__ = [
    "IPCheckResult",
    "SKIN_DEV_SPEC",
    "SKIN_REQUIRED_VARS",
    "check_ip_risk",
    "validate_skin_vars",
]
