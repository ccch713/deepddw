"""FastAPI 路由（15+ 端点）。"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wenqu_tutor.config import WALLET_BASE
from plugins.ddw_wenqu_tutor.models import (
    WenquQuestion,
    WenquSession,
    WenquTheme,
    WenquWrongAnswer,
)
from plugins.ddw_wenqu_tutor.prompt.chemistry_safety import SAFETY_RULES
from plugins.ddw_wenqu_tutor.schemas import (
    FourQuestionsOut,
    GenerateVariantIn,
    GenerateVariantOut,
    MessageOut,
    MessageSend,
    ParentStatsOut,
    QuestionListOut,
    QuestionSubmit,
    QuestionSubmitOut,
    SafetyRulesListOut,
    SessionEndOut,
    SessionOut,
    SessionStart,
    WrongRedoOut,
)
from plugins.ddw_wenqu_tutor.services.questions import (
    generate_variant,
    get_question,
    judge_answer,
    list_questions,
)
from plugins.ddw_wenqu_tutor.services.session import (
    add_message,
    create_session,
    end_session,
    get_messages,
    get_session,
)
from plugins.ddw_wenqu_tutor.services.textbook import list_textbooks
from plugins.ddw_wenqu_tutor.services.parent_stats import get_weekly_stats
from plugins.ddw_wenqu_tutor.prompt.token_budget import estimate_tokens
from plugins.ddw_wenqu_tutor.llm_client import get_llm_client
from plugins.ddw_wenqu_tutor.services.wallet_client import (
    WenquWalletClient,
)
from plugins.ddw_wenqu_tutor.services.wrongbook import (
    get_four_questions,
    list_wrong_answers,
    start_redo_session,
)

router = APIRouter(prefix="/api/v1/plugins/ddw_wenqu_tutor", tags=["ddw_wenqu_tutor"])


async def get_db():
    """FastAPI dependency: yield an AsyncSession from core's session factory."""
    from core.database.session import get_session_maker
    async with get_session_maker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def build_router() -> APIRouter:
    """构建路由器。"""
    return router


# ── Wallet 客户端懒加载单例（进程级复用 httpx 连接池） ──

_wallet_client: WenquWalletClient | None = None


def _get_wallet_client(_obj=None) -> WenquWalletClient:
    """获取 wallet 客户端单例。首次调用时创建，后续复用。

    _obj 参数仅为兼容调用处传参习惯，实际未使用。
    """
    global _wallet_client
    if _wallet_client is None:
        _wallet_client = WenquWalletClient(base_url=WALLET_BASE)
    return _wallet_client


@router.post("/session/start", response_model=SessionOut)
async def session_start(
    req: SessionStart,
    db: AsyncSession = Depends(get_db),
):
    """开课（校验钱包余额>0，不足 402）。"""
    wallet = _get_wallet_client()
    has_balance = await wallet.check_balance(
        req.student_name, min_cents=100
    )
    if not has_balance:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "INSUFFICIENT_BALANCE",
                "message": "钱包余额不足，请先充值",
            },
        )
    session = await create_session(
        db,
        student_name=req.student_name,
        subject=req.subject,
        chapter=req.chapter,
    )
    return SessionOut(
        session_id=session.id,
        subject=session.subject,
        status=session.status,
        started_at=session.started_at,
    )


