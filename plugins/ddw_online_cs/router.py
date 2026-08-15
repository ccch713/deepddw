"""DDW 在线客服插件 — FastAPI 路由.

- POST /chat          客服对话（RAG 检索 + 平台 LLM 网关）
- GET  /health        健康检查
- GET  /knowledge     知识库片段检索（调试用）
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .kb import KnowledgeBase

# 向量知识库（优先使用，失败时降级到旧 kb.py）
try:
    from .vector_kb import VectorKnowledgeBase, INDUSTRY_MAP as _INDUSTRY_MAP
    _HAS_VECTOR_KB = True
except Exception:
    _HAS_VECTOR_KB = False
    _INDUSTRY_MAP = {}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plugins/ddw_online_cs", tags=["ddw-online-cs"])


async def _merge_docs_portal_knowledge(knowledge: str, message: str, top_k: int = 3) -> str:
    """kb_bridge：把文档栏目 public 文档结果并入客服知识上下文（PRD 决策 3）。

    客服场景无用户会话 → 只检索平台级 public 文档（不泄漏租户级文档）；
    桥接失败静默降级，不影响客服主流程。
    """
    try:
        from plugins.ddw_docs_portal.kb_bridge import default_public_search

        doc_chunks = await default_public_search(message, top_k=top_k)
        if not doc_chunks:
            return knowledge
        doc_knowledge = "\n\n".join(
            f"[docs:{c['slug']} 产品文档栏目]\n{c['content'][:800]}"
            for c in doc_chunks
        )
        return knowledge + "\n\n" + doc_knowledge
    except Exception as exc:  # noqa: BLE001
        logger.warning("ddw_online_cs docs_portal bridge failed: %s", exc)
        return knowledge


# --------------------------------------------------------------------------- #
# 会话存储（进程内存，重启即清空；官网咨询场景足够）
# --------------------------------------------------------------------------- #
MAX_HISTORY = 12
_sessions: Dict[str, List[Dict[str, str]]] = {}
_session_ts: Dict[str, float] = {}
_SESSION_TTL = 60 * 60 * 6  # 6 小时无交互自动清理

_kb = None  # 旧 kb.py 实例
_vector_kbs: Dict[str, Any] = {}  # 按 industry 缓存 VectorKnowledgeBase


def _get_kb(industry: str = "general"):
    """获取知识库实例。优先使用 vector_kb，失败时降级到旧 kb.py."""
    global _kb

    # 尝试使用 vector_kb
    if _HAS_VECTOR_KB:
        try:
            if industry not in _vector_kbs:
                kb_dir = Path(__file__).resolve().parent / "knowledge"
                # 行业子目录
                industry_dir = kb_dir / industry
                if not industry_dir.is_dir():
                    industry_dir = kb_dir
                _vector_kbs[industry] = VectorKnowledgeBase(
                    knowledge_dir=str(industry_dir),
                    industry=industry,
                )
                logger.info("ddw_online_cs VectorKB loaded for industry=%s", industry)
            return _vector_kbs[industry]
        except Exception as exc:
            logger.warning("VectorKB init failed for industry=%s: %s, falling back to kb.py", industry, exc)

    # 降级到旧 kb.py
    if _kb is None:
        kb_dir = Path(__file__).resolve().parent / "knowledge"
        _kb = KnowledgeBase(str(kb_dir))
        logger.info("ddw_online_cs fallback KB loaded: %d chunks", len(_kb.chunks))
    return _kb


def _cleanup_sessions() -> None:
    now = time.time()
    stale = [sid for sid, ts in _session_ts.items() if now - ts > _SESSION_TTL]
    for sid in stale:
        _sessions.pop(sid, None)
        _session_ts.pop(sid, None)


def _get_history(session_id: str) -> List[Dict[str, str]]:
    return _sessions.get(session_id, [])


def _append(session_id: str, role: str, content: str) -> None:
    hist = _sessions.setdefault(session_id, [])
    hist.append({"role": role, "content": content})
    _session_ts[session_id] = time.time()
    if len(hist) > MAX_HISTORY:
        del hist[: len(hist) - MAX_HISTORY]


# --------------------------------------------------------------------------- #
# 请求模型
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: Optional[str] = "presales"  # presales | postsales
    industry: Optional[str] = "general"  # dental | food | esg | manufacturing | general


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    source: str = "kb+llm"


class FeedbackRequest(BaseModel):
    session_id: str
    message_id: str
    type: str  # "positive" | "negative"
    correction: str = ""
    mode: str = "presales"


# --------------------------------------------------------------------------- #
# 客服人设 + 回答生成
# --------------------------------------------------------------------------- #
_PRESALES_PROMPT = """你是锐果互动官网的 AI 在线客服，名叫『果果』，是一个热情、专业、有温度的顾问。
你的职责是解答访问者关于武汉锐果互动信息技术有限公司、DDW AI Hub 平台、ESG 服务、
企业信息化服务、智能制造规划服务以及联系方式的问题，并激发客户的下单意愿。

