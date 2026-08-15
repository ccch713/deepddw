"""数据字典草稿库：SQLite 表 connector_dictionary。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime, Text, create_engine
from sqlalchemy.orm import Session, declarative_base

from ..models import DictionaryDraftResp, MetadataReport

logger = logging.getLogger(__name__)

_Base = declarative_base()


class ConnectorDictionary(_Base):
    """数据字典草稿 ORM。"""

    __tablename__ = "connector_dictionary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    datasource_id = Column(Integer, nullable=False, index=True)
    table_name = Column(String(200), nullable=False)
    field_name = Column(String(200), nullable=False)
    field_type = Column(String(100), nullable=False)
    field_comment = Column(Text, nullable=True)
    perm_tag = Column(String(100), nullable=False, default="deny")
    status = Column(String(20), nullable=False, default="draft")  # draft / confirmed
    confirmed_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class DictionaryStore:
    """数据字典草稿 CRUD。"""

    def __init__(self, db_path: str = "ddw_connector.db") -> None:
        self.engine = create_engine(f"sqlite:///{db_path}")
        _Base.metadata.create_all(self.engine)

    def create_draft(self, report: MetadataReport) -> list[DictionaryDraftResp]:
        """从扫描报告生成草稿。"""
        drafts: list[DictionaryDraftResp] = []
        with Session(self.engine) as session:
            for table in report.tables:
                for field in table.fields:
                    draft = ConnectorDictionary(
                        datasource_id=report.datasource_id,
                        table_name=table.name,
                        field_name=field.name,
                        field_type=field.field_type,
                        field_comment=field.comment,
                        perm_tag="deny",
                        status="draft",
                    )
                    session.add(draft)
                    session.flush()
                    drafts.append(DictionaryDraftResp(
                        id=draft.id,
                        datasource_id=draft.datasource_id,
                        table_name=draft.table_name,
                        field_name=draft.field_name,
                        field_type=draft.field_type,
                        field_comment=draft.field_comment,
                        perm_tag=draft.perm_tag,
                        status=draft.status,
                        confirmed_by=draft.confirmed_by,
                        created_at=draft.created_at,
                        updated_at=draft.updated_at,
                    ))
            session.commit()
        return drafts

    def list_drafts(self, datasource_id: int) -> list[DictionaryDraftResp]:
        """列出数据源的所有字典草稿。"""
        with Session(self.engine) as session:
            rows = session.query(ConnectorDictionary).filter(
                ConnectorDictionary.datasource_id == datasource_id
            ).all()
            return [DictionaryDraftResp(
                id=r.id,
                datasource_id=r.datasource_id,
                table_name=r.table_name,
                field_name=r.field_name,
                field_type=r.field_type,
                field_comment=r.field_comment,
                perm_tag=r.perm_tag,
                status=r.status,
                confirmed_by=r.confirmed_by,
                created_at=r.created_at,
                updated_at=r.updated_at,
            ) for r in rows]

    def confirm_draft(self, dict_id: int, perm_tag: str, confirmed_by: str) -> Optional[DictionaryDraftResp]:
        """确认草稿并打权限标签。"""
        with Session(self.engine) as session:
            row = session.get(ConnectorDictionary, dict_id)
            if row is None:
                return None
            row.perm_tag = perm_tag
            row.status = "confirmed"
            row.confirmed_by = confirmed_by
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(row)
            return DictionaryDraftResp(
                id=row.id,
                datasource_id=row.datasource_id,
                table_name=row.table_name,
                field_name=row.field_name,
                field_type=row.field_type,
                field_comment=row.field_comment,
                perm_tag=row.perm_tag,
                status=row.status,
                confirmed_by=row.confirmed_by,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def reject_draft(self, dict_id: int) -> bool:
        """拒绝草稿。"""
        with Session(self.engine) as session:
            row = session.get(ConnectorDictionary, dict_id)
            if row is None:
                return False
            row.status = "draft"
            row.perm_tag = "deny"
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            return True