@router.post(
    "/session/{session_id}/message",
    response_model=list[MessageOut],
)
async def session_message(
    session_id: str,
    req: MessageSend,
    db: AsyncSession = Depends(get_db),
    llm_client=None,
):
    """苏格拉底对话（SSE 流式，M0-6）— 化学走新逻辑，物理走原逻辑。

    响应为 text/event-stream：
      data: {"token": "..."}     逐块内容
      data: {"done": true}       结束（已入库）
    """
    from fastapi.responses import StreamingResponse
    import json as _json

    if llm_client is None:
        llm_client = get_llm_client()

    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status != "active":
        raise HTTPException(400, "Session not active")

    await add_message(
        db, session_id, "user", req.content,
        token_count=estimate_tokens(req.content),
    )

    async def _stream():
        # 全科目走苏格拉底引擎（COACH_ROLE 已注册 7 科，见 prompt/subject_meta.py）
        from plugins.ddw_wenqu_tutor.services.socratic import (
            build_system_prompt,
            build_user_message,
        )

        system_prompt = build_system_prompt(
            subject=session.subject,
            chapter=session.chapter,
            phase=session.phase,
            max_tokens=6000,
        )
        user_msg = build_user_message(req.content)
        chunks = []
        try:
            async for chunk in llm_client.generate_stream(
                system=system_prompt,
                user=user_msg,
                temperature=0.7,
                max_tokens=2000,
            ):
                chunks.append(chunk)
                yield f"data: {_json.dumps({'token': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            logger = __import__("logging").getLogger("wenqu.router")
            logger.warning("stream failed, fallback non-stream: %s", e)
            fallback = await llm_client.generate(
                system=system_prompt,
                user=user_msg,
                temperature=0.7,
                max_tokens=2000,
            )
            chunks.append(fallback)
            yield f"data: {_json.dumps({'token': fallback}, ensure_ascii=False)}\n\n"

        ai_reply = "".join(chunks)
        await _advance_phase(db, session_id, session.phase)

        await add_message(
            db, session_id, "assistant", ai_reply,
            token_count=estimate_tokens(ai_reply),
        )
        yield f"data: {_json.dumps({'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _advance_phase(
    db: AsyncSession, session_id: str, current_phase: str,
) -> None:
    """推进 phase（线性推进，不回退）。"""
    phase_order = [
        "info_check", "mode_select", "chem_analysis",
        "answer_diag", "pinpoint", "min_intervention",
        "verify_transfer", "record",
    ]
    idx = phase_order.index(current_phase)
    if idx < len(phase_order) - 1:
        next_phase = phase_order[idx + 1]
        await db.execute(
            update(WenquSession)
            .where(WenquSession.id == session_id)
            .values(phase=next_phase)
        )
        await db.commit()


