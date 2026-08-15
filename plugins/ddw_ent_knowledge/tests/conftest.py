"""测试 fixtures。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path 中
_project_root = str(Path(__file__).resolve().parents[3])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


@pytest.fixture(autouse=True)
def _ensure_path():
    """确保 import 路径正确。"""
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    yield


@pytest.fixture()
def tmp_data_dir(tmp_path):
    """临时数据目录。"""
    return str(tmp_path / "kb_data")


@pytest.fixture()
def vector_store(tmp_data_dir):
    """临时 VectorStore。"""
    from plugins.ddw_ent_knowledge.core.vector_store import VectorStore

    db_path = os.path.join(tmp_data_dir, "vectors.sqlite")
    return VectorStore(db_path)


@pytest.fixture()
def simple_embedding():
    """SimpleEmbedding 实例。"""
    from plugins.ddw_ent_knowledge.core.embedding import SimpleEmbedding

    return SimpleEmbedding(dim=512)
