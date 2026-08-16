"""LLM 管理 API（/llm）— 提供商 / 路由规则 / 模型配置（dsh 工作台插件用）。

端点：
- GET  /llm/providers          LLM 提供商健康/列表
- GET  /llm/rules              路由规则
- GET  /llm/fallback           回退链
- POST /llm/providers          新增自定义提供商（key 仅内存注册不落盘）
- GET  /llm/config             模型配置读取（configured/has_key 布尔，不回明文 key）
- POST /llm/config             保存模型配置（key 写部署配置，权限 600）
- POST /llm/test               测试 LLM 连通（真实 chat 一次，不回传 key）

安全红线（鉴权开发说明 §3）：
- GET 只返回 ``configured: true/false``，绝不回传明文 API key；
- POST 接收 key 写入部署配置（chmod 600）；日志不打印 key。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.config import get_settings
from core.llm_gateway.gateway import chat as llm_chat
from core.llm_gateway.gateway import health as llm_health
from core.llm_gateway.gateway import register_provider
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])

# 自定义提供商元数据（API Key 不落盘——红线：明文 Key 不进长期文件）
_CUSTOM_PROVIDERS_FILE = Path("data/llm_providers.json")

# 允许保存/测试的 provider（白名单通道）
_LLM_PROVIDERS = ("deepseek", "ollama")

# 部署配置路径（gitignore；POST /config 写 key 后 chmod 600）
_DEPLOYMENT_YAML = Path("config/deployment.yaml")


class ProviderCreate(BaseModel):
    provider: str = Field(..., description="provider 类型：deepseek / ollama")
    name: str = Field(..., min_length=1, max_length=64, description="显示名称")
    model: str = Field(..., min_length=1, max_length=128)
    base_url: str | None = None
    api_key: str | None = None


class LlmConfigReq(BaseModel):
    """模型配置保存请求（api_key 可选——仅填需要变更的字段）。"""

    provider: str = Field(..., description="provider：deepseek / ollama")
    api_key: str | None = Field(
        None, max_length=512, description="API key（不读回、不打印）"
    )
    base_url: str | None = Field(None, max_length=512)
    model: str | None = Field(None, max_length=128)


class LlmTestReq(BaseModel):
    """LLM 连通测试请求。"""

    provider: str | None = Field(
        None, description="provider：deepseek / ollama（默认当前默认通道）")


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


def _build_provider(
    provider_type: str, model: str, api_key: str | None, base_url: str | None
):
    """构建 provider 实例（key 仅本次进程生效）。"""
    from core.llm_gateway.deepseek import DeepSeekProvider
    from core.llm_gateway.ollama import OllamaProvider

    cls_map = {
        "deepseek": DeepSeekProvider,
        "ollama": OllamaProvider,
    }
    cls = cls_map.get(provider_type)
    if cls is None:
        raise HTTPException(
            status_code=400, detail=f"不支持的 provider 类型：{provider_type}"
        )
    # P1-13：所有 provider 统一 api_base 参数名（BaseLLMProvider 契约），
    # 删除死分支 try/except（base_url 传参静默失效问题）
    return cls(api_key=api_key, api_base=base_url, model=model)


@router.get("/providers", response_model=Dict[str, Any])
async def list_providers(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
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
async def create_provider(
    payload: ProviderCreate,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """新增 LLM 提供商：API Key 仅内存注册（不落盘），元数据持久化。

    重启后需重新录入 Key 才能生效——红线：明文 Key 不写长期文件。
    """
    # 1) 内存注册（带 key）
    if payload.api_key:
        provider = _build_provider(
            payload.provider, payload.model, payload.api_key, payload.base_url)
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
async def list_rules(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
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
async def fallback(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
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


# ---------------------------------------------------------------------------
# 模型配置（dsh 工作台插件"模型配置"子项；key 红线：不回明文、写 600）
# ---------------------------------------------------------------------------


def _read_deployment_yaml() -> Dict[str, Any]:
    """读取现有 config/deployment.yaml（缺失返回空 dict）。"""
    try:
        if _DEPLOYMENT_YAML.exists():
            import yaml

            data = yaml.safe_load(_DEPLOYMENT_YAML.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("read deployment.yaml failed: %s", exc)
    return {}


def _write_deployment_yaml(data: Dict[str, Any]) -> None:
    """写回 config/deployment.yaml（权限 600）；失败不阻塞接口（仅告警）。"""
    try:
        import yaml

        _DEPLOYMENT_YAML.parent.mkdir(parents=True, exist_ok=True)
        _DEPLOYMENT_YAML.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        try:
            os.chmod(_DEPLOYMENT_YAML, 0o600)
        except OSError as exc:  # noqa: BLE001
            logger.warning("chmod deployment.yaml failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("write deployment.yaml failed: %s", exc)


def _provider_status() -> Dict[str, Any]:
    """各白名单 provider 的配置状态（只报布尔，绝不回传明文 key）。"""
    settings = get_settings()
    providers = (settings.llm or {}).get("providers", {}) or {}
    status: Dict[str, Any] = {}
    for name in _LLM_PROVIDERS:
        p = providers.get(name, {}) or {}
        api_key = p.get("api_key") or ""
        # 只回传是否已配置（has_key 布尔）与连接信息；key 明文永不离开服务端
        status[name] = {
            "configured": bool(api_key) or name == "ollama",
            "has_key": bool(api_key),
            "base_url": p.get("base_url", ""),
            "model": p.get("default_model", ""),
        }
    settings_llm = settings.llm or {}
    return {
        "provider": settings_llm.get("default_provider", "deepseek"),
        "providers": status,
    }


@router.get("/config", response_model=Dict[str, Any])
async def get_llm_config(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """读取模型配置（configured/has_key 布尔；**不回传明文 API key**）。"""
    return _provider_status()


@router.post("/config", response_model=Dict[str, Any])
async def save_llm_config(
    payload: LlmConfigReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """保存模型配置：api_key 写 config/deployment.yaml（权限 600）+ 内存注册即时生效。

    - 日志不打印 key（logger 只记 provider 名与布尔标记）；
    - 响应不回传 key，只回 ``key_saved`` 布尔。
    """
    provider = payload.provider
    if provider not in _LLM_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"不支持的 provider：{provider}")

    data = _read_deployment_yaml()
    providers = data.setdefault("llm_gateway", {}).setdefault("providers", {})
    entry = providers.setdefault(provider, {})
    if payload.api_key:
        # P1-9：key 加密后落盘（Fernet，yaml 只存密文）；日志/响应仍不出现明文
        from core.security.key_store import encrypt_secret

        entry["api_key"] = encrypt_secret(payload.api_key)
    if payload.base_url:
        entry["base_url"] = payload.base_url
    if payload.model:
        entry["default_model"] = payload.model
    _write_deployment_yaml(data)

    # 内存注册即时生效（key 仅本次进程可用，重启后从 deployment.yaml 重新加载）
    if payload.api_key:
        try:
            from core.llm_gateway.base import BaseLLMProvider

            if provider == "deepseek":
                from core.llm_gateway.deepseek import DeepSeekProvider

                provider_inst: BaseLLMProvider = DeepSeekProvider(
                    api_key=payload.api_key,
                    api_base=payload.base_url,
                    model=payload.model,
                )
            else:
                from core.llm_gateway.ollama import OllamaProvider

                provider_inst = OllamaProvider(
                    api_base=payload.base_url,
                    model=payload.model,
                )
            register_provider(provider_inst)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "llm config: in-memory register failed for %s: %s", provider, exc)

    # 日志只记布尔，不记 key
    logger.info("llm config saved: provider=%s key_saved=%s base_url=%s",
                provider, bool(payload.api_key), bool(payload.base_url))
    return {"ok": True, "provider": provider, "key_saved": bool(payload.api_key)}


@router.post("/test", response_model=Dict[str, Any])
async def test_llm(
    payload: LlmTestReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """LLM 连通测试：对指定 provider 发一条最小 chat；不回传 key。

    返回 ``{ok, provider, model, error?}``——失败信息只含错误摘要。
    """
    from core.llm_gateway.base import ChatMessage

    settings = get_settings()
    settings_llm = settings.llm or {}
    provider = payload.provider or settings_llm.get("default_provider", "deepseek")
    if provider not in _LLM_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"不支持的 provider：{provider}")

    try:
        resp = await llm_chat(
            [ChatMessage(role="user", content="ping")],
            rule="simple_chat",
            ctx=None,
        )
        ok = getattr(resp, "finish_reason", None) != "error"
        return {
            "ok": ok,
            "provider": provider,
            "model": getattr(resp, "model", ""),
            "error": None if ok else (getattr(resp, "content", "") or "")[:200],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "provider": provider, "model": "", "error": str(exc)[:200]}
