"""Response shapes shared by more than one router."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """One page of rows; `total` counts every row the query matches."""

    total: int
    items: list[T] = []
