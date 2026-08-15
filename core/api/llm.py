"""LLM 管理 API（/llm）— 提供商 / 路由规则。

前端 admin.html 频道依赖：
- GET /llm/providers    LLM 提供商健康/列表
- GET /llm/rules        路由规则
- GET /llm/fallback     回退链
- POST /llm/providers   新增自定义提供商（2026-08-11，key 仅内存注册不落盘）
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security.token_gate import require_access_token
from core.llm_gateway.gateway import health as llm_health
from core.llm_gateway.gateway import register_provider
from core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])

# 自定义提供商元数据（API Key 不落盘——红线：明文 Key 不进长期文件）
_CUSTOM_PROVIDERS_FILE = Path("data/llm_providers.json")


class ProviderCreate(BaseModel):
    provider: str = Field(..., description="provider 类型：deepseek / ollama")
    name: str = Field(..., min_length=1, max_length=64, description="显示名称")
    model: str = Field(..., min_length=1, max_length=128)
    base_url: str | None = None
    api_key: str | None = None


def _load_custom_providers() -> list[Dict[str, Any]]:
    try:
        if _CUSTOM_PROVIDERS_FILE.exists():
            return json.loads(_CUSTOM_PROVIDERS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("load custom providers failed: %s", exc)
    return []


def _save_custom_providers(items: list[Dict[str, Any]]) -> None:
    _CUSTOM_PROVIDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOM_PROVIDERS_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _build_provider(provider_type: str, model: str, api_key: str | None, base_url: str | None):
    """构建 provider 实例（key 仅本次进程生效）。"""
    from core.llm_gateway.deepseek import DeepSeekProvider
    from core.llm_gateway.ollama import OllamaProvider

    cls_map = {
        "deepseek": DeepSeekProvider,
        "ollama": OllamaProvider,
    }
    cls = cls_map.get(provider_type)
    if cls is None:
        raise HTTPException(status_code=400, detail=f"不支持的 provider 类型：{provider_type}")
    try:
        return cls(api_key=api_key, api_base=base_url, model=model)
    except TypeError:
        return cls(api_key=api_key, base_url=base_url, model=model)


@router.get("/providers", response_model=Dict[str, Any])
async def list_providers(claims: Dict[str, Any] = Depends(require_access_token)) -> Dict[str, Any]:
    """LLM 提供商目录 + 健康状态（2026-08-11：过滤未配置/mock，只显示真实可用的）。"""
    try:
        h = await llm_health()
        providers = h.get("providers", {}) if isinstance(h, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_health failed: %s", exc)
        providers = {}

    # 合并自定义提供商元数据（无 key 项标注 has_key=false）
    for item in _load_custom_providers():
        name = item.get("name") or item.get("provider")
        if name and name not in providers:
            providers[name] = {
                "provider": name,
                "ok": False,
                "error": "密钥未保存，需重新录入",
                "mode": "custom",
                "model": item.get("model", ""),
                "base_url": item.get("base_url", ""),
                "has_key": False,
            }

    # 过滤：只保留真实可用（ok=True 且非 mock）或自定义配置项
    filtered = {}
    for name, p in providers.items():
        mode = p.get("mode", "")
        if p.get("ok") and mode != "mock":
            filtered[name] = p
        elif mode == "custom":
            filtered[name] = p
    return {"providers": filtered, "supported": sorted(filtered.keys())}


@router.post("/providers", response_model=Dict[str, Any])
async def create_provider(payload: ProviderCreate, claims: Dict[str, Any] = Depends(require_access_token)) -> Dict[str, Any]:
    """新增 LLM 提供商：API Key 仅内存注册（不落盘），元数据持久化。

    重启后需重新录入 Key 才能生效——红线：明文 Key 不写长期文件。
    """
    # 1) 内存注册（带 key）
    if payload.api_key:
        provider = _build_provider(payload.provider, payload.model, payload.api_key, payload.base_url)
        register_provider(provider)

    # 2) 元数据持久化（无 key）
    items = _load_custom_providers()
    items = [i for i in items if i.get("name") != payload.name]
    items.append({
        "provider": payload.provider,
        "name": payload.name,
        "model": payload.model,
        "base_url": payload.base_url or "",
        "has_key": bool(payload.api_key),
    })
    _save_custom_providers(items)

    return {
        "name": payload.name,
        "provider": payload.provider,
        "model": payload.model,
        "key_saved_in_memory": bool(payload.api_key),
        "note": "Key 仅本次进程生效，重启后需重新录入",
    }


@router.get("/rules")
async def list_rules(claims: Dict[str, Any] = Depends(require_access_token)) -> Dict[str, Any]:
    """路由规则列表。返回 {items, total} 信封。"""
    try:
        settings = get_settings()
        rules = getattr(settings, "llm_routing_rules", None)
        if rules is None and hasattr(settings, "llm"):
            rules = getattr(settings.llm, "routing_rules", None)
        items = []
        if rules:
            for r in rules:
                items.append(r.model_dump() if hasattr(r, "model_dump") else dict(r))
        return {"items": items, "total": len(items)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_rules failed: %s", exc)
        return {"items": [], "total": 0}


@router.get("/fallback", response_model=Dict[str, Any])
async def fallback(claims: Dict[str, Any] = Depends(require_access_token)) -> Dict[str, Any]:
    """回退链。"""
    try:
        settings = get_settings()
        chain = getattr(settings, "llm_fallback_chain", None)
        if chain is None and hasattr(settings, "llm"):
            chain = getattr(settings.llm, "fallback_chain", None)
        return {"chain": chain or []}
    except Exception as exc:  # noqa: BLE001
        logger.warning("fallback failed: %s", exc)
        return {"chain": [], "error": str(exc)}
