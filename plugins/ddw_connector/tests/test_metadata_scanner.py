"""DDW 连接器元数据发现框架测试用例（8 条，mock 不依赖真实数据库）。"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, text

from plugins.ddw_connector.models import FieldMeta, MetadataReport, TableMeta
from plugins.ddw_connector.services.dictionary_store import DictionaryStore
from plugins.ddw_connector.services.metadata_scanner import scan_datasource
from plugins.ddw_connector.services.query_gate import query


# ---------------------------------------------------------------------------
# Helper: 创建临时 SQLite 数据库
# ---------------------------------------------------------------------------


def _create_temp_sqlite() -> str:
    """创建一个带注释的临时 SQLite 数据库。"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                department TEXT,
                salary REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER,
                amount REAL,
                FOREIGN KEY (customer_id) REFERENCES employees(id)
            )
        """))
        conn.execute(text("INSERT INTO employees VALUES (1, 'Alice', 'Engineering', 10000)"))
        conn.execute(text("INSERT INTO employees VALUES (2, 'Bob', 'Finance', 8000)"))
        conn.execute(text("INSERT INTO orders VALUES (1, 1, 500)"))
        conn.commit()
    engine.dispose()
    return db_path


# ===========================================================================
# 1. sqlite 只读源：scan → 表/字段正确提取
# ===========================================================================


def test_scan_sqlite():
    """临时 sqlite → scan → 表/字段正确提取。"""
    db_path = _create_temp_sqlite()
    try:
        conn_info = {"connection_string": f"sqlite:///{db_path}"}
        report = scan_datasource(conn_info, "sql_readonly", datasource_id=1)

        assert report.ds_type == "sql_readonly"
        assert len(report.tables) == 2

        table_names = {t.name for t in report.tables}
        assert "employees" in table_names
        assert "orders" in table_names

        emp_table = next(t for t in report.tables if t.name == "employees")
        assert emp_table.row_count_estimate == 2
        field_names = {f.name for f in emp_table.fields}
        assert "id" in field_names
        assert "name" in field_names
        assert "department" in field_names
        assert "salary" in field_names

        # 主键
        id_field = next(f for f in emp_table.fields if f.name == "id")
        assert id_field.is_primary_key is True

        # 外键
        orders_table = next(t for t in report.tables if t.name == "orders")
        cust_field = next(f for f in orders_table.fields if f.name == "customer_id")
        assert cust_field.is_foreign_key is True
        assert cust_field.fk_ref_table == "employees"
    finally:
        os.unlink(db_path)


# ===========================================================================
# 2. OpenAPI 源：mock swagger.json → 资源/描述正确提取
# ===========================================================================


def test_scan_openapi():
    """mock swagger.json → 资源/描述正确提取。"""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0"},
        "paths": {
            "/users": {
                "get": {
                    "operationId": "listUsers",
                    "summary": "获取用户列表",
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/User"},
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "User": {
                    "description": "用户模型",
                    "type": "object",
                    "required": ["id", "name"],
                    "properties": {
                        "id": {"type": "integer", "description": "用户ID"},
                        "name": {"type": "string", "description": "用户名"},
                        "email": {"type": "string", "description": "邮箱"},
                    },
                }
            }
        },
    }

    mock_response = MagicMock()
    mock_response.json.return_value = spec
    mock_response.raise_for_status = MagicMock()

    with patch("plugins.ddw_connector.services.metadata_scanner.httpx") as mock_httpx:
        mock_httpx.get.return_value = mock_response
        conn_info = {"spec_url": "https://example.com/swagger.json"}
        report = scan_datasource(conn_info, "api_openapi", datasource_id=2)

    assert report.ds_type == "api_openapi"
    table_names = {t.name for t in report.tables}
    assert "User" in table_names
    assert "listUsers" in table_names

    user_table = next(t for t in report.tables if t.name == "User")
    field_names = {f.name for f in user_table.fields}
    assert "id" in field_names
    assert "name" in field_names
    assert "email" in field_names


# ===========================================================================
# 3. create_draft：scan 后生成 draft，status=draft
# ===========================================================================


def test_create_draft():
    """scan 后生成 draft，status=draft。"""
    db_path = _create_temp_sqlite()
    fd, store_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn_info = {"connection_string": f"sqlite:///{db_path}"}
        report = scan_datasource(conn_info, "sql_readonly", datasource_id=3)

        store = DictionaryStore(db_path=store_db)
        drafts = store.create_draft(report)
        assert len(drafts) > 0

        for d in drafts:
            assert d.status == "draft"
            assert d.perm_tag == "deny"
            assert d.datasource_id == 3

        # 验证 list_drafts
        listed = store.list_drafts(3)
        assert len(listed) == len(drafts)
    finally:
        os.unlink(db_path)
        os.unlink(store_db)


# ===========================================================================
# 4. confirm_draft：带 perm_tag 确认 → status=confirmed
# ===========================================================================


def test_confirm_draft():
    """带 perm_tag 确认 → status=confirmed。"""
    db_path = _create_temp_sqlite()
    fd, store_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn_info = {"connection_string": f"sqlite:///{db_path}"}
        report = scan_datasource(conn_info, "sql_readonly", datasource_id=4)

        store = DictionaryStore(db_path=store_db)
        drafts = store.create_draft(report)
        assert len(drafts) > 0

        # 确认第一条
        first = drafts[0]
        confirmed = store.confirm_draft(first.id, "public", "admin")
        assert confirmed is not None
        assert confirmed.status == "confirmed"
        assert confirmed.perm_tag == "public"
        assert confirmed.confirmed_by == "admin"

        # 确认第二条为部门标签
        second = drafts[1]
        confirmed2 = store.confirm_draft(second.id, "dept:财务", "admin")
        assert confirmed2 is not None
        assert confirmed2.perm_tag == "dept:财务"
        assert confirmed2.status == "confirmed"
    finally:
        os.unlink(db_path)
        os.unlink(store_db)


# ===========================================================================
# 5. 查询网关：confirmed+public 字段 → 查询成功返回数据
# ===========================================================================


def test_query_gate_public():
    """confirmed+public 字段 → 查询成功返回数据。"""
    db_path = _create_temp_sqlite()
    fd, store_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn_info = {"connection_string": f"sqlite:///{db_path}"}
        report = scan_datasource(conn_info, "sql_readonly", datasource_id=5)

        store = DictionaryStore(db_path=store_db)
        drafts = store.create_draft(report)

        # 全部确认为 public
        for d in drafts:
            store.confirm_draft(d.id, "public", "admin")

        confirmed_drafts = store.list_drafts(5)
        result = query(
            datasource_id=5,
            user_perms=["public"],
            sql_or_api_path="SELECT id, name FROM employees",
            params={},
            conn_info=conn_info,
            ds_type="sql_readonly",
            drafts=confirmed_drafts,
        )

        assert result.error is None
        assert result.row_count == 2
        assert "id" in result.columns
        assert "name" in result.columns
    finally:
        os.unlink(db_path)
        os.unlink(store_db)


# ===========================================================================
# 6. 查询网关：未确认字段 → permission_denied
# ===========================================================================


def test_query_gate_unconfirmed():
    """未确认字段 → permission_denied。"""
    db_path = _create_temp_sqlite()
    fd, store_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn_info = {"connection_string": f"sqlite:///{db_path}"}
        report = scan_datasource(conn_info, "sql_readonly", datasource_id=6)

        store = DictionaryStore(db_path=store_db)
        drafts = store.create_draft(report)
        # 不确认，直接查询

        result = query(
            datasource_id=6,
            user_perms=["public"],
            sql_or_api_path="SELECT * FROM employees",
            params={},
            conn_info=conn_info,
            ds_type="sql_readonly",
            drafts=drafts,
        )

        assert result.error == "permission_denied"
        assert "尚未确认" in result.detail
    finally:
        os.unlink(db_path)
        os.unlink(store_db)


# ===========================================================================
# 7. 查询网关：perm_tag=dept:财务 但用户无该权限 → permission_denied
# ===========================================================================


def test_query_gate_dept_denied():
    """perm_tag=dept:财务 但用户无该权限 → permission_denied。"""
    db_path = _create_temp_sqlite()
    fd, store_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn_info = {"connection_string": f"sqlite:///{db_path}"}
        report = scan_datasource(conn_info, "sql_readonly", datasource_id=7)

        store = DictionaryStore(db_path=store_db)
        drafts = store.create_draft(report)

        # 确认为 dept:财务
        for d in drafts:
            store.confirm_draft(d.id, "dept:财务", "admin")

        confirmed_drafts = store.list_drafts(7)
        result = query(
            datasource_id=7,
            user_perms=["dept:工程"],  # 用户只有工程部权限
            sql_or_api_path="SELECT * FROM employees",
            params={},
            conn_info=conn_info,
            ds_type="sql_readonly",
            drafts=confirmed_drafts,
        )

        assert result.error == "permission_denied"
        assert "不在您的权限范围" in result.detail
    finally:
        os.unlink(db_path)
        os.unlink(store_db)


# ===========================================================================
# 8. 查询网关：API 源只允许 GET（mock 检查方法）
# ===========================================================================


def test_query_gate_api_only_get():
    """API 源只允许 GET。"""
    fd, store_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        store = DictionaryStore(db_path=store_db)

        # 创建一个 mock report
        report = MetadataReport(
            datasource_id=8,
            ds_type="api_openapi",
            tables=[TableMeta(name="users", fields=[
                FieldMeta(name="id", field_type="integer"),
                FieldMeta(name="name", field_type="string"),
            ])],
        )
        drafts = store.create_draft(report)
        for d in drafts:
            store.confirm_draft(d.id, "public", "admin")

        confirmed_drafts = store.list_drafts(8)
        conn_info = {"base_url": "https://api.example.com"}

        mock_response = MagicMock()
        mock_response.json.return_value = [{"id": 1, "name": "Alice"}]
        mock_response.raise_for_status = MagicMock()

        with patch("plugins.ddw_connector.services.query_gate.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response

            result = query(
                datasource_id=8,
                user_perms=["public"],
                sql_or_api_path="/users",
                params={},
                conn_info=conn_info,
                ds_type="api_openapi",
                drafts=confirmed_drafts,
            )

            # 验证 httpx.get 被调用（GET 方法）
            mock_httpx.get.assert_called_once()
            call_args = mock_httpx.get.call_args
            assert "/users" in call_args[0][0]

        assert result.error is None
        assert result.row_count == 1
    finally:
        os.unlink(store_db)
