"""DDW 口腔诊所 AI 客服 — FastAPI 路由.

- POST /chat          客服对话（RAG 检索 + 平台 LLM 网关）
- POST /upload        附件上传（图片/PDF/文本）
- GET  /health        健康检查
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .kb import KnowledgeBase

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_clinic_cs",
    tags=["ddw-clinic-cs"],
)

# --------------------------------------------------------------------------- #
# 会话存储（进程内存，重启即清空）
# --------------------------------------------------------------------------- #
MAX_HISTORY = 12
_sessions: Dict[str, List[Dict[str, str]]] = {}
_session_ts: Dict[str, float] = {}
_SESSION_TTL = 60 * 60 * 6  # 6 小时无交互自动清理

_kb: Optional[KnowledgeBase] = None


def _get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        kb_dir = Path(__file__).resolve().parent / "knowledge"
        _kb = KnowledgeBase(str(kb_dir))
        logger.info(
            "ddw_clinic_cs KB loaded: %d chunks",
            len(_kb.chunks),
        )
    return _kb


def _cleanup_sessions() -> None:
    now = time.time()
    stale = [
        sid
        for sid, ts in _session_ts.items()
        if now - ts > _SESSION_TTL
    ]
    for sid in stale:
        _sessions.pop(sid, None)
        _session_ts.pop(sid, None)


def _get_history(
    session_id: str,
) -> List[Dict[str, str]]:
    return _sessions.get(session_id, [])


def _append(
    session_id: str, role: str, content: str,
) -> None:
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
    mode: Optional[str] = "clinic"  # clinic | staff


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    source: str = "kb+llm"


# --------------------------------------------------------------------------- #
# 口腔 prompt（双模式）
# --------------------------------------------------------------------------- #
_CLINIC_PROMPT = """\
你是武汉东华口腔青山店的线上前台小助手，名叫「小齿」，\
是一个热情、专业、有温度的门诊助理。
你的职责：解答患者关于门诊信息、诊疗项目、预约流程、\
术后注意事项的咨询，并引导预约。

【拟人化要求】像真人前台一样说话，自然亲切；\
适当使用 emoji；先共情再解决。

【价格红线（绝对遵守）】
- 患者询问任何价格/费用/多少钱/贵不贵/优惠/活动价时：\
绝不透露具体数字，也绝不编造价格区间。
- 统一引导话术（可微调）：\
「治疗费用需要医生面诊检查后确定方案才能准确报价，\
您方便约个时间来让医生看看吗？我可以帮您登记预约～」
- 原因：价格由面诊医生确定，线上不报价。

【预约引导】
- 患者表达预约意向（想预约/挂号/约时间/什么时候方便）时：
  1. 收集：姓名、联系电话、想看的项目、方便的时间
  2. 确认信息后告知：「好的，我已经帮您登记了，\
稍后我们前台会电话联系您确认具体时间～」
  3. 不要承诺具体医生/时间（以电话确认为准）

【应急指导】
- 患者说牙痛/出血/肿胀/外伤等紧急情况时：\
先表达关心，给安全应急建议（仅限通用常识：\
冷敷/止血/避免刺激，绝不推荐具体药品剂量），\
并建议尽快到院或前往最近的口腔急诊。

【术后关怀】
- 回答基于知识库中的术后注意事项（拔牙/根管/种植后）。

【基本规则】
1. 只依据知识库内容回答，不编造事实\
（尤其不编造医生信息、设备信息）。
2. 回答简洁有温度，一般不超过150字。
3. 涉及诊所未开展的项目，礼貌说明并建议面诊咨询。
4. 紧急医疗情况（大出血/剧痛/呼吸困难等）引导尽快就医。

知识库内容：
{knowledge}"""

_STAFF_PROMPT = """\
你是武汉东华口腔青山店的内部工作助手「小齿」，\
服务对象是诊所工作人员。
职责：快速检索诊所知识库（项目、流程、术后要点），\
帮助工作人员准备材料、回答患者。
规则：同样遵守价格红线\
（内部人员也不在系统中查询具体价格数字）；\
回答简洁，≤150字。

