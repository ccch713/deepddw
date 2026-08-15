"""DDW 连接器元数据发现框架 API 路由。

5 个端点：
  注册数据源：POST /datasources
  触发扫描：  POST /datasources/{id}/scan
  草稿列表：  GET /datasources/{id}/drafts
  确认草稿：  POST /drafts/{id}/confirm
  查询网关：  POST /query
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .models import (
    DatasourceCreateReq,
    DatasourceResp,
    DictionaryDraftResp,
    DraftConfirmReq,
    MetadataReport,
    QueryReq,
    QueryResult,
)

logger = logging.getLogger(__name__)

# 内存数据源注册表（V0.1，生产应持久化）
_datasources: dict[int, dict] = {}
_ds_counter = 0


def _next_ds_id() -> int:
    global _ds_counter
    _ds_counter += 1
    return _ds_counter


def build_router() -> APIRouter:
    """构造连接器元数据发现路由。"""
    router = APIRouter(
        prefix="/api/v1/plugins/ddw-connector",
        tags=["ddw-connector"],
    )

    # -----------------------------------------------------------------------
    # 注册数据源
    # -----------------------------------------------------------------------
    @router.post("/datasources", response_model=DatasourceResp, status_code=201)
    async def create_datasource(data: DatasourceCreateReq) -> DatasourceResp:
        """注册数据源（凭据密文存储：conn_info 经 Fernet 加密后保存）。"""
        from .security import encrypt_conn_info

        try:
            conn_info_enc = encrypt_conn_info(data.conn_info)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        ds_id = _next_ds_id()
        _datasources[ds_id] = {
            "id": ds_id,
            "name": data.name,
            "ds_type": data.ds_type,
            "conn_info_enc": conn_info_enc,
            "description": data.description,
        }
        return DatasourceResp(
            id=ds_id,
            name=data.name,
            ds_type=data.ds_type,
            description=data.description,
        )

    # -----------------------------------------------------------------------
    # 触发扫描
    # -----------------------------------------------------------------------
    @router.post("/datasources/{ds_id}/scan", response_model=MetadataReport)
    async def scan_datasource(ds_id: int) -> MetadataReport:
        """触发元数据扫描。"""
        ds = _datasources.get(ds_id)
        if not ds:
            raise HTTPException(status_code=404, detail=f"datasource {ds_id} not found")

        from .security import decrypt_conn_info
        from .services.metadata_scanner import scan_datasource

        conn_info = decrypt_conn_info(ds["conn_info_enc"])
        report = scan_datasource(conn_info, ds["ds_type"], ds_id)

        # 自动生成草稿
        from .services.dictionary_store import DictionaryStore

        store = DictionaryStore()
        store.create_draft(report)

        return report

    # -----------------------------------------------------------------------
    # 草稿列表
    # -----------------------------------------------------------------------
    @router.get("/datasources/{ds_id}/drafts", response_model=list[DictionaryDraftResp])
    async def list_drafts(ds_id: int) -> list[DictionaryDraftResp]:
        """查询数据源的字典草稿列表。"""
        if ds_id not in _datasources:
            raise HTTPException(status_code=404, detail=f"datasource {ds_id} not found")

        from .services.dictionary_store import DictionaryStore

        store = DictionaryStore()
        return store.list_drafts(ds_id)

    # -----------------------------------------------------------------------
    # 确认草稿
    # -----------------------------------------------------------------------
    @router.post("/drafts/{dict_id}/confirm", response_model=DictionaryDraftResp)
    async def confirm_draft(dict_id: int, data: DraftConfirmReq) -> DictionaryDraftResp:
        """确认草稿并打权限标签。"""
        from .services.dictionary_store import DictionaryStore

        store = DictionaryStore()
        result = store.confirm_draft(dict_id, data.perm_tag, data.confirmed_by)
        if result is None:
            raise HTTPException(status_code=404, detail=f"dict {dict_id} not found")
        return result

    # -----------------------------------------------------------------------
    # 查询网关
    # -----------------------------------------------------------------------
    @router.post("/query", response_model=QueryResult)
    async def query_gateway(data: QueryReq) -> QueryResult:
        """查询网关入口。"""
        ds = _datasources.get(data.datasource_id)
        if not ds:
            raise HTTPException(status_code=404, detail=f"datasource {data.datasource_id} not found")

        from .security import decrypt_conn_info
        from .services.dictionary_store import DictionaryStore
        from .services.query_gate import query

        store = DictionaryStore()
        drafts = store.list_drafts(data.datasource_id)
        conn_info = decrypt_conn_info(ds["conn_info_enc"])

        result = query(
            datasource_id=data.datasource_id,
            user_perms=data.user_perms,
            sql_or_api_path=data.sql_or_api_path,
            params=data.params,
            conn_info=conn_info,
            ds_type=ds["ds_type"],
            drafts=drafts,
        )
        return result

    return router


__all__ = ["build_router"]
