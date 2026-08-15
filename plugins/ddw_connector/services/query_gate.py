"""查询网关：权限标签校验 + 只读查询。"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import create_engine, text

from ..models import QueryResult

logger = logging.getLogger(__name__)


def _check_permission(perm_tag: str, user_perms: list[str]) -> bool:
    """校验用户是否拥有该字段的权限标签。"""
    if perm_tag == "public":
        return True
    if perm_tag == "deny":
        return False
    # dept:<部门名> / role:<角色>
    return perm_tag in user_perms


def query(
    datasource_id: int,
    user_perms: list[str],
    sql_or_api_path: str,
    params: dict[str, Any],
    conn_info: dict[str, Any],
    ds_type: str,
    drafts: list[Any],
) -> QueryResult:
    """查询网关入口。

    校验流程：
    1. 数据源存在（由 router 层保证）
    2. 字段全部 confirmed
    3. 用户权限包含字段 perm_tag
    4. 执行只读查询
    """
    # 检查是否所有字段已确认
    unconfirmed = [d for d in drafts if d.status != "confirmed"]
    if unconfirmed:
        unconfirmed_fields = [f"{d.table_name}.{d.field_name}" for d in unconfirmed[:5]]
        return QueryResult(
            error="permission_denied",
            detail=f"字段 {', '.join(unconfirmed_fields)} 尚未确认，请先完成数据字典确认",
        )

    # 校验权限
    for d in drafts:
        if not _check_permission(d.perm_tag, user_perms):
            return QueryResult(
                error="permission_denied",
                detail=f"字段 {d.table_name}.{d.field_name} 不在您的权限范围",
            )

    # 执行查询
    if ds_type == "sql_readonly":
        return _query_sql(conn_info, sql_or_api_path, params)
    elif ds_type == "api_openapi":
        return _query_api(conn_info, sql_or_api_path, params)
    else:
        return QueryResult(error="unsupported", detail=f"不支持的数据源类型: {ds_type}")


def _query_sql(conn_info: dict[str, Any], sql: str, params: dict[str, Any]) -> QueryResult:
    """SQL 只读查询。"""
    conn_str = conn_info.get("connection_string", "")
    engine = create_engine(conn_str)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()]
            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
            )
    except Exception as e:
        return QueryResult(error="query_failed", detail=str(e))
    finally:
        engine.dispose()


def _query_api(conn_info: dict[str, Any], api_path: str, params: dict[str, Any]) -> QueryResult:
    """API 只读查询（只允许 GET）。"""

    base_url = conn_info.get("base_url", "")
    if not base_url:
        return QueryResult(error="config_error", detail="api_openapi 需要 base_url")

    # 强制 GET
    url = f"{base_url.rstrip('/')}/{api_path.lstrip('/')}"
    try:
        resp = httpx.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            columns = list(data[0].keys())
            rows = [list(item.values()) for item in data]
            return QueryResult(columns=columns, rows=rows, row_count=len(rows))
        elif isinstance(data, dict):
            columns = list(data.keys())
            rows = [list(data.values())]
            return QueryResult(columns=columns, rows=rows, row_count=1)
        return QueryResult(row_count=0)
    except Exception as e:
        return QueryResult(error="query_failed", detail=str(e))