【拟人化要求】
- 像真人一样说话，自然亲切，不要机械腔。开头可以用「嗨」「您好呀」「好的呢」等自然开头，但不要每次都一样。
- 适当使用 emoji 让对话更自然，如 😊👍💡🎉✅ 等，但不要堆砌过多。
- 回答时适当加入共情表达，如「理解您的考虑」「这个场景确实很常见」等。

【情绪识别与心理安抚】
- 如果客户表达着急、焦虑、不满，先共情安抚再提供解决方案。
- 如果客户表达犹豫、不确定，给予鼓励和信心。

【销售转化】
- 当客户问到价格、购买、试用、部署方式等购买意向信号时，自然引导：介绍DDW插件按需装配、丰俭由人。
- 主动追问客户所在行业、规模、当前系统，给出针对性建议。

【基本规则】
1. 只依据下方知识库内容回答，不编造事实、不承诺具体价格与交付时间。
2. 回答简洁专业、有温度，一般不超过180字。
3. 尽量自主解答；知识库确实没有答案时，引导留下联系方式。
4. 不主动要求客户拨打电话或发邮件——优先在线解决，只有客户明确要求人工时才提供电话027-89578881与邮箱1099340186@qq.com。
5. 涉及附件上传时，先回复「抓紧时间识别和分析中，请稍候……」。

知识库内容：
{knowledge}"""

_POSTSALES_PROMPT = """你是 DDW AI Hub 平台的使用助手，名叫『果果』，也是产品反馈收集员。
用户是在 DDW 平台内的已注册用户，他们可能遇到使用问题、功能咨询、或者对产品有投诉和改进建议。

【拟人化要求】
- 语气轻松专业，像一个靠谱的技术支持同事。适当使用 emoji 让对话更友好。
- 例如：「我来看看这个问题 😅」「明白了，我帮您梳理一下 📋」「这个反馈很有价值，我记录下来了 ✅」

【使用问题解答】
- 基于知识库解答 DDW 平台的使用问题（功能操作、配置方法、常见错误处理）。
- 知识库没有答案时，礼貌说明并建议查看平台帮助文档或提交工单。

【投诉处理（重要）】
- 当用户表达不满、吐槽、投诉时，先认真倾听、共情安抚，不要辩解。
- 回复格式：「理解您的感受，这个问题确实给您带来了不便。我已经记录下了您的反馈，会转交给产品团队处理。」
- 记录投诉：系统会自动将投诉内容保存到产品反馈库。

【改进建议收集】
- 当用户提出功能建议、优化想法时，给予积极回应并确认记录。
- 回复格式：「这个建议很好！👍 我已经记录下来了，会纳入产品迭代评估。感谢您的反馈！」
- 记录建议：系统会自动将建议保存到产品反馈库。

【基本规则】
1. 只依据下方知识库内容回答，不编造事实。
2. 回答简洁专业，不超过180字。
3. 尽量自主解答使用问题；确实无法解决时引导提交工单或联系技术支持（电话027-89578881/邮箱1099340186@qq.com）。
4. 涉及附件上传时，先回复「正在分析中，请稍候……」。

