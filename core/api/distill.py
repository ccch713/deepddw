"""R4-3 / R4-4（DSH for Teams）：记忆+知识库蒸馏。

- DistillationTarget 接口（注册模式）：当前实现 family/team，商业版扩展。
- family 简化版：取所有成员近期个人记忆 → 去重合并 → shared 空间。
- team 完整版：取所有员工近期个人记忆 → LLM 提炼/去重/结构化 → team 空间。
- solo 不显示蒸馏功能。
- LLM 不可用时优雅降级（规则去重，不 500，日志记录）。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.api_response import ok
from core.config import get_deployment_mode
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["teams", "distill"])


# ---------------------------------------------------------------------------
# DistillationTarget 接口（注册模式，商业版可扩展）
# ---------------------------------------------------------------------------


class DistillationTarget:
    """蒸馏目标注册条目。

    mode: 部署模式（solo/family/team + 商业版扩展）
    name: 目标标识（如 'family:default'）
    source_filter: 取哪些成员的记忆（"all" 或 "members_only"）
    distill_fn: 蒸馏函数（async: sources → distilled_lines）
    auto_enabled: 是否可自动触发
    """

    def __init__(
        self,
        mode: str,
        name: str,
        source_filter: str = "all",
        distill_fn: Optional[Callable] = None,
        auto_enabled: bool = True,
    ) -> None:
        self.mode = mode
        self.name = name
        self.source_filter = source_filter
        self.distill_fn = distill_fn
        self.auto_enabled = auto_enabled


_DISTILL_REGISTRY: Dict[str, DistillationTarget] = {}


def register_distillation(target: DistillationTarget) -> None:
    key = f"{target.mode}:{target.name}"
    _DISTILL_REGISTRY[key] = target


def get_distillation_targets(mode: str) -> List[DistillationTarget]:
    return [t for t in _DISTILL_REGISTRY.values() if t.mode == mode]


def reset_distillation_registry() -> None:
    """测试用：清空注册表。"""
    _DISTILL_REGISTRY.clear()


# ---------------------------------------------------------------------------
# 蒸馏逻辑
# ---------------------------------------------------------------------------


def _collect_member_workspaces(mode: str) -> List[str]:
    """收集 mode 下所有成员的 workspace（排除 shared/family:default 等共享空间）。"""
    from core.api.teams import ISOLATION_LEVELS, list_members

    prefix = ISOLATION_LEVELS.get(mode, {}).get("member_prefix", "")
    if not prefix:
        return []
    members = list_members().get("results", [])
    workspaces: List[str] = []
    for m in members:
        mid = m.get("member_id", "")
        if mid and not m.get("revoked"):
            workspaces.append(f"{prefix}{mid}")
    return workspaces


def _deduplicate_lines(lines: List[str]) -> List[str]:
    """规则去重（去完全重复 + 语义近似；family 简化版用）。"""
    seen: set = set()
    result: List[str] = []
    for line in lines:
        sig = re.sub(r"\s+", "", line.lower())[:60]
        if sig not in seen:
            seen.add(sig)
            result.append(line)
    return result


async def distill_memory_family(
    recent_days: int = 3,
) -> Dict[str, Any]:
    """family 简化版记忆蒸馏：成员个人记忆 → 去重合并 → family:default。

    取所有成员近 N 天日志 → 规则去重（近似）→ 写入家庭共享空间。
    LLM 不可用时仍可运行（纯规则去重）。
    """
    from core.knowledge import memory_log_append, memory_logs_recent

    member_workspaces = _collect_member_workspaces("family")
    if not member_workspaces:
        return {"ok": True, "note": "no members", "wrote": 0, "mode": "family"}

    all_lines: List[str] = []
    for ws in member_workspaces:
        logs = memory_logs_recent(days=recent_days, workspace=ws).get("results", [])
        for r in logs:
            all_lines.append(r["content"])

    distilled = _deduplicate_lines(all_lines)[:10]  # 最多保留 10 条
    written = 0
    for line in distilled:
        memory_log_append(line, auto=True, workspace="family:default")
        written += 1

    return {"ok": True, "mode": "family", "wrote": written,
            "source_members": len(member_workspaces), "distilled": distilled}


async def distill_memory_team(
    recent_days: int = 3,
) -> Dict[str, Any]:
    """team 完整版记忆蒸馏：成员个人记忆 → LLM 提炼 → team:default。

    LLM 不可用 → 降级为规则去重（同 family）。
    """
    from core.knowledge import memory_log_append, memory_logs_recent

    member_workspaces = _collect_member_workspaces("team")
    if not member_workspaces:
        return {"ok": True, "note": "no members", "wrote": 0, "mode": "team"}

    all_lines: List[str] = []
    for ws in member_workspaces:
        logs = memory_logs_recent(days=recent_days, workspace=ws).get("results", [])
        for r in logs:
            all_lines.append(r["content"])

    if not all_lines:
        return {"ok": True, "mode": "team", "wrote": 0, "note": "no source data"}

    # LLM 路径
    try:
        from core.llm_gateway.base import ChatMessage, ChatResponse
        from core.llm_gateway.gateway import chat as _gateway_chat

        source_text = "\n".join(f"- {l}" for l in all_lines[:30])
        prompt = (
            "以下是一个团队近期的个人记忆日志。请提炼出 3-8 条团队共享知识"
            "（去除个人化、去重、结构化），每条一句话中文不超过 60 字。"
            "只输出 JSON 字符串数组，不要解释。\n\n日志：\n" + source_text
        )
        resp: ChatResponse = await _gateway_chat(
            [ChatMessage(role="user", content=prompt)], rule=None,
        )
        raw = (resp.content or "").strip()
        m = re.search(r"\[.*?\]", raw, re.S)
        if m:
            import json as _json

            items = _json.loads(m.group(0))
            if isinstance(items, list):
                distilled = [str(i).strip() for i in items if str(i).strip()][:8]
                if distilled:
                    written = 0
                    for line in distilled:
                        memory_log_append(line, auto=True, workspace="team:default")
                        written += 1
                    return {"ok": True, "mode": "team", "wrote": written,
                            "source_members": len(member_workspaces),
                            "distilled": distilled, "method": "llm"}
    except Exception as exc:  # noqa: BLE001
        logger.debug("team distill llm degraded: %s", exc)

    # 规则降级
    distilled = _deduplicate_lines(all_lines)[:8]
    written = 0
    for line in distilled:
        memory_log_append(line, auto=True, workspace="team:default")
        written += 1
    return {"ok": True, "mode": "team", "wrote": written,
            "source_members": len(member_workspaces),
            "distilled": distilled, "method": "rule"}


# 注册内置蒸馏目标
register_distillation(DistillationTarget(
    mode="family", name="family:default",
    source_filter="all", distill_fn=distill_memory_family,
))
register_distillation(DistillationTarget(
    mode="team", name="team:default",
    source_filter="members_only", distill_fn=distill_memory_team,
))


# ---------------------------------------------------------------------------
# HTTP 端点
# ---------------------------------------------------------------------------


class DistillReq(BaseModel):
    recent_days: int = Field(default=3, ge=1, le=30)


@router.post("/distill-memory")
async def distill_memory_endpoint(
    payload: DistillReq = DistillReq(),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """触发记忆蒸馏（按当前模式分发；solo 不可用）。"""
    mode = get_deployment_mode()
    if mode == "solo":
        return ok({"ok": False, "note": "蒸馏功能仅在 family/team 模式可用"})
    targets = get_distillation_targets(mode)
    if not targets:
        return ok({"ok": False, "note": f"无注册蒸馏目标（mode={mode}）"})
    result = await targets[0].distill_fn(recent_days=payload.recent_days)
    return ok(result)


@router.get("/distill-targets")
async def distill_targets(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """列出当前模式的蒸馏目标（管理员/调试用）。"""
    mode = get_deployment_mode()
    targets = get_distillation_targets(mode)
    return ok({
        "mode": mode,
        "targets": [
            {"name": t.name, "source_filter": t.source_filter,
             "auto_enabled": t.auto_enabled}
            for t in targets
        ],
    })
