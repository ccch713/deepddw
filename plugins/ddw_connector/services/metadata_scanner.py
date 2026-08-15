"""元数据扫描核心：支持 sql_readonly 和 api_openapi 两种数据源。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import create_engine, inspect, text

from ..models import FieldMeta, MetadataReport, TableMeta

logger = logging.getLogger(__name__)


def scan_datasource(conn_info: dict[str, Any], ds_type: str, datasource_id: int) -> MetadataReport:
    """扫描数据源元数据，返回 MetadataReport。"""
    if ds_type == "sql_readonly":
        return _scan_sql(conn_info, datasource_id)
    elif ds_type == "api_openapi":
        return _scan_openapi(conn_info, datasource_id)
    else:
        raise ValueError(f"unsupported ds_type: {ds_type}")


# ---------------------------------------------------------------------------
# SQL 只读扫描
# ---------------------------------------------------------------------------


def _scan_sql(conn_info: dict[str, Any], datasource_id: int) -> MetadataReport:
    """通过 SQLAlchemy inspect 扫描 SQL 数据源。"""
    conn_str = conn_info.get("connection_string", "")
    engine = create_engine(conn_str)
    insp = inspect(engine)

    tables: list[TableMeta] = []
    for table_name in insp.get_table_names():
        columns = insp.get_columns(table_name)
        pk = insp.get_pk_constraint(table_name)
        pk_cols = set(pk.get("constrained_columns", [])) if pk else set()
        fks = insp.get_foreign_keys(table_name)
        fk_map: dict[str, str] = {}
        for fk in fks:
            for col in fk.get("constrained_columns", []):
                ref_table = fk.get("referred_table", "")
                fk_map[col] = ref_table

        fields: list[FieldMeta] = []
        for col in columns:
            fields.append(
                FieldMeta(
                    name=col["name"],
                    field_type=str(col.get("type", "unknown")),
                    comment=col.get("comment"),
                    nullable=col.get("nullable", True),
                    is_primary_key=col["name"] in pk_cols,
                    is_foreign_key=col["name"] in fk_map,
                    fk_ref_table=fk_map.get(col["name"]),
                )
            )

        # 行数估计
        row_count = None
        try:
            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                row_count = result.scalar()
        except Exception:
            logger.debug("row count failed for %s", table_name)

        # 表注释
        table_comment = None
        try:
            table_info = insp.get_table_comment(table_name)
            table_comment = table_info.get("text") if table_info else None
        except Exception:
            pass

        tables.append(
            TableMeta(
                name=table_name,
                row_count_estimate=row_count,
                comment=table_comment,
                fields=fields,
            )
        )

    engine.dispose()
    return MetadataReport(
        datasource_id=datasource_id,
        ds_type="sql_readonly",
        tables=tables,
        scanned_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# OpenAPI 扫描
# ---------------------------------------------------------------------------


def _scan_openapi(conn_info: dict[str, Any], datasource_id: int) -> MetadataReport:
    """解析 OpenAPI/Swagger JSON，提取资源和字段描述。"""
    spec_url = conn_info.get("spec_url", "")
    if not spec_url:
        raise ValueError("api_openapi requires spec_url in conn_info")

    resp = httpx.get(spec_url, timeout=30)
    resp.raise_for_status()
    spec = resp.json()

    tables: list[TableMeta] = []

    # 从 components.schemas 提取数据模型
    schemas = spec.get("components", {}).get("schemas", {})
    if not schemas:
        # Swagger 2.0 fallback
        schemas = spec.get("definitions", {})

    for schema_name, schema_def in schemas.items():
        props = schema_def.get("properties", {})
        required = set(schema_def.get("required", []))
        fields: list[FieldMeta] = []
        for field_name, field_def in props.items():
            ftype = field_def.get("type", field_def.get("$ref", "object"))
            fields.append(
                FieldMeta(
                    name=field_name,
                    field_type=str(ftype),
                    comment=field_def.get("description"),
                    nullable=field_name not in required,
                )
            )
        tables.append(
            TableMeta(
                name=schema_name,
                comment=schema_def.get("description"),
                fields=fields,
            )
        )

    # 从 paths 提取资源端点
    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for method, detail in methods.items():
            if method.lower() != "get":
                continue
            # 用 operationId 或 path 作为资源名
            op_id = detail.get("operationId", path.strip("/").replace("/", "_"))
            resp_fields: list[FieldMeta] = []
            # 从 200 响应 schema 提取字段
            resp_200 = detail.get("responses", {}).get("200", {})
            resp_schema = resp_200.get("content", {}).get("application/json", {}).get("schema", {})
            if resp_schema.get("type") == "array":
                items = resp_schema.get("items", {})
                ref = items.get("$ref", "")
                if ref:
                    ref_name = ref.split("/")[-1]
                    if ref_name in schemas:
                        ref_props = schemas[ref_name].get("properties", {})
                        for fname, fdef in ref_props.items():
                            resp_fields.append(
                                FieldMeta(
                                    name=fname,
                                    field_type=str(fdef.get("type", "object")),
                                    comment=fdef.get("description"),
                                )
                            )
            if resp_fields:
                tables.append(
                    TableMeta(
                        name=op_id,
                        comment=detail.get("summary") or detail.get("description"),
                        fields=resp_fields,
                    )
                )

    return MetadataReport(
        datasource_id=datasource_id,
        ds_type="api_openapi",
        tables=tables,
        scanned_at=datetime.now(timezone.utc),
    )