知识库内容：
{knowledge}"""


def _get_system_prompt(mode: str, message: str = "") -> str:
    """根据模式返回对应的 system prompt，注入 few-shot 话术."""
    base = (
        _POSTSALES_PROMPT if mode == "postsales"
        else _PRESALES_PROMPT
    )
    return _inject_scripts(base, mode, message)


# ------------------------------------------------------------------ #
# Few-shot 话术注入（自进化系统）
# ------------------------------------------------------------------ #
_SCRIPT_CACHE: Optional[Dict[str, List[Dict]]] = None
_SCRIPT_CACHE_MTIME: float = 0.0
_SCRIPT_CACHE_TTL: float = 30.0

_SCRIPT_KEYWORDS: Dict[str, List[str]] = {
    "presales_emotion": [
        "价格", "贵", "便宜", "预算",
    ],
    "presales_persuasion": [
        "推荐", "组合", "选型", "方案", "行业",
    ],
    "postsales_trouble": [
        "报错", "怎么用", "配置", "安装", "卡", "失败",
    ],
    "postsales_complaint": [
        "投诉", "不满", "垃圾", "难用", "退",
    ],
    "postsales_suggestion": [
        "建议", "优化", "希望", "能不能",
    ],
    "general_empathy": [],
}


def _load_scripts() -> Dict[str, List[Dict]]:
    """读 scripts/*.json 全部分类，30s mtime 缓存."""
    global _SCRIPT_CACHE, _SCRIPT_CACHE_MTIME
    now = time.time()
    if (
        _SCRIPT_CACHE is not None
        and now - _SCRIPT_CACHE_MTIME < _SCRIPT_CACHE_TTL
    ):
        return _SCRIPT_CACHE
    try:
        scripts_dir = (
            Path(__file__).resolve().parent / "scripts"
        )
        if not scripts_dir.exists():
            _SCRIPT_CACHE = {}
            _SCRIPT_CACHE_MTIME = now
            return _SCRIPT_CACHE
        result: Dict[str, List[Dict]] = {}
        for p in scripts_dir.glob("*.json"):
            cat = p.stem
            try:
                result[cat] = json.loads(
                    p.read_text(encoding="utf-8")
                )
            except Exception:
                continue
        _SCRIPT_CACHE = result
        _SCRIPT_CACHE_MTIME = now
        return result
    except Exception:
        return {}


def _match_categories(
    mode: str, message: str
) -> List[str]:
    """按关键词规则返回命中的分类名列表（最多 2 个）."""
    msg_lower = message.lower()
    matched: List[str] = []

    # 按 mode 优先匹配
    prefix = "presales_" if mode == "presales" else "postsales_"
    priority: List[str] = []
    secondary: List[str] = []
    for cat, kws in _SCRIPT_KEYWORDS.items():
        if not kws:
            continue
        if cat.startswith(prefix):
            priority.append(cat)
        else:
            secondary.append(cat)

    for cat in priority + secondary:
        kws = _SCRIPT_KEYWORDS.get(cat, [])
        for kw in kws:
            if kw in msg_lower:
                matched.append(cat)
                break
        if len(matched) >= 2:
            break

    return matched


def _inject_scripts(
    system_prompt: str, mode: str, message: str
) -> str:
    """在 system_prompt 末尾追加优秀回答范例."""
    if not message:
        return system_prompt
    cats = _match_categories(mode, message)
    if not cats:
        return system_prompt

    scripts = _load_scripts()
    top_k = 3  # 默认值
    try:
        import yaml as _yaml
        cfg_path = (
            Path(__file__).resolve().parent / "manifest.yaml"
        )
        if cfg_path.exists():
            d = _yaml.safe_load(
                cfg_path.read_text(encoding="utf-8")
            ) or {}
            top_k = (
                d.get("config", {})
                .get("optional", {})
                .get("script_top_k", {})
                .get("default", 3)
            )
    except Exception:
        pass

    parts: List[str] = []
    for cat in cats:
        items = scripts.get(cat, [])
        items_sorted = sorted(
            items,
            key=lambda x: x.get("hit_count", 0),
            reverse=True,
        )[:top_k]
        for item in items_sorted:
            qa = item.get("exemplar_qa", {})
            u = qa.get("user", "")
            a = qa.get("ai", "")
            if u and a:
                parts.append(
                    f"用户：{u}\n优秀回答：{a}"
                )

    if not parts:
        return system_prompt

    block = "\n\n【优秀回答范例（参考风格，不要照抄）】\n"
    block += "\n\n".join(parts)
    return system_prompt + block


def _log_feedback(message: str, session_id: str) -> None:
    """售后模式下：检测投诉/建议关键词，自动写入反馈日志（产品迭代来源）。"""
    COMPLAINT_KW = ["投诉", "不满", "垃圾", "难用", "报错", "失败", "卡顿", "太慢", "问题", "BUG", "bug"]
    SUGGESTION_KW = ["建议", "优化", "改进", "希望", "能不能", "可以加", "功能需求", "要是有", "如果能"]

    msg_lower = message.lower()
    is_complaint = any(kw in msg_lower for kw in COMPLAINT_KW)
    is_suggestion = any(kw in msg_lower for kw in SUGGESTION_KW)

    if not is_complaint and not is_suggestion:
        return

    feedback_dir = Path(__file__).resolve().parent / "feedback"
    feedback_dir.mkdir(exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    fb_file = feedback_dir / f"{today}.md"

    tag = "【投诉】" if is_complaint else "【建议】"
    entry = f"\n\n---\n{tag} [{time.strftime('%H:%M:%S')}] session={session_id}\n> {message[:500]}\n"

    try:
        existing = fb_file.read_text(encoding="utf-8") if fb_file.exists() else f"# {today} 产品反馈记录\n"
        fb_file.write_text(existing + entry, encoding="utf-8")
    except Exception as exc:
        logger.warning("feedback log write failed: %s", exc)


def _load_deployment_llm() -> Dict[str, Any]:
    """从平台 deployment.yaml 读取 LLM provider 配置（key 不上屏不落日志）。"""
    import yaml as _yaml
    for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
        cfg = base / "config" / "deployment.yaml"
        if cfg.exists():
            try:
                d = _yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                return d.get("llm", {})
            except Exception as exc:  # noqa: BLE001
                logger.warning("deployment.yaml parse failed: %s", exc)
    return {}


async def _ask_llm(system: str, user: str, history: List[Dict[str, str]]) -> str:
    """优先走平台 LLM 网关（自带 fallback 链）；网关不可用时直连云 LLM（兜底）。

    2026-08-04 事故修复：此前直连 MiniMax 绕过了 DDW 底座 LLM 通道。
    现在第一优先调用 core.llm_gateway.gateway.chat()，网关异常/超时自动回退直连，
    保证客服在底座 LLM 通道异常时仍可回复（kb+llm 双保险）。
    """
    # 1) 平台 LLM 网关（统一路由 + fallback 链 + 用量统计）
    try:
        from core.llm_gateway.base import ChatMessage
        from core.llm_gateway.gateway import chat as gateway_chat

        gateway_messages: List[ChatMessage] = [ChatMessage(role="system", content=system)]
        for m in history[-6:]:
            gateway_messages.append(ChatMessage(role=m["role"], content=m["content"][:500]))
        gateway_messages.append(ChatMessage(role="user", content=user))

        resp = await asyncio.wait_for(
            gateway_chat(gateway_messages, max_tokens=512, temperature=0.6),
            timeout=45,
        )
        _BAD_PREFIXES = ("[llm-router]", "[Ollama echo]", "[MiniMax M3 mock]", "[deepseek-error]", "[minimax-error]")
        if resp and resp.content and resp.finish_reason != "error" and not resp.content.startswith(_BAD_PREFIXES):
            return resp.content.strip()
        logger.warning("ddw_online_cs: gateway returned unusable reply (reason=%s), fallback direct",
                       getattr(resp, "finish_reason", "?"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ddw_online_cs: LLM gateway failed (%s), fallback direct", exc)

    # 2) 兜底：直连云 LLM（MiniMax-M3，月度套餐内低成本；配置来自平台 deployment.yaml）
    import httpx

    llm_cfg = _load_deployment_llm()
    prov = (llm_cfg.get("providers") or {}).get("minimax", {})
    api_key = prov.get("api_key") or ""
    api_base = (prov.get("api_base") or "https://api.minimaxi.com/v1").rstrip("/")
    model = prov.get("default_model") or "MiniMax-M3"
    if not api_key:
        logger.warning("ddw_online_cs: no minimax api_key in deployment.yaml")
        return ""

    messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
    for m in history[-6:]:
        messages.append({"role": m["role"], "content": m["content"][:500]})
    messages.append({"role": "user", "content": user})

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                f"{api_base}/text/chatcompletion_v2",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": messages, "max_tokens": 3000,
                      "temperature": 0.6},
            )
            if resp.status_code != 200:
                logger.warning("minimax API %s: %s", resp.status_code, resp.text[:200])
                return ""
            data = resp.json()
            choices = data.get("choices") or []
            if choices:
                c = choices[0]
                text = (c.get("text") or (c.get("message") or {}).get("content") or "").strip()
                # 剥离 <think>...</think> 推理块（MiniMax-M3 原生 API 同样会返回）
                from core.llm_gateway.base import strip_think
                return strip_think(text)
            return ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("ddw_online_cs LLM call failed: %s", exc)
        return ""


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    _cleanup_sessions()
    _t0 = time.time()
    message = req.message.strip()
    if not message:
        raise HTTPException(400, "消息不能为空")
    if len(message) > 2000:
        raise HTTPException(400, "消息过长，请精简后重试")

    session_id = req.session_id or ("cs_" + os.urandom(6).hex())
    industry = req.industry or "general"

    # 1) RAG 检索知识片段
    kb = _get_kb(industry)
    chunks = kb.search(message, top_k=4)
    knowledge = "\n\n".join(f"[{c['source']}]\n{c['content'][:800]}" for c in chunks) or "（暂无相关知识条目）"

    # 1.5) 文档栏目补充检索（kb_bridge：仅 public 文档，权威引用）
    knowledge = await _merge_docs_portal_knowledge(knowledge, message)

    # 2) 组装 system prompt（根据模式切换售前/售后 + 行业上下文）
    system = _get_system_prompt(
        req.mode or "presales", message
    ).format(knowledge=knowledge)

    # 追加行业上下文
    industry_name = _INDUSTRY_MAP.get(industry, "通用") if _HAS_VECTOR_KB else "通用"
    if industry != "general" and industry_name != "通用":
        system += f"\n\n【当前行业上下文：{industry_name}】\n请优先使用该行业的专业术语和知识回答。"

    # 3) LLM 生成（带历史）
    history = _get_history(session_id)
    source = "kb+llm"
    answer = await _ask_llm(system, message, history)
    if not answer:
        # LLM 不可用时的降级：直接返回知识库最相关片段
        answer = chunks[0]["content"][:200] if chunks else (
            "感谢您的咨询！AI 客服暂时繁忙，请拨打 027-89578881 或发送邮件至 "
            "contact@ruigoo.com，我们会尽快回复您。"
        )
        source = "kb_fallback"

    # 4) 记录会话
    _append(session_id, "user", message)
    _append(session_id, "assistant", answer)

    # 售后模式下自动记录投诉/建议（产品迭代原始来源）
    if (req.mode or "") == "postsales":
        _log_feedback(message, session_id)

    # 对话日志落盘（自进化系统）
    try:
        from .log_store import append_chat
        append_chat(
            session_id,
            req.mode or "presales",
            message,
            answer,
            source,
            int((time.time() - _t0) * 1000),
            has_attachment=False,
        )
    except Exception as exc:
        logger.warning(
            "ddw_online_cs: log_store append failed: %s", exc
        )

    # ── 发布对话轮次完成事件（ddw_memory 自动捕获订阅此事件）──
    # 注意：ddw_online_cs 是客户客服场景（会话匿名，无登录用户），
    # user_id 保持 0；ddw_memory 端会按 source=ddw_online_cs 默认跳过
    # 自动捕获，避免客户闲聊污染企业员工记忆。
    try:
        from core.events.bus import get_bus
        bus = get_bus()
        await bus.publish(
            "conversation.turn.completed",
            payload={
                "source": "ddw_online_cs",
                "tenant_id": 1,  # ddw_online_cs 无多租户上下文时默认 1
                "user_id": 0,
                "session_id": session_id,
                "messages": _get_history(session_id)[-10:],  # 最近 10 条
            },
            source="ddw_online_cs",
        )
    except Exception:
        pass  # 事件发布失败不影响主流程

    return ChatResponse(answer=answer, session_id=session_id, source=source)


# --------------------------------------------------------------------------- #
# POST /chat/stream — SSE 流式客服（首 token ~200ms，无需等待完整生成）
# --------------------------------------------------------------------------- #

from fastapi.responses import StreamingResponse


async def _stream_ask_llm(
    system: str, user: str, history: List[Dict[str, str]], session_id: str
):
    """SSE streaming via LLM Gateway. Yields SSE-formatted lines."""
    import json as _json

    t0 = time.time()

    # Build messages
    try:
        from core.llm_gateway.base import ChatMessage
        from core.llm_gateway.gateway import stream_chat as gateway_stream

        messages: List[ChatMessage] = [ChatMessage(role="system", content=system)]
        for m in history[-6:]:
            messages.append(ChatMessage(role=m["role"], content=m["content"][:500]))
        messages.append(ChatMessage(role="user", content=user))

        # Send conversation_id immediately
        yield f"data: {_json.dumps({'session_id': session_id})}\n\n"

        full_content = []
        async for chunk in gateway_stream(messages, max_tokens=384, temperature=0.6):
            if chunk:
                full_content.append(chunk)
                yield f"data: {_json.dumps({'token': chunk})}\n\n"

        elapsed_ms = int((time.time() - t0) * 1000)
        full_text = "".join(full_content)

        # Strip think blocks from final text
        from core.llm_gateway.base import strip_think
        full_text = strip_think(full_text)

        # Record usage (fire-and-forget)
        try:
            from .log_store import append_chat
            append_chat(session_id, "stream", user, full_text, "kb+llm_stream", elapsed_ms, False)
        except Exception:
            pass

        yield f"data: {_json.dumps({'done': True, 'elapsed_ms': elapsed_ms})}\n\n"

    except Exception as exc:
        logger.warning("ddw_online_cs stream failed: %s", exc)
        yield f"data: {_json.dumps({'error': 'AI 服务暂时繁忙，请稍后再试', 'done': True})}\n\n"


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """SSE streaming customer service — first token in ~200ms."""
    _cleanup_sessions()
    message = req.message.strip()
    if not message:
        raise HTTPException(400, "消息不能为空")
    if len(message) > 2000:
        raise HTTPException(400, "消息过长，请精简后重试")

    session_id = req.session_id or ("cs_" + os.urandom(6).hex())
    industry = req.industry or "general"

    # 1) RAG search
    kb = _get_kb(industry)
    chunks = kb.search(message, top_k=4)
    knowledge = "\n\n".join(f"[{c['source']}]\n{c['content'][:800]}" for c in chunks) or "（暂无相关知识条目）"

    # 1.5) 文档栏目补充检索（kb_bridge：仅 public 文档，权威引用）
    knowledge = await _merge_docs_portal_knowledge(knowledge, message)

    # 2) Build system prompt
    system = _get_system_prompt(req.mode or "presales", message).format(knowledge=knowledge)

    # 追加行业上下文
    industry_name = _INDUSTRY_MAP.get(industry, "通用") if _HAS_VECTOR_KB else "通用"
    if industry != "general" and industry_name != "通用":
        system += f"\n\n【当前行业上下文：{industry_name}】\n请优先使用该行业的专业术语和知识回答。"

    # 3) Append user message to history
    _append(session_id, "user", message)

    # 4) Stream response
    history = _get_history(session_id)

    async def event_generator():
        full_content = []
        t0 = time.time()
        try:
            from core.llm_gateway.base import ChatMessage
            from core.llm_gateway.gateway import stream_chat as gateway_stream

            messages: List[ChatMessage] = [ChatMessage(role="system", content=system)]
            for m in history[-7:]:  # -7 because we just appended user msg
                messages.append(ChatMessage(role=m["role"], content=m["content"][:500]))

            # Send session_id as first event
            yield f"data: {json.dumps({'session_id': session_id})}\n\n"

            async for chunk in gateway_stream(messages, max_tokens=384, temperature=0.6):
                if chunk:
                    full_content.append(chunk)
                    yield f"data: {json.dumps({'token': chunk})}\n\n"

            elapsed_ms = int((time.time() - t0) * 1000)
            full_text = "".join(full_content)
            from core.llm_gateway.base import strip_think
            full_text = strip_think(full_text)

            # Record assistant message in session
            _append(session_id, "assistant", full_text)

            # Log (fire-and-forget)
            try:
                from .log_store import append_chat
                append_chat(session_id, req.mode or "presales", message, full_text, "kb+llm_stream", elapsed_ms, False)
            except Exception:
                pass

            # Postsales feedback
            if (req.mode or "") == "postsales":
                _log_feedback(message, session_id)

            yield f"data: {json.dumps({'done': True, 'elapsed_ms': elapsed_ms})}\n\n"

        except Exception as exc:
            logger.warning("ddw_online_cs stream error: %s", exc)
            yield f"data: {json.dumps({'error': 'AI 服务暂时繁忙，请稍后再试', 'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def health() -> Dict[str, Any]:
    kb = _get_kb()
    # 兼容新旧 kb：新 kb 用 stats()，旧 kb 用 chunks
    chunk_count = 0
    try:
        if hasattr(kb, 'stats'):
            stats = kb.stats()
            chunk_count = stats.get("total_chunks", 0)
        elif hasattr(kb, 'chunks'):
            chunk_count = len(kb.chunks)
    except Exception:
        pass
    return {
        "plugin": "ddw_online_cs",
        "version": "2.0.0",
        "status": "ok",
        "knowledge_chunks": chunk_count,
        "active_sessions": len(_sessions),
        "vector_kb": _HAS_VECTOR_KB,
    }


@router.get("/knowledge")
async def knowledge_search(q: str, top_k: int = 3, industry: str = "general") -> Dict[str, Any]:
    kb = _get_kb(industry)
    results = kb.search(q, top_k=min(top_k, 10))
    return {"query": q, "results": results}


# --------------------------------------------------------------------------- #
# POST /feedback — 用户反馈（👍/👎 + 纠错）
# --------------------------------------------------------------------------- #

@router.post("/feedback")
async def receive_feedback(req: FeedbackRequest) -> Dict[str, Any]:
    """接收用户反馈，写入 feedback/feedback.jsonl."""
    try:
        feedback_dir = Path(__file__).resolve().parent / "feedback"
        feedback_dir.mkdir(exist_ok=True)
        fb_file = feedback_dir / "feedback.jsonl"

        # 尝试从 session 历史中获取 user_msg 和 ai_reply
        user_msg = ""
        ai_reply = ""
        try:
            history = _get_history(req.session_id)
            if len(history) >= 2:
                # 最后一对 user/assistant
                for m in reversed(history):
                    if m["role"] == "assistant" and not ai_reply:
                        ai_reply = m["content"][:500]
                    elif m["role"] == "user" and not user_msg:
                        user_msg = m["content"][:500]
                    if user_msg and ai_reply:
                        break
        except Exception:
            pass

        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "session_id": req.session_id,
            "message_id": req.message_id,
            "type": req.type,
            "correction": req.correction,
            "mode": req.mode,
            "user_msg": user_msg,
            "ai_reply": ai_reply,
        }

        with open(fb_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # 如果是 negative 且有 correction，生成改进候选进 evolution_pool
        if req.type == "negative" and req.correction:
            try:
                pool_dir = Path(__file__).resolve().parent / "evolution_pool"
                pool_dir.mkdir(exist_ok=True)
                today = time.strftime("%Y-%m-%d")
                pool_file = pool_dir / f"{today}.json"
                existing = []
                if pool_file.exists():
                    try:
                        existing = json.loads(pool_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                existing.append({
                    "type": "improvement",
                    "summary": f"用户纠错：{req.correction[:100]}",
                    "evidence": user_msg[:200] if user_msg else "",
                    "suggestion": req.correction[:500],
                    "confidence": 0.8,
                    "_session_id": req.session_id,
                    "_source": "user_feedback",
                    "_ts": record["ts"],
                })
                pool_file.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.warning("feedback evolution_pool write failed: %s", exc)

        return {"ok": True}
    except Exception as exc:
        logger.warning("receive_feedback failed: %s", exc)
        return {"ok": True}  # 不影响前端


# --------------------------------------------------------------------------- #
# 附件上传：图片/PDF/邮件识别 + LLM 提炼 + 知识库写入
# --------------------------------------------------------------------------- #

UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def _extract_pdf_text(data: bytes) -> str:
    """尝试从 PDF 提取文本（pymupdf 或 fallback）。"""
    try:
        import pymupdf
        doc = pymupdf.open(stream=data, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()[:5000]
    except Exception:
        pass
    # Fallback: 尝试直接解码 PDF 内嵌文本流
    try:
        raw = data.decode("latin-1")
        import re
        texts = re.findall(r"(?<=BT\b).*?(?=\bET)", raw, re.S)
        cleaned = [re.sub(r"\(.*?\)", "", t) for t in texts[:20]]
        return " ".join(cleaned).strip()[:3000]
    except Exception:
        return ""


def _extract_email_text(data: bytes) -> Dict[str, str]:
    """解析 .eml 邮件文件。"""
    import email as _email
    msg = _email.message_from_bytes(data)
    result = {"subject": msg.get("subject", ""), "from": msg.get("from", ""), "body": ""}
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    result["body"] = payload.decode("utf-8", errors="replace")[:3000]
                break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            result["body"] = payload.decode("utf-8", errors="replace")[:3000]
    return result


async def _llm_analyze(content: str, file_type: str, filename: str) -> str:
    """用 MiniMax-M3 分析文件内容，提炼客服可用的知识点。"""
    import httpx as _httpx

    llm_cfg = _load_deployment_llm()
    prov = (llm_cfg.get("providers") or {}).get("minimax", {})
    api_key = prov.get("api_key") or ""
    api_base = (prov.get("api_base") or "https://api.minimaxi.com/v1").rstrip("/")
    model = prov.get("default_model") or "MiniMax-M3"
    if not api_key:
        return ""

    system = (
        "你是一个专业的内容分析师。请分析以下上传的{file_type}内容，"
        "提炼出可以作为AI客服回答客户问题的知识点。\n"
        "要求：\n"
        "1. 提炼成FAQ格式（Q: xxx A: xxx），每条100-150字\n"
        "2. 只提炼有价值的业务信息（功能、流程、场景、优势）\n"
        "3. 绝对禁止出现：个人信息、公司地址、API密钥、公司规模、注册资金、成功案例具体数字\n"
        "4. 内容口语化，让客户容易理解\n"
        "5. 如果内容无业务价值，返回'该文件内容无适合客服使用的知识点'"
    ).format(file_type=file_type)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"文件名：{filename}\n\n内容摘要：\n{content[:4000]}"},
    ]
    try:
        async with _httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{api_base}/text/chatcompletion_v2",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": messages, "max_tokens": 4000, "temperature": 0.4},
            )
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices") or []
                if choices:
                    c = choices[0]
                    return (c.get("text") or (c.get("message") or {}).get("content") or "").strip()
    except Exception as exc:
        logger.warning("upload LLM analyze failed: %s", exc)
    return ""


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Form(""),
    industry: str = Form("general"),
) -> JSONResponse:
    """接收附件（图片/PDF/邮件），识别内容，LLM提炼知识点，追加到知识库。"""
    content = await file.read()
    filename = file.filename or "unknown"
    mime = file.content_type or ""
    size_kb = len(content) // 1024

    if size_kb > 10240:
        return JSONResponse({"error": "文件过大，请控制在10MB以内"}, status_code=400)

    # 保存到 uploads 目录（用于回传32G）
    safe_name = f"{int(time.time())}_{filename}"
    (UPLOAD_DIR / safe_name).write_bytes(content)

    extracted = ""
    file_type = "文档"

    if mime.startswith("image/") or filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        file_type = "图片"
        # 无视觉LLM，返回图片基本信息+引导描述
        extracted = f"已接收图片「{filename}」（{size_kb}KB）。由于当前AI暂不支持图片视觉识别，请您描述图片中的关键内容（如文字、数据、图表含义），我来帮您分析。"
    elif mime == "application/pdf" or filename.lower().endswith(".pdf"):
        file_type = "PDF文档"
        extracted = _extract_pdf_text(content)
        if not extracted:
            extracted = f"已接收PDF「{filename}」（{size_kb}KB），但未能提取到文本内容。如果是扫描件PDF，请描述其中的关键信息。"
    elif mime in ("message/rfc8282",) or filename.lower().endswith((".eml", ".msg")):
        file_type = "邮件"
        email_data = _extract_email_text(content)
        extracted = f"邮件主题：{email_data['subject']}\n发件人：{email_data['from']}\n正文：\n{email_data['body']}"
    elif mime.startswith("text/") or filename.lower().endswith((".txt", ".md", ".csv")):
        file_type = "文本文件"
        extracted = content.decode("utf-8", errors="replace")[:5000]
    else:
        return JSONResponse(
            {"error": f"暂不支持 {mime or filename} 格式，支持：图片/JPG/PNG、PDF、邮件/EML、文本/TXT/MD"},
            status_code=400,
        )

    # LLM 提炼（非图片时）
    analysis = ""
    if file_type != "图片" and extracted and not extracted.startswith("已接收"):
        analysis = await _llm_analyze(extracted, file_type, filename)

    # 追加到知识库
    kb_path = Path(__file__).resolve().parent / "knowledge"
    today = time.strftime("%Y-%m-%d")
    kb_file = kb_path / f"{today}.md"
    section = f"\n\n## 来源：{filename}（{file_type}，{size_kb}KB）\n\n"
    if analysis and "无适合" not in analysis:
        section += analysis + "\n"
        kb_file.write_text(kb_file.read_text(encoding="utf-8") + section if kb_file.exists() else f"# {today} 客服知识库更新\n{section}", encoding="utf-8")
    else:
        section += f"（文件已接收，但未提炼出客服可用知识点。原文前200字：{extracted[:200]}）\n"
        kb_file.write_text(kb_file.read_text(encoding="utf-8") + section if kb_file.exists() else f"# {today} 客服知识库更新\n{section}", encoding="utf-8")

    # 重置 KB 缓存让下次请求加载新内容
    global _kb
    _kb = None

    answer = analysis if analysis and "无适合" not in analysis else extracted
    return JSONResponse({
        "answer": answer,
        "filename": filename,
        "file_type": file_type,
        "size_kb": size_kb,
        "knowledge_updated": bool(analysis and "无适合" not in analysis),
        "session_id": session_id,
    })
