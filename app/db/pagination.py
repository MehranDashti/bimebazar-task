from collections.abc import Sequence
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class PaginationParams:
    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="Page number (1-based)"),
        page_size: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class Page(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta

    @classmethod
    def create(
        cls,
        items: Sequence[T],
        total: int,
        params: PaginationParams,
    ) -> "Page[T]":
        total_pages = max(1, -(-total // params.page_size))  # ceil division
        return cls(
            items=list(items),
            meta=PageMeta(
                page=params.page,
                page_size=params.page_size,
                total=total,
                total_pages=total_pages,
                has_next=params.page < total_pages,
                has_prev=params.page > 1,
            ),
        )


async def paginate(
    db: AsyncSession,
    query: Select,
    params: PaginationParams,
) -> tuple[list, int]:
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total: int = total_result.scalar_one()

    paginated_query = query.offset(params.offset).limit(params.limit)
    result = await db.execute(paginated_query)
    items = result.scalars().all()

    return list(items), total
