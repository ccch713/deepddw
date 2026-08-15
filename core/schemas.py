"""API 统一契约模型。所有列表端点必须返回 ListResponse。"""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ListResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
