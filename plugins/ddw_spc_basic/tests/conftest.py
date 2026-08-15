"""Test fixtures for ddw_spc_basic."""
import os
import sys

import pytest

_project_root = os.path.join(os.path.dirname(__file__), "..", "..")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.ddw_spc_basic.models import Base
from plugins.ddw_spc_basic.services import SPCService


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
    return SPCService(db_session)


@pytest.fixture
def normal_data():
    """Normally distributed data for testing."""
    import random
    random.seed(42)
    return [random.gauss(100, 2) for _ in range(50)]