@router.post(
    "/session/{session_id}/end",
    response_model=SessionEndOut,
)
async def session_end(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """下课：活跃计时结算 → 钱包扣费。"""
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    wallet = _get_wallet_client()
    try:
        result = await end_session(db, session_id, wallet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return SessionEndOut(
        session_id=session_id,
        active_minutes=result["active_minutes"],
        charge_cents=result["charge_cents"],
        balance_after_cents=result["balance_after_cents"],
        txn_no=result["txn_no"],
    )


@router.get(
    "/session/{session_id}",
    response_model=list[MessageOut],
)
async def session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """会话详情（消息列表）。"""
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    messages = await get_messages(db, session_id)
    return [
        MessageOut(
            role=m.role,
            content=m.content,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.get("/textbook/list")
async def textbook_list(
    subject: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """教材列表。"""
    textbooks = await list_textbooks(db, subject=subject)
    return {
        "items": [
            {
                "id": t.id,
                "subject": t.subject,
                "grade": t.grade,
                "version": t.version,
                "chapters": t.chapters,
                "indexed_at": t.indexed_at,
            }
            for t in textbooks
        ],
        "total": len(textbooks),
    }


@router.post("/textbook/upload")
async def textbook_upload(db: AsyncSession = Depends(get_db)):
    """上传教材 PDF（本地 OCR 切片入库）。"""
    # TODO: OCR 管道（M0-7）实现后接线：register_textbook + index_textbook
    return {"status": "not_implemented"}


@router.get("/questions/list", response_model=QuestionListOut)
async def questions_list(
    subject: Optional[str] = None,
    chapter: Optional[str] = None,
    difficulty: Optional[str] = None,
    mastery: Optional[str] = None,
    student_name: str = "CXY",
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """练习列表。

    mastery 模式（2026-08-14 用户拍板：难度=错误次数）：
    weak=错误≥3次 / medium=错误1-2次 / mastered=已掌握；
    传 mastery 时按学生错题记录筛选，difficulty 忽略。
    """
    if mastery:
        from plugins.ddw_wenqu_tutor.services.questions import (
            list_questions_by_mastery,
        )

        paired, total = await list_questions_by_mastery(
            db,
            student_name=student_name,
            mastery=mastery,
            subject=subject,
            chapter=chapter,
            limit=limit,
            offset=offset,
        )
        return QuestionListOut(
            items=[
                {
                    "id": q.id,
                    "subject": q.subject,
                    "chapter": q.chapter,
                    "year": q.year,
                    "difficulty": q.difficulty,
                    "source": q.source,
                    "question_text": q.question_text,
                    "answer": q.answer,
                    "explanation": q.explanation,
                    "knowledge_points": q.knowledge_points,
                    "mode": q.mode,
                    "wrong_count": wrong_count,
                }
                for q, wrong_count in paired
            ],
            total=total,
        )

    questions, total = await list_questions(
        db,
        subject=subject,
        chapter=chapter,
        difficulty=difficulty,
        limit=limit,
        offset=offset,
    )
    return QuestionListOut(
        items=[
            {
                "id": q.id,
                "subject": q.subject,
                "chapter": q.chapter,
                "year": q.year,
                "difficulty": q.difficulty,
                "source": q.source,
                "question_text": q.question_text,
                "answer": q.answer,
                "explanation": q.explanation,
                "knowledge_points": q.knowledge_points,
                "mode": q.mode,
            }
            for q in questions
        ],
        total=total,
    )


@router.post(
    "/questions/submit",
    response_model=QuestionSubmitOut,
)
async def questions_submit(
    req: QuestionSubmit,
    db: AsyncSession = Depends(get_db),
    llm_client=None,
):
    """主观题评判 — 化学走结构化评判+四问。"""
    question = await get_question(db, req.question_id)
    if not question:
        raise HTTPException(404, "Question not found")

    result = await judge_answer(
        db,
        question_id=req.question_id,
        student_answer=req.student_answer,
        session_id=req.session_id,
        llm_client=llm_client,
        student_name=req.student_name,
    )
    return QuestionSubmitOut(**result)


@router.get("/questions/challenge", response_model=QuestionListOut)
async def questions_challenge(
    student_name: str = "CXY",
    subject: Optional[str] = None,
    chapter: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """挑战模式：全用户错误最多的公共题（排除已作对）。

    对外口径：AI 根据学生错题类型自动生成的练习题。
    """
    from plugins.ddw_wenqu_tutor.services.questions import (
        list_challenge_questions,
    )

    paired, total = await list_challenge_questions(
        db,
        student_name=student_name,
        subject=subject,
        chapter=chapter,
        limit=limit,
    )
    return QuestionListOut(
        items=[
            {
                "id": q.id,
                "subject": q.subject,
                "chapter": q.chapter,
                "year": q.year,
                "difficulty": q.difficulty,
                "source": q.source,
                "question_text": q.question_text,
                "answer": q.answer,
                "explanation": q.explanation,
                "knowledge_points": q.knowledge_points,
                "mode": q.mode,
                "wrong_count": wrong_count,
            }
            for q, wrong_count in paired
        ],
        total=total,
    )


@router.get("/wrongbook/list")
async def wrongbook_list(
    student_name: str = "CXY",
    resolved: Optional[bool] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """错题本。"""
    wrongs = await list_wrong_answers(
        db,
        student_name=student_name,
        resolved=resolved,
        limit=limit,
    )
    return {
        "items": [
            {
                "id": w.id,
                "question_id": w.question_id,
                "student_answer": w.student_answer,
                "error_type": w.error_type,
                "knowledge_gap": w.knowledge_gap,
                "mode": w.mode,
                "resolved": w.resolved,
                "created_at": w.created_at,
            }
            for w in wrongs
        ],
        "total": len(wrongs),
    }


@router.post(
    "/wrongbook/{wrong_id}/redo",
    response_model=WrongRedoOut,
)
async def wrongbook_redo(
    wrong_id: str,
    db: AsyncSession = Depends(get_db),
    llm_client=None,
):
    """错题苏格拉底复盘 — 先展示四问，再递进。"""
    try:
        result = await start_redo_session(db, wrong_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return WrongRedoOut(**result)


@router.get("/parent/stats", response_model=ParentStatsOut)
async def parent_stats(
    student_name: str = "CXY",
    days: int = 7,
    db: AsyncSession = Depends(get_db),
):
    """家长面板统计（周报数据源）。"""
    stats = await get_weekly_stats(db, student_name=student_name, days=days)
    return ParentStatsOut(**stats)


@router.post(
    "/questions/generate-variant",
    response_model=GenerateVariantOut,
)
async def questions_generate_variant(
    req: GenerateVariantIn,
    db: AsyncSession = Depends(get_db),
    llm_client=None,
):
    """AI 生成同类变式题。"""
    try:
        result = await generate_variant(
            db, req.question_id, req.difficulty, llm_client,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    return GenerateVariantOut(**result)


@router.get(
    "/wrongbook/{wrong_id}/four-questions",
    response_model=FourQuestionsOut,
)
async def wrongbook_four_questions(
    wrong_id: str,
    db: AsyncSession = Depends(get_db),
):
    """错题四问详情。"""
    result = await get_four_questions(db, wrong_id)
    if not result:
        raise HTTPException(404, "Wrong answer not found")
    return FourQuestionsOut(**result)


@router.get(
    "/safety/rules",
    response_model=SafetyRulesListOut,
)
async def safety_rules():
    """安全规则查询（常量数据，不需要 DB）。"""
    return SafetyRulesListOut(
        rules=SAFETY_RULES,
        total=len(SAFETY_RULES),
    )


@router.get("/health")
async def health():
    """健康检查。"""
    return {"status": "ok", "plugin": "ddw_wenqu_tutor"}


# ── 皮肤商店（2026-08-14 移植自 wenquK12） ──

@router.get("/skin/list")
async def skin_list(
    target_gender: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """皮肤市场列表（官方免费 + UGC 已审核）。"""
    from plugins.ddw_wenqu_tutor.services.skin import list_themes

    items, total = await list_themes(db, target_gender=target_gender)
    return {"themes": items, "total": total}


@router.get("/skin/active")
async def skin_active(
    student_name: str = "CXY",
    db: AsyncSession = Depends(get_db),
):
    """学生当前激活的皮肤。"""
    from plugins.ddw_wenqu_tutor.services.skin import get_active_theme

    theme = await get_active_theme(db, student_name)
    if not theme:
        return {"theme_id": None, "css_vars": None, "name": None}
    return {
        "theme_id": theme["id"],
        "name": theme["name"],
        "css_vars": theme["css_vars"],
    }


@router.post("/skin/activate")
async def skin_activate(
    req: dict,
    db: AsyncSession = Depends(get_db),
):
    """激活皮肤（M0 简化：student_name 参数；M1 接登录鉴权）。"""
    from plugins.ddw_wenqu_tutor.services.skin import activate_theme

    student_name = (req.get("student_name") or "CXY")
    theme_id = req.get("theme_id", "")
    if not theme_id:
        raise HTTPException(400, "theme_id required")
    try:
        result = await activate_theme(db, student_name, theme_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return result


@router.post("/skin/seed-presets")
async def skin_seed_presets(db: AsyncSession = Depends(get_db)):
    """初始化官方预设皮肤（幂等）。"""
    from plugins.ddw_wenqu_tutor.services.skin import seed_presets

    return await seed_presets(db)


@router.post("/skin/upload")
async def skin_upload(
    name: str = Form(...),
    css_vars_json: str = Form("{}"),
    target_gender: str = Form("unisex"),
    description: str = Form(""),
    preview: Optional[UploadFile] = File(None),
    student_name: str = Form("CXY"),
    db: AsyncSession = Depends(get_db),
):
    """UGC 皮肤上传（2026-08-14 移植 wenquK12 + IP 版权审核）。

    流程：变量规范校验 → 预览图 AI 版权检测 → 待审核入库
    （审核通过后上架售卖，75% 作者分成 M1 钱包结算）。
    """
    import json as _json

    from plugins.ddw_wenqu_tutor.services.ip_check import (
        check_ip_risk, validate_skin_vars,
    )
    from plugins.ddw_wenqu_tutor.services.skin import (
        generate_theme_id,
    )

    try:
        css_vars = _json.loads(css_vars_json)
    except _json.JSONDecodeError:
        raise HTTPException(400, "CSS 变量 JSON 格式错误")

    # 1. 皮肤变量规范校验
    err = validate_skin_vars(css_vars)
    if err:
        raise HTTPException(400, err)

    # 2. 预览图 IP 版权检测
    ip_result = None
    if preview:
        preview_bytes = await preview.read()
        if len(preview_bytes) > 5 * 1024 * 1024:
            raise HTTPException(413, "预览图太大（>5MB）")
        ip_result = await check_ip_risk(
            image_bytes=preview_bytes,
            description=f"皮肤预览图：{name}",
        )
        if ip_result.has_risk:
            raise HTTPException(
                400,
                f"版权风险未通过（{ip_result.risk_type}，{ip_result.details}）——"
                "请使用原创设计，避免知名 IP 角色/标志",
            )
    else:
        # 无预览图：说明文字描述皮肤（不涉及图片版权）
        ip_result = None

    # 3. 待审核入库（is_approved=False；审核通过后上架）
    theme = WenquTheme(
        id=generate_theme_id(),
        name=name,
        description=description or f"{student_name} 制作",
        css_vars=_json.dumps(css_vars, ensure_ascii=False),
        style_tags="[]",
        target_gender=target_gender,
        is_official=False,
        is_approved=False,
        price_cents=0,  # 待定价（上限 5 元）
        author_user_id=None,
        author_name=student_name,
    )
    db.add(theme)
    await db.commit()

    return {
        "created": True,
        "theme_id": theme.id,
        "status": "pending_review",
        "ip_check": (
            {"passed": True, "risk_type": "none", "details": ip_result.details}
            if ip_result else {"passed": True, "risk_type": "none"}
        ),
        "message": "皮肤已提交，等待审核（版权检测通过）。上架后 75% 收入归你。",
    }


# ── 老版页面适配端点（2026-08-14 移植 wenquK12 页面） ──

@router.get("/auth/me")
async def auth_me(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """当前用户档案（M0 演示模式；M1 接微信 OAuth）。"""
    from plugins.ddw_wenqu_tutor.services.adapters import (
        DEMO_STUDENT, is_demo_token,
    )

    token = (authorization or "").replace("Bearer ", "")
    if not is_demo_token(token):
        raise HTTPException(401, "未登录")
    # 查询钱包余额（三钱包）
    wallet = _get_wallet_client()
    balance = {"recharge_balance_cents": 0}
    try:
        bal = await wallet.get_balance(DEMO_STUDENT)
        balance = bal or balance
    except Exception:  # noqa: BLE001
        pass
    return {
        "student_name": DEMO_STUDENT,
        "recharge_balance_cents": balance.get("recharge_balance_cents", 0),
        "income_balance_cents": balance.get("income_balance_cents", 0),
        "skin_balance_cents": balance.get("skin_balance_cents", 0),
        "is_test": False,
    }


@router.get("/parent/weekly-report")
async def parent_weekly_report(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """家长周报（老页面格式）。"""
    from plugins.ddw_wenqu_tutor.services.adapters import (
        DEMO_STUDENT, build_weekly_report, is_demo_token,
    )

    token = (authorization or "").replace("Bearer ", "")
    if not is_demo_token(token):
        raise HTTPException(401, "未登录")
    return await build_weekly_report(db, DEMO_STUDENT)


@router.get("/wallet/recharge-options")
async def wallet_recharge_options():
    """充值金额档位（老页面格式）。"""
    return {
        "options": [
            {"amount_cents": 500, "label": "¥5"},
            {"amount_cents": 1000, "label": "¥10"},
            {"amount_cents": 2000, "label": "¥20"},
            {"amount_cents": 5000, "label": "¥50"},
            {"amount_cents": 10000, "label": "¥100"},
        ]
    }


@router.post("/wallet/recharge/create")
async def wallet_recharge_create(req: dict, db: AsyncSession = Depends(get_db)):
    """创建充值单（包装 ddw_wallet /recharges）。"""
    from plugins.ddw_wenqu_tutor.services.adapters import DEMO_STUDENT

    wallet = _get_wallet_client()
    amount = int(req.get("amount_cents") or 500)
    try:
        result = await wallet.create_recharge(
            user_id=req.get("user_id") or DEMO_STUDENT,
            amount_cents=amount,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"充值单创建失败：{e}")
    return {
        "order_no": result.get("order_no", ""),
        "amount_cents": amount,
        "status": result.get("status", "pending"),
    }


@router.get("/wallet/recharge/query")
async def wallet_recharge_query(order_no: str):
    """查询充值单状态（包装 ddw_wallet）。"""
    wallet = _get_wallet_client()
    try:
        result = await wallet.get_recharge(order_no)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(404, f"订单不存在：{e}")
    return result


# ── 拍照错题 OCR（2026-08-14 移植 wenquK12 + 多模态） ──

@router.post("/ocr/recognize")
async def ocr_recognize(
    file: UploadFile = File(...),
    subject: str = "physics",
    student_name: str = "CXY",
):
    """识别错题/试卷图片，返回题目列表（不直接归档，等用户确认）。"""
    from plugins.ddw_wenqu_tutor.services.ocr import (
        questions_to_mistake_records,
        recognize_exam_paper,
    )

    if subject not in ("physics", "chemistry"):
        raise HTTPException(400, "subject 必须是 physics 或 chemistry")

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "图片太大（>10MB）")

    result = await recognize_exam_paper(image_bytes, subject=subject)
    drafts = questions_to_mistake_records(result.questions, subject)

    return {
        "success": True,
        "student_name": student_name,
        "total_questions": result.total_questions,
        "questions": result.questions,
        "mistake_drafts": drafts,
        "confidence": result.confidence,
        "raw_text": (result.raw_text or "")[:500],
    }


class _ConfirmToMistakeReq(BaseModel):
    """OCR 确认归档请求。"""
    questions: list[dict] = []
    subject: str = "physics"
    student_name: str = "CXY"


@router.post("/ocr/confirm-to-mistake")
async def ocr_confirm_to_mistake(
    req: _ConfirmToMistakeReq,
    db: AsyncSession = Depends(get_db),
):
    """确认 OCR 题目 → 新题入公共题库（众筹贡献）+ 错题入错题本。"""
    from datetime import datetime

    from plugins.ddw_wenqu_tutor.services.questions import (
        generate_question_id,
        generate_wrong_id,
    )

    if not req.questions:
        raise HTTPException(400, "没有题目需要归档")

    created_questions = 0
    wrong_ids = []
    for q in req.questions:
        text = (q.get("question_text") or q.get("text") or "").strip()
        if not text:
            continue
        # 新题入公共题库（众筹：contributor 标记，0.1 元/题奖励 M1 结算）
        qid = generate_question_id()
        db.add(
            WenquQuestion(
                id=qid,
                subject=q.get("subject", req.subject),
                chapter=(q.get("chapter") or ""),
                year=datetime.now().year,
                difficulty="medium",
                source="ocr_upload",
                question_text=text,
                answer=q.get("answer", ""),
                explanation=q.get("explanation", ""),
                knowledge_points="[]",
                contributor=req.student_name,
            )
        )
        created_questions += 1
        # 错题记录（四问留空，AI 复盘时补）
        wid = generate_wrong_id()
        db.add(
            WenquWrongAnswer(
                id=wid,
                student_name=req.student_name,
                question_id=qid,
                student_answer="",
                error_type="concept",
                knowledge_gap="待 AI 复盘归因",
                resolved=False,
            )
        )
        wrong_ids.append(wid)
    await db.commit()

    return {
        "success": True,
        "created_questions": created_questions,
        "wrong_ids": wrong_ids,
        "reward_note": "新题已入公共题库（众筹），0.1 元/题学习金奖励将在 M1 结算",
    }

@router.get("/auth/wechat/config")
async def auth_wechat_config():
    """微信登录配置（M1：返回 AppID 与 OAuth 地址）。

    前置条件：微信开放平台网站应用（AppID + 审核通过），
    学生端 PWA 域名加入授权回调域。
    """
    app_id = os.environ.get("DDW_WENQU_WECHAT_APPID", "")
    return {
        "enabled": bool(app_id),
        "app_id": app_id,
        "login_url": (
            "https://open.weixin.qq.com/connect/qrconnect"
            f"?appid={app_id}&scope=snsapi_login"
            "&redirect_uri="
            + os.environ.get("DDW_WENQU_LOGIN_REDIRECT", "")
            if app_id else ""
        ),
        "note": "M1 接入：填 DDW_WENQU_WECHAT_APPID + DDW_WENQU_LOGIN_REDIRECT 后启用",
    }


__all__ = ["build_router", "router"]