from __future__ import annotations

"""DDW 电子签章适配器插件业务逻辑层。

关键设计：
- :class:`SignatureAdapter` —— 适配器基类（占位/扩展点），未来实现各 provider
  （tencent / dianxiaoyu / esign）接入时继承此基类，实现 create_request / get_status /
  parse_callback 三个方法
- :func:`get_adapter` —— 适配器工厂，根据 provider 名称返回对应实现
- :class:`SignatureRequestService` —— 签署请求 CRUD + 状态机 + 回调 + 统计
- :data:`ALLOWED_CALLBACK_STATUSES` —— 回调可设置的目标状态白名单
  （signed / rejected / expired）
- :data:`_EDITABLE_STATUSES` —— 允许 update 的状态（仅 pending）
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import SignatureRequest
from .schemas import (
    CallbackReq,
    ManualUploadReq,
    SignatureRequestCreateReq,
    SignatureRequestListResp,
    SignatureRequestResp,
    SignatureRequestStatsResp,
    SignatureRequestUpdateReq,
    SignerItem,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ALL_STATUSES: list[str] = ["pending", "signing", "signed", "rejected", "expired"]
ALL_PROVIDERS: list[str] = ["tencent", "dianxiaoyu", "esign", "manual"]

# 第三方回调可设置的目标状态白名单
ALLOWED_CALLBACK_STATUSES: frozenset[str] = frozenset({"signed", "rejected", "expired"})

# 仅 pending 状态允许 update（一旦开始签署就不能再改基本信息）
_EDITABLE_STATUSES: frozenset[str] = frozenset({"pending"})


# ---------------------------------------------------------------------------
# 适配器模式（占位/扩展点）
# ---------------------------------------------------------------------------


class SignatureAdapter:
    """基础适配器（占位，未来实现各 provider 接入）。

    第三方签章服务商接入规范：
    - 子类需要实现 :meth:`create_request` / :meth:`get_status` / :meth:`parse_callback`
    - ``provider`` 属性是唯一标识（如 'tencent'），用于 :func:`get_adapter` 工厂分发
    - 所有方法都是 async，避免阻塞事件循环
    """

    provider: str = ""

    async def create_request(
        self,
        request: SignatureRequest,
        signers: list[dict[str, Any]] | None,
        document_url: Optional[str],
    ) -> str:
        """调用第三方 API 创建签署请求，返回 external_request_id。

        :raises NotImplementedError: 基类未实现，需子类覆盖
        """
        raise NotImplementedError(
            f"SignatureAdapter for provider='{self.provider}' "
            "must implement create_request()"
        )

    async def get_status(self, external_request_id: str) -> dict[str, Any]:
        """查询第三方系统当前状态，返回 {'status': str, 'signed_document_url': Optional[str]}。

        :raises NotImplementedError: 基类未实现，需子类覆盖
        """
        raise NotImplementedError(
            f"SignatureAdapter for provider='{self.provider}' "
            "must implement get_status()"
        )

    async def parse_callback(self, payload: dict[str, Any]) -> dict[str, Any]:
        """解析第三方回调 payload，标准化为 {'status': str, 'signed_document_url': Optional[str], ...}。

        :raises NotImplementedError: 基类未实现，需子类覆盖
        """
        raise NotImplementedError(
            f"SignatureAdapter for provider='{self.provider}' "
            "must implement parse_callback()"
        )


def get_adapter(provider: str) -> SignatureAdapter:
    """适配器工厂：根据 provider 名称返回对应适配器实例。

    本版本不实现任何具体 provider，返回基类占位实例（调用具体方法会抛
    NotImplementedError）。未来接入 tencent / dianxiaoyu / esign 时在此处
    添加具体适配器类的实例化分支。
    """
    # 预留：未来实现时类似：
    # if provider == "tencent":
    #     return TencentSignatureAdapter()
    # if provider == "dianxiaoyu":
    #     return DianxiaoyuSignatureAdapter()
    return SignatureAdapter()


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _to_dict(r: SignatureRequest) -> dict[str, Any]:
    """ORM -> dict（用于响应）。"""
    return {
        "id": r.id,
        "tenant_id": r.tenant_id,
        "contract_id": r.contract_id,
        "provider": r.provider,
        "external_request_id": r.external_request_id,
        "signers": r.signers or [],
        "document_url": r.document_url,
        "signed_document_url": r.signed_document_url,
        "status": r.status,
        "signed_at": r.signed_at,
        "notes": r.notes,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "created_by": r.created_by,
    }


def _signers_to_list(items: list[SignerItem] | None) -> list[dict[str, Any]]:
    """Pydantic SignerItem 列表 -> 原始 dict 列表（用于 JSON 存储）。"""
    if not items:
        return []
    return [
        {
            "name": it.name,
            "phone": it.phone,
            "email": it.email,
            "role": it.role,
            "status": it.status or "pending",
        }
        for it in items
    ]


# ---------------------------------------------------------------------------
# 业务服务
# ---------------------------------------------------------------------------


class SignatureRequestService:
    """签署请求业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- CRUD -----

    async def create(self, data: SignatureRequestCreateReq) -> dict[str, Any]:
        """新建签署请求（不真正调用第三方 API，仅落库，状态默认 pending）。"""
        req = SignatureRequest(
            tenant_id=data.tenant_id,
            contract_id=data.contract_id,
            provider=data.provider,
            external_request_id=data.external_request_id,
            signers=_signers_to_list(data.signers),
            document_url=data.document_url,
            signed_document_url=None,
            status="pending",
            signed_at=None,
            notes=data.notes,
            created_by=data.created_by,
        )
        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        logger.info(
            "signature request created: id=%s provider=%s contract_id=%s",
            req.id, req.provider, req.contract_id,
        )
        return _to_dict(req)

    async def get(self, request_id: int) -> dict[str, Any] | None:
        """获取签署请求详情。"""
        r = await self.db.get(SignatureRequest, request_id)
        if not r:
            return None
        return _to_dict(r)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        contract_id: Optional[int] = None,
        provider: Optional[str] = None,
        status: Optional[str] = None,
    ) -> SignatureRequestListResp:
        """签署请求列表（分页 + 多维筛选）。"""
        conditions = []
        if contract_id is not None:
            conditions.append(SignatureRequest.contract_id == contract_id)
        if provider:
            conditions.append(SignatureRequest.provider == provider)
        if status:
            conditions.append(SignatureRequest.status == status)

        # total
        count_stmt = select(func.count(SignatureRequest.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar_one()

        # items
        offset = (page - 1) * page_size
        list_stmt = (
            select(SignatureRequest)
            .order_by(SignatureRequest.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        if conditions:
            list_stmt = list_stmt.where(and_(*conditions))
        rows = (await self.db.execute(list_stmt)).scalars().all()

        return SignatureRequestListResp(
            total=total,
            page=page,
            page_size=page_size,
            items=[SignatureRequestResp(**_to_dict(r)) for r in rows],
        )

    async def update(
        self, request_id: int, data: SignatureRequestUpdateReq
    ) -> dict[str, Any]:
        """更新签署请求（仅 pending 状态可改）。"""
        r = await self.db.get(SignatureRequest, request_id)
        if not r:
            raise LookupError(f"signature request {request_id} not found")
        if r.status not in _EDITABLE_STATUSES:
            raise ValueError(
                f"当前 status='{r.status}' 不允许修改（仅允许 pending）"
            )

        updates = data.model_dump(exclude_unset=True)
        # 保护字段：id / tenant_id / status / signed_at / signed_document_url
        # 都不能通过 update 改 —— 状态必须走 callback / manual-upload
        for protected in (
            "id",
            "tenant_id",
            "status",
            "signed_at",
            "signed_document_url",
            "created_at",
            "updated_at",
            "created_by",
        ):
            updates.pop(protected, None)
        # signers 需要从 Pydantic 转 dict 列表
        if "signers" in updates and updates["signers"] is not None:
            updates["signers"] = [
                s if isinstance(s, dict) else s.model_dump() for s in updates["signers"]
            ]

        for k, v in updates.items():
            setattr(r, k, v)
        await self.db.commit()
        await self.db.refresh(r)
        logger.info(
            "signature request updated: id=%s fields=%s", r.id, list(updates.keys())
        )
        return _to_dict(r)

    # ----- 状态机迁移 -----

    async def callback(
        self, request_id: int, payload: CallbackReq
    ) -> dict[str, Any]:
        """处理第三方异步回调：更新 status + signed_at + signed_document_url。

        业务规则：
        - 目标 status 必须在 ALLOWED_CALLBACK_STATUSES 白名单内（signed/rejected/expired）
        - status=signed 时记录 signed_at = now（UTC）
        - 可选更新 external_request_id / signed_document_url / notes
        - 已处于终态（signed/rejected/expired）时再回调会被忽略（按幂等处理）
        """
        r = await self.db.get(SignatureRequest, request_id)
        if not r:
            raise LookupError(f"signature request {request_id} not found")

        if payload.status not in ALLOWED_CALLBACK_STATUSES:
            raise ValueError(
                f"callback status='{payload.status}' 不在白名单内 "
                f"（仅允许: {sorted(ALLOWED_CALLBACK_STATUSES)}）"
            )

        # 幂等：已处于该目标状态时直接返回（不更新时间戳）
        if r.status == payload.status:
            logger.info(
                "callback idempotent: id=%s already in status=%s",
                r.id, r.status,
            )
            return _to_dict(r)

        r.status = payload.status
        if payload.status == "signed":
            r.signed_at = datetime.now(timezone.utc)
            if payload.signed_document_url:
                r.signed_document_url = payload.signed_document_url
        if payload.external_request_id:
            r.external_request_id = payload.external_request_id
        if payload.notes:
            r.notes = (
                f"{r.notes}\n[callback] {payload.notes}" if r.notes else f"[callback] {payload.notes}"
            )

        await self.db.commit()
        await self.db.refresh(r)
        logger.info(
            "signature request callback: id=%s -> %s signed_at=%s",
            r.id, r.status, r.signed_at,
        )
        return _to_dict(r)

    async def manual_upload(
        self, request_id: int, payload: ManualUploadReq
    ) -> dict[str, Any]:
        """人工上传签后文件（status -> signed, signed_document_url 必填）。"""
        r = await self.db.get(SignatureRequest, request_id)
        if not r:
            raise LookupError(f"signature request {request_id} not found")

        r.status = "signed"
        r.signed_at = datetime.now(timezone.utc)
        r.signed_document_url = payload.signed_document_url
        if payload.notes:
            r.notes = (
                f"{r.notes}\n[manual-upload] {payload.notes}"
                if r.notes
                else f"[manual-upload] {payload.notes}"
            )

        await self.db.commit()
        await self.db.refresh(r)
        logger.info(
            "signature request manual-upload: id=%s signed_at=%s",
            r.id, r.signed_at,
        )
        return _to_dict(r)

    # ----- 统计 -----

    async def stats(self) -> SignatureRequestStatsResp:
        """签署请求统计概览。"""
        # 按 status
        by_status_rows = (
            await self.db.execute(
                select(SignatureRequest.status, func.count(SignatureRequest.id)).group_by(
                    SignatureRequest.status
                )
            )
        ).all()
        by_status: dict[str, int] = dict(by_status_rows)

        # 按 provider
        by_provider_rows = (
            await self.db.execute(
                select(SignatureRequest.provider, func.count(SignatureRequest.id)).group_by(
                    SignatureRequest.provider
                )
            )
        ).all()
        by_provider: dict[str, int] = dict(by_provider_rows)

        total = sum(by_status.values())
        return SignatureRequestStatsResp(
            total=total,
            pending=by_status.get("pending", 0),
            signing=by_status.get("signing", 0),
            signed=by_status.get("signed", 0),
            rejected=by_status.get("rejected", 0),
            expired=by_status.get("expired", 0),
            by_provider=by_provider,
        )


__all__ = [
    "ALLOWED_CALLBACK_STATUSES",
    "ALL_PROVIDERS",
    "ALL_STATUSES",
    "SignatureAdapter",
    "SignatureRequestService",
    "get_adapter",
]
