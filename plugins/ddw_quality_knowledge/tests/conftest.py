"""Test fixtures for ddw_quality_knowledge."""
import os
import sys

import pytest

# Project root is two levels up from tests/
_project_root = os.path.join(os.path.dirname(__file__), "..", "..")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.ddw_quality_knowledge.models import Base
from plugins.ddw_quality_knowledge.services import QualityKnowledgeService


@pytest.fixture
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    return QualityKnowledgeService(db_session)