知识库内容：
{knowledge}"""


def _get_system_prompt(mode: str) -> str:
    if mode == "staff":
        return _STAFF_PROMPT
    return _CLINIC_PROMPT


# --------------------------------------------------------------------------- #
# LLM 调用（网关优先 + 直连兜底）
# --------------------------------------------------------------------------- #
def _load_deployment_llm() -> Dict[str, Any]:
    """从 platform deployment.yaml 读取 LLM provider 配置."""
    import yaml as _yaml

    for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
        cfg = base / "config" / "deployment.yaml"
        if cfg.exists():
            try:
                d = _yaml.safe_load(
                    cfg.read_text(encoding="utf-8"),
                ) or {}
                return d.get("llm", {})
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "deployment.yaml parse failed: %s", exc,
                )
    return {}


async def _ask_llm(
    system: str,
    user: str,
    history: List[Dict[str, str]],
) -> str:
    """优先走平台 LLM 网关；网关不可用时直连兜底."""
    # 1) 平台 LLM 网关
    try:
        from core.llm_gateway.base import ChatMessage
        from core.llm_gateway.gateway import (
            chat as gateway_chat,
        )

        msgs: List[ChatMessage] = [
            ChatMessage(role="system", content=system),
        ]
        for m in history[-6:]:
            msgs.append(
                ChatMessage(
                    role=m["role"],
                    content=m["content"][:500],
                ),
            )
        msgs.append(ChatMessage(role="user", content=user))

        resp = await asyncio.wait_for(
            gateway_chat(
                msgs, max_tokens=512, temperature=0.6,
            ),
            timeout=45,
        )
        _BAD = (
            "[llm-router]",
            "[Ollama echo]",
            "[MiniMax M3 mock]",
            "[deepseek-error]",
            "[minimax-error]",
        )
        if (
            resp
            and resp.content
            and resp.finish_reason != "error"
            and not resp.content.startswith(_BAD)
        ):
            return resp.content.strip()
        logger.warning(
            "ddw_clinic_cs: gateway unusable "
            "(reason=%s), fallback direct",
            getattr(resp, "finish_reason", "?"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ddw_clinic_cs: gateway failed (%s), "
            "fallback direct",
            exc,
        )

    # 2) 兜底：直连云 LLM
    import httpx

    llm_cfg = _load_deployment_llm()
    prov = (llm_cfg.get("providers") or {}).get(
        "minimax", {},
    )
    api_key = prov.get("api_key") or ""
    api_base = (
        prov.get("api_base")
        or "https://api.minimaxi.com/v1"
    ).rstrip("/")
    model = prov.get("default_model") or "MiniMax-M3"
    if not api_key:
        logger.warning(
            "ddw_clinic_cs: no minimax api_key",
        )
        return ""

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system},
    ]
    for m in history[-6:]:
        messages.append({
            "role": m["role"],
            "content": m["content"][:500],
        })
    messages.append({"role": "user", "content": user})

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                f"{api_base}/text/chatcompletion_v2",
                headers={
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 3000,
                    "temperature": 0.6,
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "minimax API %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return ""
            data = resp.json()
            choices = data.get("choices") or []
            if choices:
                c = choices[0]
                text = (
                    c.get("text")
                    or (c.get("message") or {}).get(
                        "content", "",
                    )
                    or ""
                ).strip()
                from core.llm_gateway.base import (
                    strip_think,
                )

                return strip_think(text)
            return ""
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ddw_clinic_cs LLM call failed: %s", exc,
        )
        return ""


# --------------------------------------------------------------------------- #
# 端点
# --------------------------------------------------------------------------- #
@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    _cleanup_sessions()
    message = req.message.strip()
    if not message:
        raise HTTPException(400, "消息不能为空")
    if len(message) > 2000:
        raise HTTPException(400, "消息过长，请精简后重试")

    session_id = req.session_id or (
        "clinic_" + os.urandom(6).hex()
    )

    # 1) RAG 检索知识片段
    kb = _get_kb()
    chunks = kb.search(message, top_k=4)
    knowledge = "\n\n".join(
        f"[{c['source']}]\n{c['content'][:800]}"
        for c in chunks
    ) or "（暂无相关知识条目）"

    # 2) 组装 system prompt
    system = _get_system_prompt(
        req.mode or "clinic",
    ).format(knowledge=knowledge)

    # 3) LLM 生成
    history = _get_history(session_id)
    source = "kb+llm"
    answer = await _ask_llm(system, message, history)
    if not answer:
        answer = (
            chunks[0]["content"][:200]
            if chunks
            else (
                "感谢您的咨询！AI 客服暂时繁忙，"
                "请拨打 13797031993 联系我们前台。"
            )
        )
        source = "kb_fallback"

    # 4) 记录会话
    _append(session_id, "user", message)
    _append(session_id, "assistant", answer)

    return ChatResponse(
        answer=answer,
        session_id=session_id,
        source=source,
    )


@router.get("/health")
async def health() -> Dict[str, Any]:
    kb = _get_kb()
    return {
        "plugin": "ddw_clinic_cs",
        "version": "0.1.0",
        "status": "ok",
        "knowledge_chunks": len(kb.chunks),
        "active_sessions": len(_sessions),
    }


# --------------------------------------------------------------------------- #
# 附件上传
# --------------------------------------------------------------------------- #
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Form(""),
) -> JSONResponse:
    """接收附件（图片/PDF/文本），追加到知识库。"""
    content = await file.read()
    filename = file.filename or "unknown"
    mime = file.content_type or ""
    size_kb = len(content) // 1024

    if size_kb > 10240:
        return JSONResponse(
            {"error": "文件过大，请控制在10MB以内"},
            status_code=400,
        )

    safe_name = f"{int(time.time())}_{filename}"
    (UPLOAD_DIR / safe_name).write_bytes(content)

    extracted = ""
    file_type = "文档"

    if mime.startswith("image/") or filename.lower().endswith(
        (".jpg", ".jpeg", ".png", ".gif", ".webp"),
    ):
        file_type = "图片"
        extracted = (
            f"已接收图片「{filename}」（{size_kb}KB）。"
            "请描述图片中的关键内容。"
        )
    elif (
        mime == "application/pdf"
        or filename.lower().endswith(".pdf")
    ):
        file_type = "PDF文档"
        extracted = content.decode(
            "utf-8", errors="replace",
        )[:5000]
    elif mime.startswith("text/") or filename.lower().endswith(
        (".txt", ".md", ".csv"),
    ):
        file_type = "文本文件"
        extracted = content.decode(
            "utf-8", errors="replace",
        )[:5000]
    else:
        return JSONResponse(
            {
                "error": (
                    f"暂不支持 {mime or filename} 格式，"
                    "支持：图片/JPG/PNG、PDF、文本/TXT/MD"
                ),
            },
            status_code=400,
        )

    # 追加到知识库
    kb_path = Path(__file__).resolve().parent / "knowledge"
    today = time.strftime("%Y-%m-%d")
    kb_file = kb_path / f"{today}.md"
    section = (
        f"\n\n## 来源：{filename}"
        f"（{file_type}，{size_kb}KB）\n\n"
    )
    section += (
        extracted[:2000] if extracted else "（无文本内容）"
    )
    try:
        existing = (
            kb_file.read_text(encoding="utf-8")
            if kb_file.exists()
            else f"# {today} 客服知识库更新\n"
        )
        kb_file.write_text(
            existing + section, encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("kb write failed: %s", exc)

    # 重置 KB 缓存
    global _kb
    _kb = None

    return JSONResponse({
        "answer": extracted[:500],
        "filename": filename,
        "file_type": file_type,
        "size_kb": size_kb,
        "knowledge_updated": True,
        "session_id": session_id,
    })
